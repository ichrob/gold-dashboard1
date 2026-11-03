# Storage budget

Render allocation verified on 2026-10-27: 1 GB, no disk autoscaling. This change
neither increases the plan nor enables paid scaling. A logical database measurement
is not a disk-utilization percentage: WAL, other databases and platform overhead
also occupy space. The 500 MB caution / 700 MB action thresholds leave headroom.

Existing asynchronous diagnostic delivery observes database size at most once per
30 minutes per process. The shared time-bucket key deduplicates samples. Only these
small capacity samples expire after 90 days; no test evidence is deleted. Reports
show a trend only after at least 24 hours, and a linear days-to-threshold estimate
only for positive observed growth. Estimates are not a capacity guarantee.

Each new capacity sample also records an exact `pg_total_relation_size` snapshot
for the current user tables. After two fixed snapshots, the private report exposes
the twelve largest absolute per-relation byte deltas together with their baseline,
latest sample, and elapsed time. This separates measured table growth from a later
single-table size ranking without adding full row scans or modifying evidence.

The authenticated /storage-health endpoint performs bounded catalog reads and is
independent of the full simulation report. It exposes the 12 largest tables,
estimated live/dead tuples, autovacuum time, measured database bytes. No prices, identities, credentials or queries are returned.

Identical candle checkpoints no longer create a replacement row/version, reducing
write amplification while preserving all accepted candle revisions.

Unbounded data generation cannot fit forever on fixed storage. When a budget
threshold is crossed, inspect measured table growth before choosing an additional
lossless archive/export or a separately authorized capacity change. Never silently
truncate comparison evidence, lower sampling quality or stop a test to hide growth.


## Retrospective exact 18:00 UTC daily view

The compact private storageBrief.fixedSlotDaily projects **only existing**
bob_storage_samples half-hour snapshots. For the latest 18:00 UTC daily
boundary it compares the exact preceding 18:00 UTC slot; it also reports up
to seven retrospectively requested daily windows, within the already loaded
336 snapshot rows. Earlier or missing snapshots remain missing-* and
unavailable numbers are null, never inferred from neighboring times.

The fixed five-table order is bob_diagnostic_history,
bob_candle_evidence, bob_decision_audit, bob_metric_checks,
bob_improvement_observations. The current exact pair exposes before/after
relation allocation, net allocation, and four cumulative tuple-counter
differences (INSERT/UPDATE/DELETE/HOT-UPDATE), with per-table missing/reset
status. Past daily windows expose database deltas, five ordered per-table
relation allocation deltas and counter coverage, without original row
contents. The compact view is derived during the existing diagnostic report;
there is **no new collection, background worker, retention modification, or
database read**. The current logical database size and independently
timestamped Render volume value remain separate.

This is not a WAL/bloat measurement, a physical disk savings claim, a
verified statistics-reset history, or an archived recording of missing
snapshots. diskBytesFreed and the physical-volume delta are null. A positive
tuple-counter difference does **not** exclude an unseen PostgreSQL statistics
reset: reset timestamps were not persisted. Do not authorize deletion,
table rewrites or maintenance from the report. Historical access is bounded
by the existing snapshot query and the existing 90-day telemetry retention.
