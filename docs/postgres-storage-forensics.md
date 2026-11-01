# PostgreSQL storage forensics: allocation, TOAST and 24-hour writes

## Verified read-only baseline · 1 November 2026, 08:13 UTC

This baseline comes from Bob's authenticated **private** storage report. It is
not a new SQL direct connection, pgstattuple scan, page inspection, nor evidence
of actual reclaimable disk space. Primary production Postgres external IP
allowlist remains empty.

- Logical PostgreSQL database: **558,634,687 B**.
- Independently observed Render DB volume: **668,655,600 B** of the unchanged
  **1,000,000,000 B** allocation.
- `bob_decision_audit`: 139,796,480 B total; TOAST 122,814,464 B,
  heap 9,371,648 B, indexes 7,577,600 B.
- `bob_diagnostic_history`: 136,962,048 B total; heap 109,404,160 B,
  indexes 27,205,632 B.
- `bob_improvement_observations`: 66,838,528 B total; TOAST 52,912,128 B,
  heap 11,157,504 B.
- Prior manually verified, strictly bounded weekend tail VACUUM attempts:
  `bob_diagnostic_history` and `bob_improvement_observations` both returned
  `observedRelationBytesDecrease=0`. No physical Render space savings claimed.

Across the existing fixed snapshots from slot 1793179800 to 1793520000
(**340,200 seconds = 94.5 hours**), allocation changed by:

| Fixed table | Relation bytes delta | Average allocated MB/day over that exact span |
| --- | ---: | ---: |
| bob_improvement_observations | +27,525,120 | +6.99 |
| bob_diagnostic_history | +18,931,712 | +4.81 |
| bob_decision_audit | +14,360,576 | +3.65 |
| bob_candle_evidence | +9,371,648 | +2.38 |
| bob_decision_outcomes | +6,914,048 | +1.76 |
| bob_metric_checks | -28,844,032 | -7.33 |

These are **allocated-size deltas**, not new user data, hourly write
throughput, actual WAL volume or reclaimed/reclaimable page bytes. Dead row
statistics cannot prove free pages. A negative allocated-size delta must
not be used to claim an equivalent direct decrease in the physical Render
volume.

## Implemented diagnostic

The new `storage_forensics` attaches to the existing authenticated
`storage-health`/private diagnostic path, with a fixed allowlist of ten
table names, without raw rows, client IDs, ISINs, quotes, source URLs or
credentials. Current metadata reads include heap, indexes, TOAST,
free-space-map and visibility-map allocation, and only catalog-based row
estimates. **FSM/VM file sizes are not the number of free bytes.**

The already deployed half-hour `bob_storage_samples` slot stores an
additional bounded JSON object, `writer_stats`, containing only cumulative
`pg_stat_user_tables` inserted/updated/deleted/HOT-update counts for those
ten tables (maximum ten small records per slot). It reuses the existing
90-day telemetry retention, without any new history-table deletion or
appending an unbounded catalog. No original evidence table or original
product data is changed. Each snapshot has one fixed slot and the original
`ON CONFLICT DO NOTHING` behavior.

The daily analysis picks the **closest existing snapshot to 24 hours prior,
within 23–25 hours**, not the oldest historical snapshot, and publishes the
exact elapsed seconds and net allocated-size deltas. Only when both
snapshots contain valid nondecreasing cumulative counters will SQL tuple
operation deltas be reported. New installations must collect two counter
snapshots before these can be claimed. Counter resets, missing snapshots,
invalid numeric types and schema absences are explicit incomplete states.

No exhaustive full-table size scan, installed extension, `VACUUM FULL`,
`REINDEX`, `CLUSTER`, destructive SQL, product pointer creation or
paid database upgrade is authorized. A report remains **read-only**; only
the preexisting scheduled metadata snapshot process adds small bounded
aggregate counters. Missing observations must not imply zero writes.

## Decision gate before any physical rebuild

- Confirm distinct current daily growth versus SQL tuple modifications over
  a reliable 23–25-hour window, with no counter reset or missing data.
- Separate heap, TOAST and index allocations and inspect the dominant
  applications' write logic without shortening or replacing evidence.
- Assess whether changed paths create avoidable duplicate writes. Change
  only with exact original-identity/read-through and CI/PG regression.
- A physical rewrite requires an **independent safe scratch/WAL/lock budget,
  live traffic and rollback plan, complete evidence-and-reference restore
  proof**, a separate explicit maintenance authorization and a post-change
  measurement of Render physical volume. Mere relation allocation or
  n_dead_tup cannot substitute for these conditions.
- No automatic paid scaling, no open database allowlist, no account or
  trade permissions, and no claim of immediate free disk space.
