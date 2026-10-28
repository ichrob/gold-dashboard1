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
