# Explicit diagnostic-history compaction

The existing one-shot compactor additionally accepts `target: "diagnostic"`.
It accepts only the fixed metric/diagnostic tables and their known indexes.
The diagnostic relation must be <=200 MB. No rows or JSON values are deleted.
All cold writers and normal maintenance are excluded with session locks.
A verified remote-download/restore backup from the last 24 hours and an
operator-observed free-disk lower bound no older than one hour are mandatory.
Never derive this bound by subtracting database size from allocation.

Free-space input is capped at 250 MB. Deduct database growth since observation,
and twice the size of each rebuilt index to budget unrecycled WAL/temp writes.
Never credit index shrink as newly measured free disk. FULL requires twice the
estimated live row/index footprint plus 50 MB reserve within the remainder.
Insufficient capacity skips FULL, even if index rebuilding succeeded.

Each index statement has a 30-second limit, lock wait one second. Diagnostic
FULL has a 90-second statement limit and briefly blocks diagnostic table access;
a lock failure or timeout is reported, not retried automatically. Existing
one-attempt ledger and expiry prevent recurring rewrites. Resume evidence is
specific to the selected target. Clear the one-shot setting after observation.

Only relation-size reduction is reported; actual filesystem free space still
requires a fresh Render Disk Usage observation.
