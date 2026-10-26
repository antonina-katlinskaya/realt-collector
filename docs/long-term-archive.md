# Long-term archive — verified 26 October 2026

Complete new Realt snapshots are stored as immutable ZIP assets in weekly GitHub Releases, with original compressed RAW bytes, all current CSV rows, and SHA-256 manifests. Existing legacy RAW files and daily archives remain preserved. The working CSV retains the latest two snapshots for analytics.

A successful snapshot is committed only after the uploaded asset is downloaded again and its checksum and contents pass verification. Upload/readback failure stops completion; there is no local-only fallback. Monthly references are kept in data/archive.

## Live evidence
- Collector run: https://github.com/antonina-katlinskaya/realt-collector/actions/runs/40360066141 — success, including 10 tests, archive bootstrap, new full collection, verification and analytics.
- New snapshot: 2026-10-26T16:32:36Z; completed 16:39:38Z (19:39 Moscow/Minsk), 1519 listings, 421.574 seconds.
- Asset: snapshot-2026-10-26_16-32-36-98dfd33979a2.zip, 834298 bytes, SHA-256 98dfd33979a2f811e6cbaccef73f83cc16a91b17a4bcbd4a4ee41f30bd8eea28.
- Release: https://github.com/antonina-katlinskaya/realt-collector/releases/tag/realt-data-2026-W44
- Reader run: https://github.com/antonina-katlinskaya/kufar-radar/actions/runs/40361274242 — success, 45 tests, new snapshot processed at 16:40:10Z, zero pending notifications.
- Subsequent run https://github.com/antonina-katlinskaya/kufar-radar/actions/runs/40363565317 correctly skipped the unchanged source and sent no duplicates.

No additional D1/Worker storage or paid service was enabled. This is archival storage, not a guarantee that GitHub cannot change its terms. Current documented asset limits: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases . Code protective ceilings are 900 assets per weekly release and 100 MB per packet; the planned maximum 30 snapshots/day gives 210 assets/week. Full-day schedule/resource trial remains unfinished.

Nataliya Sidorova research was cancelled and removed from the Realt research/policy helpers. Kufar rules, recipients and publisher were not modified by this archival change.
