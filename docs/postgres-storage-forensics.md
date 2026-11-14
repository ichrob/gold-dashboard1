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


## Short-horizon weekend growth attribution · 1 Nov 2026

The already-saved `bob_storage_samples` half-hour slots now also support
independent 2-hour and 6-hour **read-only** comparisons, using the nearest
existing baseline within 30 minutes of the requested duration. These
shorter windows complement, but do not replace, the exact 24-hour
insert/update/delete counter comparison.

The new `storageForensics.recentWindows` report includes the actual
snapshot slots and elapsed seconds, current minus baseline
`pg_database_size`, the sum of changes in relations present with valid
sizes at both snapshots, and the largest positive and negative allocated
relation-size deltas. Up to 12 fixed-format public `bob_*` table names
are shown in each direction. Private, unusually long or unsafe catalog
identifiers are never output. Newly created, removed or invalid relations
are counted as **not comparable**, not treated as zero-size and not
silently presented as saved disk.

The derived relation and database deltas can differ because not all
database objects are in the tracked catalog or are directly comparable.
They exclude physical Render WAL/volume observations. The comparison
**does not** measure WAL, filesystem free bytes, bloat, logical tuple
insert/update count, or the effect of a particular change. A missing
2h/6h baseline is `needs-snapshots`; it must not be extrapolated from
the oldest available measurement. No new database tables, scheduled
queries, credentials, retention changes, or writes to historical
market/simulation/product evidence are required.

This resolves an attribution gap observed on Sunday: the independent
Render volume moved from about 669.85 MB to 674.85 MB even though
the *largest* three visible relations had unchanged allocation. The
short-horizon view is intended to isolate which of the smaller
relations grew during that same recent period before authorizing any
lossless writer adjustment or offline physical maintenance. It does
not itself reclaim volume space.


### Optional PostgreSQL WAL-directory allocation check

The forensic report also attempts one read-only, one-second-bounded
aggregate `SELECT count(*),sum(size) FROM pg_ls_waldir()` against the
current PostgreSQL instance. File names, paths, archive receipts and WAL
contents are never returned. Managed Render roles may lack permission;
then `walDirectory.status=not-observed`, without breaking the main
storage report or claiming zero WAL.

An observed `allocatedFileBytes` value measures current files in the
`pg_wal` directory, including reusable or preallocated segments. It is
**not** measured physical Render free space, permission to delete WAL,
or a prediction that `CHECKPOINT` or `VACUUM` will reduce it. The
independent Render volume reading remains the only provider-level
physical-usage observation. The current approximately 110 MB difference
between `pg_database_size` and Render volume is not automatically all
WAL: temporary data, other database/system files and accounting scope
can contribute. No WAL recycling, checkpoint, shell command or SQL
maintenance is performed by the diagnostic.

## Decision-audit routine space reuse: manual opt-in (14 November 2026)

The existing hourly `storage_maintenance.run_once()` continues to vacuum **only** its
original four fixed tables. The large `bob_decision_audit` relation is now permitted
**only** through an explicit `run_once(target_table='bob_decision_audit', manual_decision_audit=True)` call
from an already authorized operator environment. Any attempt to target this table
without that additional literal boolean is rejected before opening a connection,
including attempts made through existing weekend-tail maintenance paths. This is an operator capability,
**not** an auto-start job, deploy, new service, cloud credential, or user endpoint.

The manual attempt requires the existing exclusive advisory lock, dedicated
autocommit connection, metadata-estimated dead tuples, and six-hour separation
from previous manual and automatic vacuum. It uses
`VACUUM (SKIP_LOCKED, TRUNCATE FALSE, PARALLEL 0) ONLY public.bob_decision_audit`,
with short lock wait and bounded statement timeout. There is **no** `FULL`,
`REINDEX`, `CLUSTER`, table rewrite, manual deletion, maintenance tail
truncation, retention-policy change, or new hourly work.

Operator must first check live load, current backups, disk/WAL headroom, and
competing jobs before explicitly choosing a maintenance window. Do not infer
reclaimable pages from `n_dead_tup`; after a completed command, compare
independently observed provider volume before/after and PostgreSQL relation
allocation/index stats, with non-savings reported as unknown/zero rather
than inventing freed bytes. Normal vacuum may allow **reuse** without reducing
files visible in Render disk measurements. Keeping the PR unmerged leaves the
production database entirely unchanged.

## Persisted weekend one-shot outcome (read-only addition)

The old `already-claimed` worker result only proves that a persistent claim
exists. It cannot distinguish success, deferral, a failed command or a
process interruption. The private storage health report now includes a
bounded `tailReclaimReceipt` projection for **only the currently configured
one-shot claim ID**. The underlying read uses catalog existence checking,
a 750-ms local statement timeout and one fixed parameterized row lookup.
It does not enumerate claim IDs, run a VACUUM, create tables, access
original market/product evidence, or clear consumed claims. If the
configuration is absent or the record is unavailable, it reports an
explicit unknown/disabled state.

The private projection exposes only an allowlisted table name, fixed
terminal/running state, update time and an optional decline in PostgreSQL
relation allocation **if** the command completed. It always reports
`diskBytesFreed=null`: a recorded completed command or relation allocation
change is not independent proof of Render provider-level disk savings.
This new observability requires separate review and deployment of this
draft PR; it does not retroactively prove the November 14 attempt.
