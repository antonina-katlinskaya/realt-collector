"""One shared Minsk collection window with a final midnight snapshot."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MINSK = ZoneInfo("Europe/Minsk")
UTC = timezone.utc


def slots(day, interval=60):
    if interval not in (30, 60):
        raise ValueError("Only free hourly/half-hourly stages are supported")
    start = datetime.combine(day, datetime.min.time(), MINSK).replace(hour=7, minute=10)
    # The ordinary cadence runs until 23:40 (30-minute mode) or 23:10 (hourly).
    ordinary = [start + timedelta(minutes=n) for n in range(0, 17 * 60, interval)]
    # Explicit final checkpoint at 00:00 of the next Minsk day.
    midnight = datetime.combine(day + timedelta(days=1), datetime.min.time(), MINSK)
    return ordinary + [midnight]


def expected_slot(now, interval=60, grace=0):
    local = now.astimezone(MINSK)
    candidates = slots(local.date() - timedelta(days=1), interval) + slots(local.date(), interval)
    return max(t for t in candidates if t + timedelta(minutes=grace) <= local)


def is_daytime(now):
    local = now.astimezone(MINSK)
    # Allow a delayed scheduled 00:00 pass within the first hour after midnight.
    return local.hour >= 7 or local.hour == 0


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
