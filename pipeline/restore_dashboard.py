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
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pipeline.archive import REPO, Releases, sha, verify_packet
from pipeline.storage import rotate


# Exact collector commits retained for the November 6–7 release outage.
COLLECTOR_COMMITS = {
    "2026-11-07T18:37:13Z": "02a88a596243e58a726ddb8132a03697ac6aaeec",
    "2026-11-07T18:07:13Z": "6cc363cb34bf659e7857cbfbdab1cf6500a6feee",
    "2026-11-07T16:37:13Z": "4f753467283d34f9a22745498c064756240d3dbb",
    "2026-11-07T15:37:13Z": "14a61cd2daa2e36d613e54f48b1ad7d1fe4a7c1b",
    "2026-11-07T14:37:13Z": "4ebede65c02f0d12a04b81537fc45032a20e88f8",
    "2026-11-07T13:37:13Z": "14104234899e75a8850c2ab9539347b4f5279c7f",
    "2026-11-07T12:37:12Z": "7dece2d4c6796105bdcd001643e7922b5b3be867",
    "2026-11-07T11:37:12Z": "2a80e414b58398d82ebd1fa52771de9025971708",
    "2026-11-07T10:37:12Z": "21159eb4d0355d5c7b476b3c8116c9c97b5acf09",
    "2026-11-07T09:37:15Z": "ba4480943f8cda7876dc531d70bebe81263ae8c1",
    "2026-11-07T08:37:12Z": "40ab4a01806412f7ac41908951443a673248dc91",
    "2026-11-07T07:37:12Z": "3f9b66e8f0db27df2957f0ffbecf1931950589cf",
    "2026-11-07T06:37:14Z": "0d87bfdeb587f7dfd6ca7f3b81e0437ef54db7c7",
    "2026-11-07T06:07:13Z": "32de2dbb1ad33c4d34d17852d49a8fbc70e84f8e",
    "2026-11-07T04:37:14Z": "f81017376946ed1392dc651ea9c33bc273a9ae74",
    "2026-11-06T18:37:14Z": "5d8f4c835793c61b37fd3142ccb9516ddd2640da",
    "2026-11-06T17:37:14Z": "7e40f24792eb70d96d05a4682e4e9aca2f8bbe15",
    "2026-11-06T16:37:13Z": "f8a4c279c6a7c950e240c5aea7fb14fb701bff0c",
    "2026-11-06T15:37:15Z": "5f2457e4de1454957ae209bfca5132138832ab8f",
    "2026-11-06T14:37:16Z": "42aff4e321dd9a2b88fd20cdb31fc449aa86626c",
    "2026-11-06T13:07:13Z": "8a5764f77dd33b62c627081f52acb5208515c057",
    "2026-11-06T11:37:16Z": "9d35856ae3475e3a4889d634623d8f7aac766b44",
    "2026-11-06T09:37:12Z": "188bff00dc72e6e216fc06fa0e9ebca46e41847a",
    "2026-11-06T08:37:13Z": "4819156ca0a6a4e4439b44eaefc85a105307d353",
    "2026-11-06T07:37:14Z": "b1773ac8c7e15c5f961fbb0dc45d591532adbbfa",
    "2026-11-06T06:37:14Z": "d867e6f937bab651a8f56ea65dccd7ccea542684",
    "2026-11-06T05:37:16Z": "df7009afbe911e91af87e31a089280a694bf3fcc",
    "2026-11-06T04:37:12Z": "15e862c2ee58440f79e27c8f739485e1739bf4ee",
}


class AssetRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


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
            stamp = entry["snapshot_at"]
            commit = COLLECTOR_COMMITS.get(stamp)
            if commit:
                source = f"https://raw.githubusercontent.com/{REPO}/{commit}/data/snapshots.csv"
                try:
                    with build_opener().open(source, timeout=15) as response:
                        columns, saved = read_csv(response.read())
                    snapshot = [row for row in saved if row["snapshot_at"] == stamp]
                    if len(snapshot) == entry["rows"]:
                        fields = list(dict.fromkeys(fields + columns))
                        rows.extend(snapshot)
                        continue
                except OSError as error:
                    print(f"Collector commit unavailable for {stamp}: {error}")
            asset = f"https://api.github.com/repos/{REPO}/releases/assets/{int(entry['asset_id'])}"
            request = Request(asset, headers={
                "Authorization": f"Bearer {releases.token}",
                "Accept": "application/octet-stream",
                "User-Agent": "realt-dashboard-restore",
            })
            try:
                with build_opener(AssetRedirect()).open(request, timeout=30) as response:
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
