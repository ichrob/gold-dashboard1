# Exact heap + TOAST bloat probe with a rolled-back extension

This is a **separately opt-in**, one-time diagnostic for issue #1231.
Bob has **1 GB** of Render PostgreSQL storage; measured table allocation
does not prove how many bytes pg_repack would return to the provider.
The initial WAL survey showed 1,272,025 bytes generated in 15.5 seconds;
that is traffic during one window, **not** physical WAL reservation.

## How it operates

When and only when `BOB_BLOAT_PROBE_ONCE=1` is set on the existing Push
service, a separate daemon checks the current Render provider volume
(under 750 MB, metric fresh within 300 seconds) and that the existing
archiver is not running. It then opens one short, non-autocommit
PostgreSQL transaction on the fixed table
`public.bob_improvement_observations`, with 4-second statement timeout,
250-ms lock timeout, and 11-second idle-transaction timeout.

The transaction checks table size (less than 100 MB) and whether
`pgstattuple` is already installed. If not, it attempts PostgreSQL's
transactional `CREATE EXTENSION pgstattuple WITH SCHEMA public`, then
calls `pgstattuple_approx` on **exactly** the main table and its TOAST
relation. Results are aggregate tuple/free-space counters only.
**The transaction is unconditionally rolled back and the connection
closed.** A separate read-only connection confirms the extension's
installed/uninstalled state is unchanged. If the managed Postgres role
cannot create or execute it, or a scan times out, the probe returns
only a redacted `probe-unavailable` with no live data changes.

This can briefly write PostgreSQL system-catalog changes inside a
transaction that is rolled back. No original data rows are touched;
no extension is left installed by this diagnostic, no `pg_repack`
client is invoked and no `VACUUM FULL`, TRUNCATE, DELETE, ALTER TABLE,
copy of source data, external database access or scheduled retry occurs.
No credential, ISIN, token or original payload enters logs.

## Interpretation

`pgstattuple_approx` gives exact dead-tuple bytes and approximate
free-space/live-tuple bytes for each scanned relation. Its main/TOAST
estimate is **not index bloat** and does not equal guaranteed provider
disk reduction: repacking also needs a new table copy, extra WAL,
brief locks and a matching explicitly enabled `pg_repack` extension.
Even a large internal free-space figure requires separate maintenance
approval and an independent Render physical before/after metric.

The diagnostic **always** reports `readyToRepack=false` and
`diskBytesFreed=null`. If extension activation or the TOAST scan
fails, we do not alter PostgreSQL privileges or fall back to unsafe
heap-size arithmetic. This is a measurement, not a storage rewrite.
