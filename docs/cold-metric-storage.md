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

1. Set `BOB_COLD_METRIC_ENABLED=0` on the writer before upgrading reference
   formats. Deploy the reader to both existing services and pass PostgreSQL integration
   tests (including unchanged report results, restart reads, corruption,
   concurrent update and transaction rollback).
2. Only then set `BOB_COLD_METRIC_ENABLED=1` on the push service. Leave it unset
   on the web service. Existing encrypted Drive credentials/folder are reused.
3. The first run starts 240 seconds after process start, then hourly. It skips
   while the existing local archive worker reports a running export.
4. Each run moves at most 32 batches of 500 rows, with 2 MiB raw JSON per
   batch. It keeps the most recent 24 hours hot, ignores individual JSON values
   >=64 KiB, and selects payloads occupying more than 192 PostgreSQL bytes.
   Source transactions never span network I/O. Only matching original values
   are replaced, and every replacement is read back before commit.
5. Observe `BOB_COLD_METRICS` logs and `storage.coldMetrics` aggregate receipts.
   JSON byte reduction is not disk space freed. Ordinary VACUUM reuses dead-row
   space; it does not promise a physical database shrink.

V1 references remain readable. V2 stores only a random batch key and row index
per payload. The immutable batch ledger holds the file ID and SHA-256 once per
batch. Every V2 read compares the original version, scope, bar time and check
time to the retained SQL columns, so a pointer cannot silently select a different
row. Reference lookup and chunk caches are bounded. Ledger insertion and pointer
updates commit atomically; neither cache is required after a process restart.

## Stop / recovery

Unset or set `BOB_COLD_METRIC_ENABLED=0` to stop future moves. Keep this reader
version (or a compatible newer version) deployed: rolling back to a version
without pointer resolution would make archived metric reports unreadable.
Do not delete batch files, change their contents, or revoke Drive access while
payload references remain. The ledger and each row pointer contain file and
SHA-256 identities; no credentials are stored in those records. A failed upload,
download, comparison or transaction preserves source values. An uploaded but
unreferenced chunk after a failure is intentionally retained for investigation.
