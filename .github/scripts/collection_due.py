"""Retry missed collection slots; manual and recovery-patch runs always collect."""
import csv
import datetime as dt
import os
from pathlib import Path

UTC = dt.timezone.utc
SLOT_HOURS_UTC = (6, 9, 12, 15, 18)


def latest_slot(now):
    today = now.astimezone(UTC).replace(hour=0, minute=17, second=0, microsecond=0)
    slots = [today + dt.timedelta(hours=hour) for hour in SLOT_HOURS_UTC]
    return max((slot for slot in slots if slot <= now),
               default=slots[-1] - dt.timedelta(days=1))


def latest_snapshot(path):
    if not Path(path).exists():
        return ""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return max((r["snapshot_at"] for r in csv.DictReader(f)
                    if r.get("uuid") and r.get("snapshot_at")), default="")


def collection_due(last, event, now):
    if event != "schedule" or not last:
        return True
    timestamp = dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
    return timestamp < latest_slot(now)


def main():
    now = dt.datetime.now(UTC)
    last = latest_snapshot("data/snapshots.csv")
    due = collection_due(last, os.environ.get("COLLECTION_EVENT", ""), now)
    message = f"Last snapshot: {last or 'none'}; expected slot: {latest_slot(now).isoformat()}; collect: {due}"
    print(message)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"due={str(due).lower()}\nlast_snapshot={last}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(message + "\n")


if __name__ == "__main__":
    main()
