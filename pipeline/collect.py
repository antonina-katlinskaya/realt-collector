"""Transactional wrapper: original anonymous queries, filters and pauses are preserved."""
import contextlib
import csv
import datetime as dt
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import requests
import collector
import config as C
from pipeline.storage import rotate, compress_raw
from pipeline.developer_filter import developer_offer
from pipeline.archive import archive_snapshot, tail
from pipeline.source_quality import verify_pages, assess_drop, diagnose_uuid_integrity

ROOT = Path.cwd()
DATA = ROOT / "data"
HEALTH = DATA / "health"


class SourceBlocked(BaseException):
    pass


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run():
    HEALTH.mkdir(parents=True, exist_ok=True)
    history_file = HEALTH / "collection_runs.json"
    history = json.loads(history_file.read_text()) if history_file.exists() else []
    started = dt.datetime.now(dt.timezone.utc)
    record = {"started_at": started.isoformat(), "status": "failed", "http_403": 0, "http_429": 0,
              "requests": 0, "d1_rows_read": 0, "d1_rows_written": 0}
    # Never silently retry a failed slot indefinitely.
    slot = os.environ.get("COLLECTION_SLOT", "")
    attempts = [r for r in history if r.get("slot") == slot]
    if slot and len(attempts) >= 2:
        raise RuntimeError("Retry budget exhausted for this collection slot")
    record["slot"] = slot
    received = {}
    source_pages = []
    deferred_history = []
    original_session = requests.Session
    original_history = collector.fetch_view_history

    def postpone_history(session, uuid):
        # The original, unmodified query and pauses run in a bounded later batch.
        deferred_history.append(uuid)
        return {}


    class TrackedSession(original_session):
        def begin_source_scan(self, agency):
            # Failed passes remain in logs, never in the accepted-page evidence.
            source_pages[:] = [p for p in source_pages if p["agency"] != agency]

        def post(self, *args, **kwargs):
            record["requests"] += 1
            response = super().post(*args, **kwargs)
            if response.status_code in (403, 429):
                record["http_" + str(response.status_code)] += 1
                raise SourceBlocked("Realt source blocked: HTTP " + str(response.status_code))
            if response.ok:
                payload = response.json()
                for entry in payload if isinstance(payload, list) else [payload]:
                    if entry.get("errors"):
                        raise SourceBlocked("Incomplete GraphQL response")
                    objects = ((entry.get("data") or {}).get("searchObjects") or {}).get("body") or {}
                    if objects:
                        req = (kwargs.get("json") or [{}])[0]
                        variables = req.get("variables") or {}
                        body_vars = variables.get("data") or {}
                        agencies = (body_vars.get("where") or {}).get("agencyUuids") or []
                        pg = body_vars.get("pagination") or {}
                        pagination = objects.get("pagination") or {}
                        if agencies and pg.get("page") is not None and not getattr(self, "source_pagination_probe", False):
                            source_pages.append({
                                "agency": agencies[0], "page": int(pg["page"]),
                                "total": int(pagination["totalCount"]),
                                "returned": len(objects.get("results") or []),
                                # Read-only provenance for any later UUID rejection.
                                "identifiers": [
                                    {"uuid": str(item.get("uuid") or ""),
                                     "code": str(item.get("code") or "")}
                                    for item in objects.get("results") or []
                                ],
                            })
                    at = dt.datetime.now(dt.timezone.utc).isoformat()
                    for item in objects.get("results") or []:
                        received[str(item.get("uuid"))] = at
            return response

    original_paths={name:getattr(C,name) for name in ('DATA_DIR','RAW_DIR','REPORTS_DIR','SNAPSHOTS_CSV','SEEN_JSON')}
    if sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file())>=2_000_000_000:
        raise RuntimeError('Archive size guard reached (2 GB); collection stopped')
    staging = Path(tempfile.mkdtemp(prefix="realt-collection-"))
    try:
        # Original collector's path settings are redirected, not its query/filter/pause logic.
        for filename in ("snapshots.csv", "listings_seen.json"):
            if (DATA / filename).exists():
                shutil.copy2(DATA / filename, staging / filename)
        C.DATA_DIR, C.RAW_DIR = str(staging), str(staging / "raw")
        C.REPORTS_DIR = str(staging / "reports")
        C.SNAPSHOTS_CSV, C.SEEN_JSON = str(staging / "snapshots.csv"), str(staging / "listings_seen.json")
        requests.Session = TrackedSession
        collector.fetch_view_history = postpone_history
        collector.run()
        raw_files = list((staging / "raw").glob("*.json"))
        if len(raw_files) != len(C.AGENCIES):
            raise RuntimeError("Incomplete agency snapshot")
        completed = dt.datetime.now(dt.timezone.utc)
        latest, objects_count = "", 0
        raw_paths = []
        photo_manifest = {}
        all_source_ids = []
        known_developer_ids = set()
        if (DATA / 'developer_manifest.json').exists():
            existing = json.loads((DATA / 'developer_manifest.json').read_text(encoding='utf-8'))
            if existing.get('rule_version') == 2:
                known_developer_ids.update(existing.get('ids') or [])
        current_developer_ids = set()
        for file in raw_files:
            raw = json.loads(file.read_text())
            objects = raw.get("minsk_mir_objects") or []
            ids = [str(o.get("uuid") or "") for o in objects]
            if not ids or not all(ids) or len(ids) != len(set(ids)):
                report = diagnose_uuid_integrity(objects, source_pages, file.name)
                report.update({
                    "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "collection_started_at": started.isoformat(),
                    "collection_slot": slot,
                    "snapshot_at": raw.get("snapshot_at"),
                })
                atomic_json(HEALTH / "source_uuid_diagnostics.json", report)
                print("SOURCE_UUID_INTEGRITY_REJECTED " + json.dumps(
                    report, ensure_ascii=False, separators=(",", ":")
                ), flush=True)
                # Preserve the existing fail-closed rejection and the prior full snapshot.
                raise RuntimeError("Empty or duplicate source UUIDs")
            all_source_ids.extend(ids)
            for obj in objects:
                if developer_offer(obj):
                    current_developer_ids.add(str(obj['uuid']))
                    known_developer_ids.add(str(obj['uuid']))
                images = obj.get('images') or []
                image_urls = [value for value in images if isinstance(value,str) and value.startswith('https://')]
                if image_urls: photo_manifest[str(obj['uuid'])] = image_urls[:5]
                obj["observed_at"] = received.get(str(obj["uuid"]))
                if not obj["observed_at"]:
                    raise RuntimeError("Missing actual observation time")
            raw.update(collection_started_at=started.isoformat(), collection_completed_at=completed.isoformat())
            file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            latest = max(latest, raw["snapshot_at"])
            objects_count += len(objects)
            raw_paths.append("data/raw/" + file.name + ".gz")
        atomic_json(staging / 'photo_manifest.json', {'snapshot_at': latest, 'images': photo_manifest})
        atomic_json(staging / 'developer_manifest.json', {'snapshot_at': latest, 'rule_version': 2, 'ids': sorted(known_developer_ids), 'current_ids': sorted(current_developer_ids), 'current_total': objects_count})
        with (staging / "snapshots.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        fields = list(rows[0])
        if "observed_at" not in fields:
            fields.append("observed_at")
        for row in rows:
            if row["snapshot_at"] == latest:
                row["observed_at"] = received.get(row["uuid"], "")
        with (staging / "snapshots.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(rows)
        release_archive = os.environ.get('REALT_RELEASE_ARCHIVE') == '1'
        if not release_archive:
            if (DATA / "snapshots").exists():
                shutil.copytree(DATA / "snapshots", staging / "snapshots")
            storage = rotate(staging)
        # A big change must be corroborated by another COMPLETE independent source scan.
        source_quality = verify_pages(source_pages, C.AGENCIES.values(), C.PAGE_SIZE)
        marker = DATA / 'collection_state.json'
        previous = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else {}
        candidate_path = HEALTH / 'source_drop_candidate.json'
        candidate = json.loads(candidate_path.read_text(encoding='utf-8')) if candidate_path.exists() else None
        accepted, new_candidate, quality_reason = assess_drop(
            previous, objects_count, all_source_ids, started.isoformat(), candidate)
        if not accepted:
            atomic_json(candidate_path, new_candidate)
            raise RuntimeError('Large Realt source drop quarantined pending a second complete agreeing scan')
        # A fresh listing/price/photo snapshot is independent of the expensive
        # one-time historical view backfill; never block freshness on its backlog.
        queue_file = DATA / 'history_backfill_pending.json'
        old_queue = json.loads(queue_file.read_text(encoding='utf-8')) if queue_file.exists() else []
        pending = list(dict.fromkeys(old_queue + deferred_history))
        done = []
        if pending:
            seen_path = staging / 'listings_seen.json'
            seen = json.loads(seen_path.read_text(encoding='utf-8'))
            session = requests.Session()
            session.headers.update({
                'content-type': 'application/json', 'user-agent': C.USER_AGENT,
                'accept': 'application/json',
            })
            for uuid in pending[:12]:
                if uuid not in seen:
                    done.append(uuid)
                    continue
                try:
                    history_views = original_history(session, uuid)
                    if not history_views or all(value is None for value in history_views.values()):
                        print('View history unavailable; keep pending:', uuid)
                        break
                    seen[uuid]['history_views'] = history_views
                    done.append(uuid)
                except SourceBlocked:
                    raise
                except Exception as error:
                    print('Historical view backfill postponed:', type(error).__name__, str(error))
                    break
            if done:
                atomic_json(seen_path, seen)
        remaining = [uuid for uuid in pending if uuid not in set(done)]
        atomic_json(staging / 'history_backfill_pending.json', remaining)
        compress_raw(staging / "raw")
        archive_entry = None
        if release_archive:
            if (DATA / 'archive').exists():shutil.copytree(DATA / 'archive',staging / 'archive')
            archive_entry=archive_snapshot(staging,list((staging/'raw').glob('*.gz')),
                {'snapshot_at':latest,'completed_at':completed.isoformat(),'rows':objects_count})
            storage={**tail(staging/'snapshots.csv'),'archive':'verified-github-release','packet_bytes':archive_entry['bytes']}
            # Only newly-created staging RAW files are omitted from Git after verified readback.
            # Existing repository RAW and legacy daily CSV archives are untouched.
            shutil.rmtree(staging/'raw')
            raw_paths=[]
        # A full snapshot is made visible only after all checks complete.
        for file in staging.rglob("*"):
            if file.is_file():
                target = DATA / file.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
        record.update(status="ok", completed_at=completed.isoformat(), snapshot_at=latest,
                      objects=objects_count, duration_seconds=round((completed-started).total_seconds(), 3),
                      source_quality=source_quality, quality_reason=quality_reason,
                      history_backfill_pending=len(remaining), storage=storage)
        atomic_json(DATA / "collection_state.json", {"schema": 1, "complete": True,
                    "snapshot_at": latest, "completed_at": completed.isoformat(), "rows": objects_count,
                    "raw_paths": raw_paths, "archive_entry":archive_entry,
                    "source_quality": source_quality, "quality_reason": quality_reason,
                    "history_backfill_pending": len(remaining),
                    "observed_at": "per-object in raw snapshots", "duration_seconds": record["duration_seconds"]})
        if candidate_path.exists():
            candidate_path.unlink()
    except BaseException as error:
        record["retryable_pagination"] = isinstance(error, collector.SourcePaginationChanged)
        record.update(error=type(error).__name__ + ": " + str(error), duration_seconds=round((dt.datetime.now(dt.timezone.utc)-started).total_seconds(),3))
        raise
    finally:
        requests.Session = original_session
        collector.fetch_view_history = original_history
        for name,value in original_paths.items():setattr(C,name,value)
        shutil.rmtree(staging, ignore_errors=True)
        history.append(record)
        atomic_json(history_file, history[-1000:])


if __name__ == "__main__":
    run()

