"""Check a missed Realt collection slot and notify Telegram exactly once."""
import csv
import datetime as dt
import os
import pathlib
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from pipeline.schedule import expected_slot
import json
OWNER_ID = "352252956"
GRACE = dt.timedelta(minutes=25)
STATE = pathlib.Path(".github/state/telegram_alerted_slot.txt")
SNAPSHOTS = pathlib.Path("data/snapshots.csv")
OWNER_MONITOR_REPOSITORY = 'antonina-katlinskaya/kufar-radar'

def verify_owner_health_monitor(now):
    """Reuse the existing verified owner bot without copying its secrets."""
    url='https://api.github.com/repos/'+OWNER_MONITOR_REPOSITORY+'/actions/workflows/realt-scheduled-owner.yml/runs?per_page=5'
    headers={'Accept':'application/vnd.github+json','User-Agent':'RealtCollectorWatchdog/1.0'}
    if os.environ.get('GITHUB_TOKEN'):headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=25) as response:
        runs=json.load(response).get('workflow_runs',[])
    completed=[run for run in runs if run.get('status')=='completed']
    if not completed:raise RuntimeError('Owner health monitor has no completed check')
    latest=completed[0]
    checked=dt.datetime.fromisoformat(str(latest['updated_at']).replace('Z','+00:00'))
    if latest.get('conclusion')!='success' or not dt.timedelta(minutes=-5)<=now-checked<=dt.timedelta(minutes=40):
        raise RuntimeError('Owner health monitor is not recently healthy; notification route unverified')
    link=str(latest.get('html_url') or '')
    if not link.startswith('https://github.com/'+OWNER_MONITOR_REPOSITORY+'/actions/runs/'):
        raise RuntimeError('Unexpected owner health monitor identity')
    return link

def last_due_slot(now):
    policy = pathlib.Path("data/health/cadence.json")
    interval = json.loads(policy.read_text()).get("interval_minutes", 60) if policy.exists() else 60
    return expected_slot(now, interval, grace=25).astimezone(UTC)


def latest_snapshot():
    marker = pathlib.Path("data/collection_state.json")
    if marker.exists():
        state = json.loads(marker.read_text())
        if state.get("complete") is not True:
            raise RuntimeError("Incomplete collection marker")
        return state["snapshot_at"]
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
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or chat != OWNER_ID:
        if os.environ.get('REALT_ALERT_ROUTE')=='owner-health':
            link=verify_owner_health_monitor(now)
            print(json.dumps({'source_stale':True,'notification_route':'verified-owner-health',
                              'monitor_run':link,'direct_telegram_sent':False}))
            return
        # A stale snapshot without a delivered warning is a FAILED monitoring check.
        # Never leak token or recipient data into public Actions logs.
        print("::error::Realt watchdog cannot alert owner: Telegram secrets missing or recipient mismatch.")
        raise RuntimeError("Realt collection alert not delivered; Telegram watchdog configuration invalid")
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

