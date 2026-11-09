"""Independent checks for complete, corroborated Realt observations.

Never converts a partial collection into a valid snapshot.
"""
from datetime import datetime, timedelta, timezone
from math import ceil
from collections import Counter


def verify_pages(pages, agencies, page_size):
    """Verify every accepted page and the final count, including bounded growth.

    The live source may append newly created ads while a stable oldest-first
    scan is in progress. We accept such growth only when every page is present
    and all returned rows exactly cover the final total. Shrinkage and gaps
    remain invalid; the caller independently rejects UUID overlap and reorders.
    """
    summary = {}
    for agency in agencies:
        observations = [p for p in pages if p["agency"] == agency]
        if not observations:
            raise RuntimeError("Missing source list pages for an agency")
        first_total = observations[0]["total"]
        if first_total <= 0 or observations[0]["page"] != 1:
            raise RuntimeError("Missing or invalid first source page")
        totals = [p["total"] for p in observations]
        if any(after < before for before, after in zip(totals, totals[1:])):
            raise RuntimeError("Source pagination total shrank during a scan")
        final_total = totals[-1]
        max_growth = max(20, (first_total + 19) // 20)
        if final_total > first_total + max_growth:
            raise RuntimeError("Source pagination grew beyond safe allowance")
        expected_pages = ceil(final_total / page_size)
        numbers = [p["page"] for p in observations]
        if numbers != list(range(1, expected_pages + 1)):
            raise RuntimeError("Incomplete or repeated source pages")
        for p in observations:
            required = min(page_size, final_total - (p["page"] - 1) * page_size)
            if p["returned"] != required:
                raise RuntimeError("Source pagination count differs materially from final totalCount")
        actual = sum(p["returned"] for p in observations)
        if actual != final_total:
            raise RuntimeError("Incomplete source page rows")
        summary[agency] = {"reported": final_total, "retrieved": actual, "pages": expected_pages}
    return summary


def assess_drop(previous, count, uuids, observed_at, candidate=None):
    """Two independent consistent full scans are required to accept a major drop."""
    baseline_count = int(previous.get("rows") or 0)
    baseline_at = previous.get("snapshot_at")
    unique = set(uuids)
    if len(unique) != count or not count:
        raise RuntimeError("Missing or duplicate source UUIDs")
    if not baseline_count or count >= baseline_count * 0.8:
        return True, None, "normal"
    next_candidate = {
        "reference_snapshot_at": baseline_at,
        "rows": count,
        "observed_at": observed_at,
        "uuids": sorted(unique),
    }
    if not candidate or candidate.get("reference_snapshot_at") != baseline_at:
        return False, next_candidate, "first independent drop observation"
    try:
        before = datetime.fromisoformat(candidate["observed_at"].replace("Z", "+00:00"))
        now = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        delta = now - before
        old_ids = set(candidate["uuids"])
        same_count = 0.85 <= count / int(candidate["rows"]) <= 1.15
        overlap = len(old_ids & unique) / min(len(old_ids), len(unique))
        # Frequent scheduler/fallback runs must not move the first observation
        # forward forever while waiting for the independent-scan interval.
        if timedelta(0) <= delta < timedelta(minutes=20) and same_count and overlap >= 0.85:
            return False, candidate, "waiting for independent drop confirmation"
        if (timedelta(minutes=20) <= delta <= timedelta(hours=48)
                and same_count and overlap >= 0.85):
            return True, None, "major drop independently corroborated"
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    return False, next_candidate, "unconfirmed source count drop"


def diagnose_uuid_integrity(objects, source_pages, source_file):
    """Describe rejected UUIDs without trusting or rewriting source rows.

    Keep only small, non-personal identifier/page samples in durable health data.
    No duplicate is removed and this report never authorizes a snapshot.
    """
    identifiers = [str(item.get("uuid") or "") for item in objects]
    counts = Counter(identifiers)
    duplicates = {uid: count for uid, count in counts.items() if uid and count > 1}
    affected = []
    for page in source_pages:
        bad_positions = []
        for position, item in enumerate(page.get("identifiers") or [], 1):
            uid = str(item.get("uuid") or "")
            if not uid or uid in duplicates:
                bad_positions.append({
                    "position": position,
                    "uuid": uid or None,
                    "code": str(item.get("code") or "") or None,
                })
        if bad_positions:
            affected.append({
                "agency": page.get("agency"),
                "page": page.get("page"),
                "source_total": page.get("total"),
                "anomaly_count": len(bad_positions),
                "examples": bad_positions[:12],
            })
    return {
        "status": "rejected",
        "reason": "Empty or duplicate source UUIDs",
        "source_file": source_file,
        "filtered_rows": len(identifiers),
        "missing_uuid_count": counts.get("", 0),
        "duplicate_uuid_count": len(duplicates),
        "duplicate_extra_rows": sum(total - 1 for total in duplicates.values()),
        "duplicate_samples": [
            {"uuid": uid, "occurrences": count}
            for uid, count in sorted(duplicates.items())
        ][:15],
        "source_pages_checked": len(source_pages),
        "affected_pages": affected[:20],
        "affected_pages_truncated": len(affected) > 20,
        "valid": bool(identifiers) and not counts.get("", 0) and not duplicates,
    }

