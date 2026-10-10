"""Check a missed Realt collection slot and notify Telegram exactly once."""
import csv
import datetime as dt
import os
import pathlib
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
HOURS = (6, 9, 12, 15, 18)
GRACE = dt.timedelta(minutes=45)
STATE = pathlib.Path(".github/state/telegram_alerted_slot.txt")
SNAPSHOTS = pathlib.Path("data/snapshots.csv")

def last_due_slot(now):
    day = now.date()
    for days_back in range(2):
        date = day - dt.timedelta(days=days_back)
        for hour in reversed(HOURS):
            slot = dt.datetime.combine(date, dt.time(hour, 17), tzinfo=UTC)
            if slot + GRACE <= now:
                return slot
    raise RuntimeError("No due collection slot")

def latest_snapshot():
    with SNAPSHOTS.open(encoding="utf-8-sig", newline="") as file:
        return max((row["snapshot_at"] for row in csv.DictReader(file)
                    if row.get("uuid") and row.get("snapshot_at")), default="")

def main():
    now = dt.datetime.now(UTC)
    slot = last_due_slot(now)
    latest = latest_snapshot()
    print(f"Now: {now.isoformat()}; due slot: {slot.isoformat()}; snapshot: {latest}")
    if latest and dt.datetime.fromisoformat(latest.replace("Z", "+00:00")) >= slot:
        print("OK: collection is up to date for the due slot.")
        return
    slot_text = slot.strftime("%Y-%m-%dT%H:%MZ")
    if STATE.exists() and STATE.read_text(encoding="utf-8").strip() == slot_text:
        print("Alert already sent for this slot.")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("::warning::Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub Actions secrets to enable alerts.")
        return
    slot_local = (slot + dt.timedelta(hours=3)).strftime("%d.%m.%Y %H:%M")
    message = ("⚠️ Realt Collector: пропущено обновление!\n"
               f"Контрольная точка: {slot_local} (Минск).\n"
               f"Последний снимок: {latest or 'отсутствует'}.\n"
               "Проверьте GitHub Actions: https://github.com/antonina-katlinskaya/realt-collector/actions")
    data = urllib.parse.urlencode({"chat_id": chat, "text": message}).encode()
    with urllib.request.urlopen(
        urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data),
        timeout=25,
    ) as response:
        if response.status != 200:
            raise RuntimeError("Telegram returned non-200 status")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(slot_text + "\n", encoding="utf-8")
    print("Telegram alert sent for", slot_text)

if __name__ == "__main__":
    main()
