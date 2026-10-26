"""One shared Minsk daytime policy for collection and watchdog."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MINSK = ZoneInfo("Europe/Minsk")
UTC = timezone.utc


def slots(day, interval=60):
    if interval not in (30, 60):
        raise ValueError("Only free hourly/half-hourly stages are supported")
    start = datetime.combine(day, datetime.min.time(), MINSK).replace(hour=7, minute=10)
    return [start + timedelta(minutes=n) for n in range(0, 15 * 60, interval)]


def expected_slot(now, interval=60, grace=0):
    local = now.astimezone(MINSK)
    candidates = slots(local.date() - timedelta(days=1), interval) + slots(local.date(), interval)
    return max(t for t in candidates if t + timedelta(minutes=grace) <= local)


def is_daytime(now):
    return 7 <= now.astimezone(MINSK).hour < 22


def due(last, now, interval=60):
    if not is_daytime(now):
        return False
    target = expected_slot(now, interval)
    if target.date() != now.astimezone(MINSK).date():
        return False
    if not last:
        return True
    previous = datetime.fromisoformat(last.replace("Z", "+00:00"))
    return previous < target
