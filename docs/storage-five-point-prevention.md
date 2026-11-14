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

## Additional RAM guard for optional PostgreSQL work (14 November)

A real Render memory-metrics check shows the existing 256 MiB PostgreSQL
instance temporarily reached about 98.6% of its reported RAM limit in the
24-hour sample. This is NOT a confirmed OOM or evidence that paid RAM is
required: normal work remains active and disk occupancy was only ~21.5%.

Before either the already explicitly authorized single-table weekend tail
reclaim or the new manually confirmed decision-audit VACUUM, a separate
read-only `render_memory_guard` now checks the **existing** Render API's
fixed `/v1/metrics/memory` and `/v1/metrics/memory-limit` endpoints
using the already configured metrics key. It requires at least eight aligned
provider observations across at least ten minutes, with no gap greater
than three minutes and the latest no older than five minutes. Two good
readings with an unobserved interval can never authorize a maintenance run. Every observed sample in the last 15 minutes must
stay at or below 85% of the minimum applicable plan RAM limit and keep
at least 32 MiB free. Any missing, delayed, malformed, mixed-resource,
unverifiable, high-RAM or credential/HTTP error blocks the optional
maintenance before any discretionary claim or table VACUUM.

The original hourly four-table nontruncating maintenance is unchanged.
No automated RAM upgrade, plan change, new API credential, separate
service, alert channel, trading modification, backup retry, or SQL
retention expansion is introduced. An acceptable RAM result is NOT
authority for maintenance: the preexisting backup-age, independent
restore, Render volume, weekend, one-shot claim, lock and operator
authorization protections still apply. High-RAM deferrals are not
represented as SQL failures or reclaimed disk bytes.

After deployment, absence of green memory evidence must be surfaced as
a deferral; it must not be worked around by disabling the RAM guard or
silently enabling the currently off archive/compression/retention flags.


## Release preflight: interrupted same-day archive attempt (14 November 2026)

The owner explicitly authorized all four release tasks together: fresh
independently restored backup, adequate RAM/WAL/scratch capacity, controlled
deployment and post-release comparison. This is **not** unconditional
permission to bypass per-action recovery or availability gates.

On 14 November, a deliberate new `BOB_ARCHIVE_ATTEMPT` was configured
through the existing push service (no new service, provider or plan).
The attempt wrote a durable `running` claim at 19:39:57 UTC. Render then
completed a second automatic deploy at 19:40:40 UTC. The replacement
process had no running archive worker, while the claim was still
`running`. At that earlier observation, no subsequent independently restored success
receipt was available. The morning 00:49 UTC verified archive remained
intact but stale for further database-affecting maintenance.

**Treat this claim as interrupted / indeterminate, never successful.**
Do not reset the claim, delete source rows, overwrite a remote object,
or silently consume a new attempt ID. Review pending Render deploys,
current archive worker, uploaded remote objects, current Drive quota,
fresh provider RAM telemetry, independent Aiven restore-target identity,
and WAL/scratch headroom before any explicit new attempt. A resumed
archive must get a NEW audit ID only after ruling out simultaneous work
and orphaned or ambiguous remote receipts. Returning
`BOB_ARCHIVE_ATTEMPT` to its ordinary `scheduled` setting also triggers
a Render deploy; do this only at a controlled idle boundary, never
during an uncompleted archive or concurrent code rollout. Do not leave
the one-off attempt name as a permanent normal schedule label.

GitHub `main` advanced during this work to include the Aiven-only
runtime restore policy and provider-bound receipt proof. The integrated
storage branch now contains those additions, and a new merge commit
with `main` as its second parent, preserving the latest production
files. All four CI categories must pass on that **exact latest head**
again before a production release.

Release order:
1. Prove a new completed remote-download / encrypted authenticated
   independent Aiven restore, recovery key and persisted receipt;
   do not equate a `running` claim with success.
2. Prove a sustained conservative RAM window for PostgreSQL plus
   adequate WAL, lock and temporary-space headroom. Never interpret a
   low database file size as available RAM.
3. Verify `main` has not advanced, all GitHub checks pass, no archive
   job is active, the rollback target is recorded, and the owner
   accepted the short restart window. Release one code revision only.
4. Confirm Render push/scanner deploys both finish on the exact commit.
   Recheck original-price freshness, signal/push and simulation health;
   compare two independent physical Render volume observations and
   report actual bytes freed only if independently measured. Retain
   all originals, encrypted archives and claims.

If any gate is unavailable, leave the draft unmerged and report the
specific blocked step through the existing Bob Fehlerzentrale; do not
create another recurring checker or external paid resource.


### Later receipt and integrated code baseline (14 November 2026)

The authenticated storage projection observed at 21:14 UTC reports a
later persisted verified receipt at 19:59:25 UTC: independent restore,
remote download, encryption, recovery key and isolation were confirmed.
This supersedes the earlier lack-of-receipt observation above; it does
not establish which old claim completed or permit rewriting that claim.
Read the newest original receipt and its explicit Aiven target binding
again at release time. Do not start another archive merely because an
older progress report still says `running`.

Provider RAM samples from 21:00 through 21:16 UTC still included values
above the 85% discretionary-maintenance gate, including the final sample.
The later receipt therefore does not by itself release optional SQL work.
No physical space saving has been demonstrated.

The integrated draft now includes main's Friday chart change and
deterministic risk-test clock from commit
`289d525f820ea0b04d3ae4ee0669f0ce49c4e6d1`. The merge was conflict-free;
local targeted tests passed, with unavailable local PostgreSQL integration
checks left to CI. All four checks must complete successfully on the new
draft head, not on the older `d13ee83d` revision. Before any storage merge,
verify the actually deployed main revision and record that revision as
the rollback baseline. The existing one-time 15 November 03:30
Europe/Zurich review remains the release window; no second job is added.
