"""Independent checks for complete, corroborated Realt observations.

Never converts a partial collection into a valid snapshot.
"""
from datetime import datetime, timedelta, timezone
from math import ceil
from collections import Counter


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
        # Frequent scheduler/fallback runs must not move the first observation
        # forward forever while waiting for the independent-scan interval.
        if timedelta(0) <= delta < timedelta(minutes=20) and same_count and overlap >= 0.85:
            return False, candidate, "waiting for independent drop confirmation"
        if (timedelta(minutes=20) <= delta <= timedelta(hours=48)
                and same_count and overlap >= 0.85):
            return True, None, "major drop independently corroborated"
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    return False, next_candidate, "unconfirmed source count drop"


def diagnose_uuid_integrity(objects, source_pages, source_file):
    """Describe rejected UUIDs without trusting or rewriting source rows.

    Keep only small, non-personal identifier/page samples in durable health data.
    No duplicate is removed and this report never authorizes a snapshot.
    """
    identifiers = [str(item.get("uuid") or "") for item in objects]
    counts = Counter(identifiers)
    duplicates = {uid: count for uid, count in counts.items() if uid and count > 1}
    affected = []
    for page in source_pages:
        bad_positions = []
        for position, item in enumerate(page.get("identifiers") or [], 1):
            uid = str(item.get("uuid") or "")
            if not uid or uid in duplicates:
                bad_positions.append({
                    "position": position,
                    "uuid": uid or None,
                    "code": str(item.get("code") or "") or None,
                })
        if bad_positions:
            affected.append({
                "agency": page.get("agency"),
                "page": page.get("page"),
                "source_total": page.get("total"),
                "anomaly_count": len(bad_positions),
                "examples": bad_positions[:12],
            })
    return {
        "status": "rejected",
        "reason": "Empty or duplicate source UUIDs",
        "source_file": source_file,
        "filtered_rows": len(identifiers),
        "missing_uuid_count": counts.get("", 0),
        "duplicate_uuid_count": len(duplicates),
        "duplicate_extra_rows": sum(total - 1 for total in duplicates.values()),
        "duplicate_samples": [
            {"uuid": uid, "occurrences": count}
            for uid, count in sorted(duplicates.items())
        ][:15],
        "source_pages_checked": len(source_pages),
        "affected_pages": affected[:20],
        "affected_pages_truncated": len(affected) > 20,
        "valid": bool(identifiers) and not counts.get("", 0) and not duplicates,
    }

