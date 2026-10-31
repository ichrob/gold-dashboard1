# Private analysis payload tier

Only `bob_diagnostic_history` rows with stage `analysis`, recorded more than six
hours ago, and stored payload size above 512 bytes are eligible. Other stages
and recent rows stay untouched. This does not change journal retention, source
recovery, push receipts, simulations or order behavior.

The private Drive store and bounded gzip/checksum codec are shared with cold
metrics, but batch receipts and row-id lookup live in `bob_cold_analysis_batches`.
A chunk has the existing five-item row envelope: id, stage, observation clock,
build, original payload. Its identity is checked before returning any payload.
Original JSON is uploaded, downloaded with bounded expansion, SHA-256 verified
and compared before replacing matching SQL payloads. Compare-and-swap includes
original JSON, id, stage, observation clock and nullable build; concurrent edits
are preserved. Pointer and ledger writes commit atomically. Failed uploads,
checks or transactions retain the source. Unreferenced files are not auto-deleted.

The SQL projection retains the exact `timeframe` and `result.ready`,
`result.priceFresh`, `result.dataAt` fields used by paper-gap analysis. Other
readers must call `cold_analysis.resolve` before using complete analysis payloads.
The diagnostic report does so. A mismatched projection, identity, missing index,
missing file or checksum mismatch raises an explicit incomplete-report error.
`cold_analysis.get(conn, id)` also resolves archived payloads after normal journal
retention, using the receipt's row-id list. This returns the original analysis
payload, not a reconstruction of every deleted journal column. Daily snapshots
remain the full-row recovery path. Never delete referenced chunks as duplicate
backups. Evidence snapshots include the new batch ledger.

Deploy compatible readers to both services before setting
`BOB_COLD_ANALYSIS_ENABLED=1` on the push service only. The default is disabled.
The first pass waits 300 seconds after startup, then runs hourly. It skips an
active archive run and holds a dedicated advisory lock. Each pass has at most
64 chunks, with a 120-second elapsed check between chunks; each chunk obeys the
existing 2 MiB raw/500-row limits. No source transaction spans Drive I/O. Existing
SQL connection statement/lock timeouts and Drive client limits remain in force.

Inspect `storage.coldAnalysis` and `BOB_COLD_ANALYSIS` logs for verified counts.
JSON-byte savings are not physical disk savings. Stop new writes by clearing the
flag, but retain compatible readers, credentials, receipts and chunks. A later
separately controlled compaction may reclaim database files after the old tuples
become removable; this writer never runs FULL or claims freed disk bytes.
