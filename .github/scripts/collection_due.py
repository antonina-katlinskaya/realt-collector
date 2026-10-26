"""Shared daytime freshness gate; no forced fresh/manual recollection."""
import csv
import datetime as dt
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.schedule import due, expected_slot
from pipeline.cadence import choose, load_history

def latest_snapshot(path="data/snapshots.csv"):
    state=Path("data/collection_state.json")
    if state.exists():
        data=json.loads(state.read_text())
        if data.get("complete") is not True:raise RuntimeError("Incomplete collection state")
        return data["snapshot_at"]
    if not Path(path).exists():return ""
    with open(path,encoding="utf-8-sig",newline="") as file:
        return max((r["snapshot_at"] for r in csv.DictReader(file) if r.get("uuid")),default="")

def main():
    now=dt.datetime.now(dt.timezone.utc)
    history=load_history()
    data_bytes=sum(p.stat().st_size for p in Path('data').rglob('*') if p.is_file())
    budget={"safe":data_bytes<2_000_000_000,"data_bytes":data_bytes,"d1_rows_read":0,"d1_rows_written":0,
            "reason":"Сборщик работает в GitHub без D1; предел рабочего архива 2 ГБ"}
    interval,reason=choose(history,budget,now)
    last=latest_snapshot()
    target=expected_slot(now,interval)
    attempts=[r for r in history if r.get("slot")==target.isoformat()]
    needed=due(last,now,interval) and len(attempts)<2
    if attempts:
        cooldown=60 if attempts[-1].get("http_403") or attempts[-1].get("http_429") else 30
        if now-dt.datetime.fromisoformat(attempts[-1]["started_at"])<dt.timedelta(minutes=cooldown):needed=False
    blocked=[r for r in history if r.get('http_403') or r.get('http_429')]
    if blocked and now-dt.datetime.fromisoformat(blocked[-1]['started_at'])<dt.timedelta(minutes=60):needed=False
    if data_bytes>=2_000_000_000:needed=False
    policy={"interval_minutes":interval,"reason":reason,"budget":budget,"checked_at":now.isoformat()}
    folder=Path("data/health");folder.mkdir(parents=True,exist_ok=True)
    (folder/"cadence.json").write_text(json.dumps(policy,ensure_ascii=False,indent=2),encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as file:
        file.write(f"due={str(needed).lower()}\nlast_snapshot={last}\nslot={target.isoformat()}\n")
    print(json.dumps({**policy,"due":needed,"last_snapshot":last},ensure_ascii=False))

if __name__=="__main__":main()
