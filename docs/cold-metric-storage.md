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

## Bounded tail reclamation

After each completed cold-worker pass, maintenance may truncate empty pages at
the end of `bob_metric_checks`, even if autovacuum ran recently. This is ordinary
VACUUM, not FULL: it never rewrites the table or removes live rows. The command
has a 10-second statement timeout and the dedicated connection retains its
1-second lock timeout. Busy locks or timeouts defer the work. Other tables retain
TRUNCATE FALSE and their existing six-hour cooldown. The local archive-running
guard and maintenance advisory lock still apply.

Logs record total relation bytes before and after a completed attempt. Their
decrease is an observed relation-size change, not total volume free space;
concurrent writes can affect it. Empty space within the table remains reusable
but cannot be released by tail truncation. No shrink is guaranteed.

## One-time physical compaction

`BOB_METRIC_COMPACTION_ONCE` is unset by default. An explicit JSON configuration
contains `id`, `observedAt` (Unix seconds), `freeBytes` (a conservative, externally
observed free-space lower bound, at most 200 MB), and `databaseBytes` at observation.
The observation expires after one hour, even across restarts. Never substitute
allocation minus logical database size for observed free space. The current
operator evidence is the 2026-10-31 08:45 Europe/Zurich Render Disk Usage graph
at about 75–76%; use 200 MB, below the approximately 240 MB shown as free.

The push service starts the one-shot task after 120 seconds. It requires a
verified backup with both restore/download proofs within 24 hours, skips a running
archive, and takes both maintenance/cold-writer advisory locks. A committed
attempt record prevents replay after success, failure, or interrupted execution.
No auto-retry or table deletion is performed. Ordinary hourly maintenance remains
separate and never uses FULL.

Only the metric table is allowed (maximum 120 MB). Rebuild its two valid indexes
one at a time when the observed budget exceeds three times the index size plus
50 MB. If either operation fails, stop. Then estimate the expanded live tuple and
current index footprint; FULL is allowed only if twice that estimate plus a 50 MB
reserve fits the remaining budget. Logical DB growth since observation reduces
the budget, but apparent shrink does not increase it. These conservative estimates
are not direct filesystem/WAL measurements. Each command has a 30-second statement
and 1-second lock timeout. REINDEX may pause writes; FULL blocks reads/writes while
it holds its exclusive lock. PostgreSQL rolls back an interrupted command.

`BOB_METRIC_COMPACTION` logs and `bob_metric_compaction_attempts.result` hold the
sanitized before/after relation size and outcome. This proves relation shrink,
not total volume free bytes. Clear the environment value after the attempt.

An explicitly configured `resumeFrom` may reference a previous persisted attempt
whose two indexes completed and whose FULL ended with QueryCanceled. Only that
verified case skips reindexing and gives FULL 90 seconds. All fresh-observation,
backup, budget, and single-attempt guards still apply. The operator must first
check that interrupted-rewrite files have been cleaned up and WAL is recycled;
do not blindly reuse old headroom. The 2026-10-31 08:02:59 and 08:07:59 UTC database
checkpoints reported 3 and 1 WAL files recycled respectively, zero files added.
No automated retry is introduced.
