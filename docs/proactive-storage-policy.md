# Proactive storage policy (4 November 2026)

The 5 GB allocation is safety headroom, not a growth target. Existing metric,
analysis and observation offload workers use logical PostgreSQL size to choose
bounded recurring work: below 500 decimal MB hourly, from 500 MB every fifteen
minutes, from 700 MB every five minutes. Failures back off for one hour. The
existing independent physical-volume gates and per-cycle limits stay intact.

Preserve recent hot data, compact evaluations and exact remote originals.
Offload must retain original identities, clocks and values and verify remote
read-through before committing references. Existing retention and reader
contracts remain unchanged. This cadence change does not enable decision or
image migrations, grant deletion permission, or trigger table rewrites.

Remaining acceptance work is tracked in issue #1329: complete historical and
independent replay checks; execute the guarded decision pilot through a private
maintenance shell; archive protected image batches only with batch-bound restore
and rollback evidence; complete the existing weekend physical-reclaim workflow.
Compare actual Render volume before/after separately from JSON savings and
PostgreSQL reusable pages. Report growth and reclaimed bytes without double
counting earlier maintenance. Preserve market analysis, ranking, push, trade
monitoring and required simulation evidence. No extra service or storage purchase.
