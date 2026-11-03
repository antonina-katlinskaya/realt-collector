"""Independent checks for complete, corroborated Realt observations.

Never converts a partial collection into a valid snapshot.
"""
from datetime import datetime, timedelta, timezone
from math import ceil


def verify_pages(pages, agencies, page_size):
    """Require complete source pagination without changing the original queries."""
    summary = {}
    for agency in agencies:
        observations = [p for p in pages if p["agency"] == agency]
        if not observations:
            raise RuntimeError("Missing source list pages for an agency")
        first = [p for p in observations if p["page"] == 1]
        if len(first) != 1:
            raise RuntimeError("Missing or repeated first source page")
        initial_total = first[0]["total"]
        if initial_total <= 0:
            raise RuntimeError("Empty agency search result requires review")
        expected = ceil(initial_total / page_size)
        numbers = [p["page"] for p in observations]
        if len(numbers) != expected or set(numbers) != set(range(1, expected + 1)):
            raise RuntimeError("Incomplete or repeated source pages")
        actual = sum(p["returned"] for p in observations)
        # Allow modest live changes during pagination, but not an incomplete search.
        tolerance = max(5, ceil(initial_total * 0.02))
        if abs(actual - initial_total) > tolerance:
            raise RuntimeError("Source pagination count differs materially from totalCount")
        if any(p["returned"] > page_size or p["returned"] < 0 for p in observations):
            raise RuntimeError("Invalid source page size")
        summary[agency] = {"reported": initial_total, "retrieved": actual, "pages": expected}
    return summary


def assess_drop(previous, count, uuids, observed_at, candidate=None):
    """Two independent consistent full scans are required to accept a major drop."""
    baseline_count = int(previous.get("rows") or 0)
    baseline_at = previous.get("snapshot_at")
    unique = set(uuids)
    if len(unique) != count or not count:
        raise RuntimeError("Missing or duplicate source UUIDs")
    if not baseline_count or count >= baseline_count * 0.8:
        return True, None, "normal"
    next_candidate = {
        "reference_snapshot_at": baseline_at,
        "rows": count,
        "observed_at": observed_at,
        "uuids": sorted(unique),
    }
    if not candidate or candidate.get("reference_snapshot_at") != baseline_at:
        return False, next_candidate, "first independent drop observation"
    try:
        before = datetime.fromisoformat(candidate["observed_at"].replace("Z", "+00:00"))
        now = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        delta = now - before
        old_ids = set(candidate["uuids"])
        same_count = 0.85 <= count / int(candidate["rows"]) <= 1.15
        overlap = len(old_ids & unique) / min(len(old_ids), len(unique))
        if (timedelta(minutes=20) <= delta <= timedelta(hours=48)
                and same_count and overlap >= 0.85):
            return True, None, "major drop independently corroborated"
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    return False, next_candidate, "unconfirmed source count drop"
