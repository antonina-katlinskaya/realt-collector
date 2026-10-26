"""Lossless daily gzip partitions and a bounded compatibility CSV."""
import csv
import gzip
import io
import json
from collections import defaultdict, Counter
from pathlib import Path


def rotate(data_dir):
    data = Path(data_dir)
    flat = data / "snapshots.csv"
    with flat.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows or "snapshot_at" not in fields:
        raise ValueError("Cannot rotate an empty or invalid snapshot")
    groups = defaultdict(list)
    for row in rows:
        groups[row["snapshot_at"][:10]].append(row)
    def identity(row):
        return tuple(sorted((k,v) for k,v in row.items() if v not in (None,'')))
    archive = data / "snapshots"
    archive.mkdir(exist_ok=True)
    for day, current in groups.items():
        target = archive / (day + ".csv.gz")
        old_rows = []
        if target.exists():
            with gzip.open(target, "rt", encoding="utf-8-sig", newline="") as f:
                old = csv.DictReader(f)
                fields = list(dict.fromkeys(fields + list(old.fieldnames or [])))
                for row in old:
                    old_rows.append(row)
        # Preserve conflicting versions and the multiplicity of identical old rows.
        # The recent window overlaps the archive: merge maximum occurrence counts.
        old_counts=Counter(identity(row) for row in old_rows)
        current_counts=Counter(identity(row) for row in current)
        merged=old_counts | current_counts
        examples={identity(row):row for row in old_rows+current}
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for key in sorted(merged,key=lambda k:(examples[k]["snapshot_at"],examples[k]["uuid"],k)):
            writer.writerows([examples[key]]*merged[key])
        encoded = stream.getvalue().encode("utf-8-sig")
        temp = target.with_suffix(".tmp")
        temp.write_bytes(gzip.compress(encoded, mtime=0))
        if gzip.decompress(temp.read_bytes()) != encoded:
            raise ValueError("Archive roundtrip failed")
        temp.replace(target)
    # Keep the last 32 *distinct* snapshots, not rows: enough for daily views at 30 min.
    times = sorted({r["snapshot_at"] for r in rows})[-32:]
    kept = [r for r in rows if r["snapshot_at"] in set(times)]
    temp = flat.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(kept)
    temp.replace(flat)
    if flat.stat().st_size > 75 * 1024 * 1024:
        raise ValueError("Compatibility CSV exceeds safety budget")
    return {"archive_days": len(list(archive.glob("*.csv.gz"))), "recent_snapshots": len(times),
            "recent_csv_bytes": flat.stat().st_size}


def compress_raw(raw_dir):
    for source in Path(raw_dir).glob("*.json"):
        content = source.read_bytes()
        target = source.with_suffix(".json.gz")
        encoded = gzip.compress(content, mtime=0)
        if gzip.decompress(encoded) != content:
            raise ValueError("Raw snapshot compression failed")
        target.write_bytes(encoded)
        source.unlink()
