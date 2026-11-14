# Bob: five-point preventive storage plan (14 November 2026)

This is a **code-only draft** for the five user-requested mitigations.
No service is deployed by this PR, no paid tier/provider is enabled, no
database/IP allowlist/retention permission is broadened, and no physical
disk savings are claimed without independent Render volume measurements.
The separate guarded PostgreSQL one-shot is PR #1724.

## 1. Drive offload promptly after independently restored backup

Existing `archive_worker.cycle` remains a daily, uniquely claimed complete
snapshot. After a *new* successful verified remote restore, the worker can
now call the **preexisting, expressly configured** weekend one-shot tail
reclaim immediately, instead of waiting up to the regular maintenance
interval. If the one-shot is absent, already claimed, outside weekend,
unverifiable, locked or out of volume headroom, nothing is reclaimed.
No new backup, upload, deletion, service or paid job is created.
No source record is deleted and the full archive and receipt persist.

This does **not** turn a backup into permission to remove originals. A
physical before/after Render volume reading is still required.

## 2. Preserve evidence and catch up with already approved journal retention

`bob_diagnostic_history` has a preexisting **seven-day / 60,000-event**
retention and a 500-row capped batch. Logs on 14 November show repeated
500-row completions at 15-minute intervals even while live-row estimates
exceeded 86,000. No original evidence category or historical retention is
shortened here. When an operator explicitly enables
`BOB_DIAGNOSTIC_WEEKEND_CATCHUP=1`, fully completed 500-row batches can
run at 5-minute spacing **only on a Swiss weekend and while a fresh,
independently restored archive receipt is verifiable**. Any failure falls
back to the existing 15-minute cycle. Active trading-hour scheduling,
per-command row limits and five-second SQL timeout remain unchanged.
The feature defaults OFF. Estimated live counts are not exact backlog
counts and no source-data loss is asserted or concealed.

## 3. Drive runway and lossless archive size option

Drive uploads already refuse unknown quota or less than the required
upload + 256 MiB reserve. The same authenticated quota observation now
also calculates conservatively how many additional full uploads of the
required bounded size *might* fit, without authorizing anything. The last
verified quota observation is exposed privately as a HISTORICAL value;
it is explicitly not the current Google account's free space.

`BOB_ARCHIVE_ZIP_LEVEL=3` is a manually selected, optional DEFLATE setting
for future full v3 archives. It defaults to level 1, alters no historical
archive, stays compatible with the existing ZIP restore reader, and must
pass a representative size, time, CPU and RAM benchmark before activation.
Do not assume compressed bytes will be smaller on actual Bob data.
**Differential/incremental archives are not activated**: such a format
would need a durable base/chain manifest, immutable encrypted objects,
independent missing-base and corruption rejection, full exact replay
and proven key availability before it could replace v3 complete backups.
No backups in Drive are automatically deleted or overwritten.

## 4. PostgreSQL space reuse

PR #1724 contains the separately scoped, operator-only decision-audit
`VACUUM` option plus a read-only persisted weekend claim status. Existing
normal `VACUUM` for four tables remains unchanged. There is no
`VACUUM FULL`, index rebuild, unapproved table, or data deletion.
Neither PR releases to Render automatically. The connected Render SQL
tool cannot reach production: the database IP allowlist remains empty.
The live background maintenance continues under its existing controls.

## 5. Early warning without invented disk savings

`storage_prevention.assess` reads only existing redacted metadata and
publishes physical-volume warning levels at 50/70/80/90%, plus bounded
**logical database** daily growth, estimated diagnostic live rows
against the existing 60k cap, archive proof freshness and the historical
Drive free-space snapshot. A stale provider reading means UNKNOWN, even
if the database is small. Logical daily allocation is not projected as
actual physical disk freed, and no alert is sent to the user from this
draft. A central alert-delivery rule should be wired only after the
existing Bob Fehlerzentrale message dedupe is verified, not as a new
parallel notification channel.

## Acceptance before deployment

- All Python/PostgreSQL/JS, risk and security CI checks must pass on this
  commit. Failed or skipped checks are never reported as green.
- Isolated exact ZIP roundtrips and tests for quota, retention, stale
  archive proof, weekend gating, storage warning and redaction.
- The older full archive workflow and locked restore server remain untouched.
- Deploy requires the existing user-accepted restart/change window; no
  automatic live rollout from these draft branches.
- Prove actual reductions using separately observed Render volume, not
  source row counts, compressed bytes or `VACUUM` completion alone.
