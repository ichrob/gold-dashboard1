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

The authenticated /storage-health endpoint performs bounded catalog reads and is
independent of the full simulation report. It exposes the 12 largest tables,
estimated live/dead tuples, autovacuum time, measured database bytes and applied
storage settings. No prices, identities, credentials or queries are returned.

For six explicit evidence tables, PostgreSQL's toast_tuple_target is lowered to
512 bytes, permitting lossless native compression earlier. The short lock timeout
and savepoint prevent maintenance from blocking diagnostic delivery. This applies
to new or subsequently updated rows. Existing tables are not bulk-rewritten and
no immediate historical disk reduction is claimed. Read/query formats are unchanged.
Identical candle checkpoints no longer create a replacement row/version, reducing
write amplification while preserving all accepted candle revisions.

Unbounded data generation cannot fit forever on fixed storage. When a budget
threshold is crossed, inspect measured table growth before choosing an additional
lossless archive/export or a separately authorized capacity change. Never silently
truncate comparison evidence, lower sampling quality or stop a test to hide growth.
