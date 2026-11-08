"""Expose verified release snapshots in the dashboard's daily CSV format."""
import csv
import gzip
import io
import json
import shutil
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile
from urllib.request import Request, urlopen

from pipeline.archive import REPO, Releases, sha, verify_packet
from pipeline.storage import rotate


def read_csv(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    return reader.fieldnames, list(reader)


def main():
    data = Path("data")
    archive = data / "archive"
    daily = data / "snapshots"
    releases = Releases()
    pending = defaultdict(list)
    for month in json.loads((archive / "index.json").read_text())["months"]:
        for entry in json.loads((archive / f"{month}.json").read_text())["snapshots"]:
            pending[entry["snapshot_at"][:10]].append(entry)

    def restore(item):
        day, entries = item
        target = daily / f"{day}.csv.gz"
        existing = read_csv(gzip.decompress(target.read_bytes()))[1] if target.exists() else []
        have = {row["snapshot_at"] for row in existing}
        fields, rows, failed = [], [], []
        for entry in entries:
            if entry["snapshot_at"] in have:
                continue
            asset = f"https://api.github.com/repos/{REPO}/releases/assets/{int(entry['asset_id'])}"
            request = Request(asset, headers={
                "Authorization": f"Bearer {releases.token}",
                "Accept": "application/octet-stream",
                "User-Agent": "realt-dashboard-restore",
            })
            try:
                with urlopen(request, timeout=30) as response:
                    packet = response.read()
                if sha(packet) != entry["sha256"]:
                    packet = releases.read(entry["url"])
            except (OSError, RuntimeError) as error:
                failed.append(entry["snapshot_at"])
                print(f"Archive temporarily unavailable for {entry['snapshot_at']}: {error}")
                continue
            if sha(packet) != entry["sha256"]:
                raise ValueError("Archive packet hash mismatch")
            manifest = verify_packet(packet)
            if manifest["snapshot_at"] != entry["snapshot_at"]:
                raise ValueError("Unexpected archive timestamp")
            with ZipFile(io.BytesIO(packet)) as bundle:
                columns, snapshot = read_csv(gzip.decompress(bundle.read(entry["csv_member"])))
            if len(snapshot) != entry["rows"] or any(row["snapshot_at"] != entry["snapshot_at"] for row in snapshot):
                raise ValueError("Incomplete archive snapshot")
            fields = list(dict.fromkeys(fields + columns))
            rows.extend(snapshot)
        if not rows:
            return failed
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / "snapshots").mkdir()
            if target.exists():
                shutil.copy2(target, temp / "snapshots" / target.name)
            with (temp / "snapshots.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fields)
                writer.writeheader()
                writer.writerows(rows)
            rotate(temp)
            staged = target.with_suffix(".restore")
            shutil.copyfile(temp / "snapshots" / target.name, staged)
            staged.replace(target)
        print(f"{day}: restored {len(rows)} rows")
        return failed

    daily.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        missing = [stamp for batch in pool.map(restore, sorted(pending.items())) for stamp in batch]
    if missing:
        raise RuntimeError(f'{len(missing)} archive snapshots still unavailable; restored days can be committed')


if __name__ == "__main__":
    main()
