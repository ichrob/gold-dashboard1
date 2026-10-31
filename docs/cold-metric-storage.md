# Private metric payload storage

Only `bob_metric_checks.payload` is eligible. Keys, version, scope, bar time and
check time remain in PostgreSQL so producer replays stay deduplicated. Original
JSON values are preserved in private, immutable, checksum-addressed Drive
chunks. `metric_quality.report` and `cold_metrics.get` resolve the original
values before calculation. Missing/corrupt chunks fail explicitly; they do not
produce empty or apparently complete reports. The existing report window stays
30 days, while exact-key historical reads have no age cutoff.

The previous 30-day metric deletion hook is now a no-op. Disabling the writer
does not restore deletion. Full evidence snapshots also include the cold batch
ledger and inline payload references; restoring such a snapshot requires
retaining its referenced Drive chunks. Never remove those files as redundant
daily backups.

## Rollout

1. Deploy the reader to both existing services and pass PostgreSQL integration
   tests (including unchanged report results, restart reads, corruption,
   concurrent update and transaction rollback).
2. Only then set `BOB_COLD_METRIC_ENABLED=1` on the push service. Leave it unset
   on the web service. Existing encrypted Drive credentials/folder are reused.
3. The first run starts 240 seconds after process start, then hourly. It skips
   while the existing local archive worker reports a running export.
4. Each run moves at most eight batches of 500 rows, with 2 MiB raw JSON per
   batch. It keeps the most recent 24 hours hot, ignores individual JSON values
   >=64 KiB, and selects payloads occupying more than 512 PostgreSQL bytes.
   Source transactions never span network I/O. Only matching original values
   are replaced, and every replacement is read back before commit.
5. Observe `BOB_COLD_METRICS` logs and `storage.coldMetrics` aggregate receipts.
   JSON byte reduction is not disk space freed. Ordinary VACUUM reuses dead-row
   space; it does not promise a physical database shrink.

## Stop / recovery

Unset or set `BOB_COLD_METRIC_ENABLED=0` to stop future moves. Keep this reader
version (or a compatible newer version) deployed: rolling back to a version
without pointer resolution would make archived metric reports unreadable.
Do not delete batch files, change their contents, or revoke Drive access while
payload references remain. The ledger and each row pointer contain file and
SHA-256 identities; no credentials are stored in those records. A failed upload,
download, comparison or transaction preserves source values. An uploaded but
unreferenced chunk after a failure is intentionally retained for investigation.
