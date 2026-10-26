# Realt Collector: hourly trial, 26 October 2026

The collector runs entirely on standard GitHub-hosted runners in this public repository. No Cloudflare D1 or Workers credentials are required. The original collector.py, queries.py and config.py queries, filters and pauses are unchanged.

## Schedule and promotion

07:10 through 21:10 Europe/Minsk: 15 full hourly slots. The cron wakes at :10 and :40, but the shared freshness gate skips already satisfied slots and all night work. After at least 24 hours and 15 successful measured collections, the gate allows 30 daily slots through 21:40. It requires the last 15 runs to succeed without 403/429, each collection at most 20 minutes, and working data below 2 GB. Any failed condition retains/reverts to hourly. Source-wide 403/429 cooldown: 60 minutes; at most two attempts per slot. No paid services are enabled.

The concurrency group prevents parallel collections. Actual object response receipt times are written to raw snapshots and CSV. Failed source responses/GraphQL errors and suspicious >20% count collapse do not replace the last complete snapshot. On failure only health diagnostics are committed. The marker is committed with a verified nonempty snapshot.

## Archive

Every CSV history row is retained in lossless daily gzip partitions under data/snapshots/. data/snapshots.csv becomes a compatibility window of 32 recent distinct snapshots. Existing raw originals remain; new raw snapshots are gzip-compressed with verified roundtrip. Analytics and the dashboard use this recent window, not the full lifetime history. At 2 GB of working data, collection stops for archive maintenance; no history is automatically deleted. This is a finite storage budget, not a promise of unlimited permanent storage.

## Observations before deployment

19–25 October: most days had 3–4 inferred full collections despite five nominal daily slots; schedule wakeups can be delayed or omitted by GitHub. The measured 26 October run 40326081859 collected for 644 seconds (12:54:11–13:04:55 UTC). Existing raw: 63 files, 691,287,179 bytes uncompressed; snapshots.csv: 57,978,052 bytes. These measurements justify a trial, not immediate 30-minute activation.

GitHub schedule is best effort. The watchdog uses the same dynamically chosen slots and 25-minute grace, and can itself be delayed by GitHub. No hard maximum alert latency is guaranteed.
