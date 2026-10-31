# Learning evidence archive and storage pressure

The optional push worker `BOB_COLD_OBSERVATIONS_ENABLED=1` moves only the
`evidence` field of learning observations older than 24 hours. All other JSON
fields, primary keys, validity and timestamps remain in PostgreSQL, preserving
SQL predicates and study windows. Full-payload readers resolve the evidence.
No decision-audit payloads or original trading records are deleted.

Identical evidence has one SHA-256 content address across observations and
batches. A compressed private Drive chunk holds up to 500 unique evidence
objects, bounded to 2 MiB uncompressed. Each new upload must be downloaded and
verified before compare-and-swap updates. Existing shared objects are read and
compared before reuse. The object ledger and pointer changes commit together.
Failures leave originals in place; missing/corrupt archived evidence raises an
explicit incomplete-report error. Original numeric values are preserved.

The object ledger is included in full backups. Keep it, all referenced private
Drive files, archive credentials and compatible readers. Disabling the writer
does not permit rolling back readers. There is no automatic archive deletion.
Deploy both readers first, then enable the writer on push only.

All enabled cold workers use measured database size to select a delay after a
bounded pass: below 500 MB 60 minutes, 500–700 MB 15 minutes, >=700 MB 5 minutes.
Errors back off for one hour; a running full backup defers work for one minute.
These are database-size thresholds, not a measurement of filesystem free space.
Observation and analysis passes stop between chunks after 120 seconds; Drive
requests and the current transaction can extend the total pass duration.

Analysis/observation offloads request a bounded normal VACUUM with tail
truncation. The SQL has a 10-second statement timeout and one-second lock
wait. Other tables retain their maintenance cooldown. No automatic FULL
rewrite is enabled: a fresh disk-space observation and a verified backup are
still required before a separate rewrite. A successful VACUUM may free zero
bytes. Raw JSON reduction, relation shrink and filesystem free space are
separate measurements. There is no guarantee of staying below 500 MB.

Decision-audit offload remains a separate task because its many JSON SQL
predicates and history readers require coordinated compatibility changes.
