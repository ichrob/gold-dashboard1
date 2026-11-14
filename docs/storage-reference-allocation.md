# #1329: Reference allocation follow-up, 12 November 2026

PR #1616's completed 96-row PG18 PGLZ/LZ4 comparison returned 90,112
bytes for each layout. Do not repeat it or infer a live LZ4 advantage.
This separate test extends the existing `diagnostic_reference_shadow`
model with actual temporary relation allocation, including both tables,
their primary keys and the referencing digest index. It does not change
any production writer, reader, maintenance task, schema or schedule.

## Observed growth, not estimated savings

Bob's read-only storage response observed at 2026-11-12 13:32:49 UTC:

| Relation | Total bytes | Heap | Indexes | TOAST |
|---|---:|---:|---:|---:|
| bob_diagnostic_history | 217161728 | 93970432 | 56303616 | 66838528 |
| bob_decision_audit | 186810368 | 13975552 | 11509760 | 161292288 |
| bob_metric_checks | 92028928 | 65355776 | 26624000 | 8192 |

Saved daily slots show +19,111,936, +5,136,384 and +10,698,752 bytes
respectively. Insert/delete counters are explicitly reset-unverified;
do not call their differences exact throughput. Diagnostic estimates
are 93,114 live / 8,500 dead rows; dead-row estimates do not prove
reclaimable bloat. Existing bounded retention must remain unchanged.

Input sample: 106 events, 21 payloads, zero identical full contexts.
Payload-only logical difference is 18,430 bytes; reference/index costs
were not included. Complete events cannot be discarded as duplicates.
Decision audit is predominantly TOAST; repeated product subtrees merit
measurement using the existing product-reference machinery. Metrics are
predominantly heap/index, so changing TOAST compression alone does not
address most current allocation. `metric_quality` already uses a primary
key (version, scope, bar_at) and ON CONFLICT, preserving first observations.
Its checkedAt, source hashes and market values cannot be rounded/removed
merely to obtain identical contents. Its no-delete compatibility hook
and cold-readthrough protection remain intact.

## Additional isolated experiment

The existing CI PostgreSQL 18 service runs a fixed synthetic matrix:
32/128/256 events, one repeated versus all unique payloads, small versus
large payloads. Both designs keep every event identity and timestamp.
Digest matches are checked against full canonical content. Joined
readback must exactly reconstruct every event. Negative differences are
valid findings; tests do not require shared storage to win.

Only localhost `bob_auth_test` DSNs without overrides are accepted before
connection, then server database/version are checked. Each case creates
TEMP tables under a savepoint and rolls back, with 10s statement/1s lock
timeouts. No original data input, production connection, external access,
new service or additional workflow is introduced. Existing CI discovery
runs the test; Risiko and CodeQL path filters include it. Aggregate output
uses `BOB_REFERENCE_PG18`; no payloads, digests or credentials are printed.

This is a bounded model, not a replica of all production indexes, archive
readers or concurrent writers. PostgreSQL allocation differs from Render
volume use. CPU/RAM, long-run cleanup, foreign-key contention, archived
reader compatibility and original-sample representativeness remain
required before a future writer proposal. No productive migration follows
automatically from a positive synthetic result.

## Access and acceptance boundaries

Provider volume projected by Bob: 1,011,367,940 / 5,000,000,000 bytes at
13:32 UTC, database size 900,716,223 bytes in its saved sample. This is
not a maintenance-bound before/after pair. Physical savings: **not proven**.
The persisted archive receipt is from 00:45 UTC, no longer fresh for new
offload; deletionPermitted=false. Termux session is expired/offline.
Direct Render inspection awaits confirmed workspace selection. No external
allowlist is opened and no maintenance/archive/restore cycle is started.

Original comparison needs an authorized internal path to the existing
isolated secured restore, and fresh scope/restore checks. Keep #1616 draft
and coordinate this follow-up in #1329. No merge/deploy before complete
CI, Risiko, CodeQL and safety evidence; production feature acceptance and
physical savings cannot be claimed from these tests.


## Follow-up 14 November 2026: prevent unproven metric pruning

The newest independent Bob read-only storage sample around 07:22 UTC shows
1,075,220,500 of 5,000,000,000 physical provider bytes (21.50%), while
the logical database is 964,318,911 B. Largest allocated relations:
`bob_diagnostic_history` 214,401,024 B,
`bob_decision_audit` 199,147,520 B, and
`bob_metric_checks` 109,518,848 B.
These three allocations are not confirmed bloat. Four completed comparison
rows were offloaded with verified readthrough (18,308 **logical JSON** bytes
reduced), not a physical disk-release proof.

There is a *candidate* for avoiding future needless metric payload repetition.
`metric_quality.py` uses an immutable `(version,scope,bar_at)` key. In
particular, product checks with no verified source clock use a minute-bucket
identity, so their missing-evidence status may recur frequently. No live
full-day per-scope write breakdown is yet established; never infer
such a breakdown from old, truncated 128-row original samples or from
synthetic PG18 shared-payload benchmarks. Missing-source checks and original
event timestamps remain scientifically relevant. Do not suppress or combine
them before verified lossless reconstruction and study-consumer acceptance.

`metric_growth_scope_probe.py` is a **separately operator-enabled,
read-only, non-scheduled** query against the existing internal database.
It selects at most the latest 256 rows within 24 hours via the existing
`checked_at` index, under short statement/lock timeouts and server-enforced
read-only transactions. The SQL itself returns only one of five fixed scope
categories, two MD5s, compressed JSONB column size and three booleans.
**No** JSON body, real clock, full scope/ISIN, hash, source URL, credential or
private trading data leaves the DB in the result. The script emits only
counts and sizes; the digest without `checkedAt` indicates a possible
repeatable *content* component, never event identity or deletion authority.
A full 256-row sample is explicitly marked truncated. It is not a day total,
relation/index allocation, WAL, verified bloat or provider disk savings.

For a **single authorized internal read-only operator session only**:
`BOB_METRIC_SCOPE_PROBE_ONCE=1 python metric_growth_scope_probe.py`
using the existing runtime `DATABASE_URL` (never print it or transfer it to
GitHub). This is a documentation example, **not a request to set a new
persistent Render variable or restart a service**. Without the flag, the
program refuses before opening SQL. The ordinary GitHub CI covers only pure
mocked tests and never accesses Bob's production database.

Apply an actual optimization only after independent current per-scope evidence
demonstrates unused content, unchanged original event times, full per-reader
reconstruction, proper secure archive/recovery binding, bounded writes and
adequate WAL/scratch/rollback. Keep the two current storage PRs as Draft.
No new archive claim, production migration, DELETE, VACUUM FULL, deployment,
new service or real order is justified by this probe.
