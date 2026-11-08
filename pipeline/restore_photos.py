"""Backfill the dashboard photo index from retained Realt snapshots."""
import gzip
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, build_opener
from zipfile import ZipFile

from pipeline.archive import REPO, Releases, sha, verify_packet
from pipeline.collect import atomic_json
from pipeline.restore_dashboard import AssetRedirect


def merge_snapshot(index, snapshot):
    stamp = snapshot["snapshot_at"]
    for obj in snapshot.get("minsk_mir_objects") or []:
        key = obj.get("uuid")
        urls = [url for url in obj.get("images") or []
                if isinstance(url, str) and url.startswith("https://")]
        if not key or not urls:
            continue
        old = index["images"].get(key, [])
        if stamp >= index["dates"].get(key, ""):
            index["dates"][key] = stamp
            old, urls = urls, old
        index["images"][key] = list(dict.fromkeys(old + urls))[:8]


def main():
    data = Path("data")
    target = data / "photo_manifest.json"
    archive = data / "archive"
    state = data / "health" / "photo_archive.json"
    index = json.loads(target.read_text(encoding="utf-8"))
    index.setdefault("dates", dict.fromkeys(index["images"], index["snapshot_at"]))
    processed = set(json.loads(state.read_text())["processed"]) if state.exists() else set()
    if not index.get("legacy_indexed"):
        for file in sorted((data / "raw").glob("*.json*")):
            if file.suffix not in (".json", ".gz"):
                continue
            opener = gzip.open if file.suffix == ".gz" else open
            with opener(file, "rt", encoding="utf-8") as stream:
                merge_snapshot(index, json.load(stream))
        index["legacy_indexed"] = True
    entries = [
        entry for month in json.loads((archive / "index.json").read_text())["months"]
        for entry in json.loads((archive / f"{month}.json").read_text())["snapshots"]
        if entry["snapshot_at"] >= "2026-10-05" and entry["sha256"] not in processed
    ]
    releases = Releases()

    def read(entry):
        try:
            asset = f"https://api.github.com/repos/{REPO}/releases/assets/{int(entry['asset_id'])}"
            request = Request(asset, headers={"Authorization": f"Bearer {releases.token}",
                              "Accept": "application/octet-stream", "User-Agent": "realt-photo-index"})
            try:
                with build_opener(AssetRedirect()).open(request, timeout=15) as response:
                    packet = response.read()
            except OSError:
                packet = b""
            if sha(packet) != entry["sha256"]:
                packet = releases.read(entry["url"])
            if sha(packet) != entry["sha256"]:
                raise ValueError("Packet hash mismatch")
            manifest = verify_packet(packet)
            if manifest["snapshot_at"] != entry["snapshot_at"]:
                raise ValueError("Packet timestamp mismatch")
            with ZipFile(io.BytesIO(packet)) as bundle:
                return [json.loads(gzip.decompress(bundle.read(name))) for name in manifest["raw_members"]]
        except (OSError, RuntimeError, ValueError) as error:
            print(f"Photo backfill deferred for {entry['snapshot_at']}: {error}", flush=True)
            return None

    batch = entries[-16:]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for entry, snapshots in zip(batch, pool.map(read, batch)):
            if snapshots is None:
                continue
            for snapshot in snapshots:
                merge_snapshot(index, snapshot)
            processed.add(entry["sha256"])
    atomic_json(target, index)
    remaining = sum(entry["sha256"] not in processed for entry in entries)
    atomic_json(state, {"processed": sorted(processed), "remaining": remaining,
                        "listings_with_photos": len(index["images"])})
    print(f"Photo index: {len(index['images'])} listings, {remaining} packets pending")


if __name__ == "__main__":
    main()
