# Bob: recovery-key continuity and a reversible one-decision pilot

**Deployment state:** Source-code preparation only. No Render configuration,
live database writes, expanded deletion rights, scheduled migration, paid
resources, new orders or physical disk-free claim are introduced by this PR.

## Why another gate is needed

The AES-GCM archive from 2026-11-03 was independently downloaded and restored,
but its recorded receipt did not certify an independently available *recovery
root*. Version `aes-256-gcm-stream-v1` derives the encryption key from the
then-current private `PUSH_SERVICE_TOKEN`. Rotating that token without
retaining its prior exact value makes that old archive undecipherable.

A second Render environment variable alone is **not independent escrow**.
The original root must be preserved outside Render, GitHub and Google Drive in
a private durable secret manager or offline backup under the operator's
control. Never transmit it in ChatGPT, issues, commits, CI logs, or screenshots.
The program cannot inspect or certify the durability of offline escrow.

## Recovery verification, no deletion

1. Confirm the exact original token is independently escrowed; **do not
   rotate** the current token until this is done. Temporarily provide the
   same original value as the private secret
   `BOB_ARCHIVE_RECOVERY_ROOT_TOKEN` in an authorized private runtime.
2. For a **new** reviewed-evidence archive attempt, opt in with
   `BOB_ARCHIVE_ENCRYPT_BEFORE_UPLOAD=1` and
   `BOB_ARCHIVE_RECOVERY_PROOF_ONCE=1`. Follow the existing once-per-day
   unique claim and independent-restore checks; never override a running
   claim, do not retry by clearing database evidence.
3. After the genuine Google Drive upload/download, the recovery proof reads
   the downloaded AES-GCM ciphertext in 1-MiB blocks, authenticates it with
   the separately supplied root, verifies the original SHA-256, and returns
   only `recoveryKeyVerified=true` when successful. It writes **no** extra
   plaintext file, hashes no secret into logs, and does **not** delete data.
4. Independently validate the new persisted receipt:
   `encryptionVerified=true`, `encryptionVersion=aes-256-gcm-stream-v1`,
   `recoveryKeyVerified=true`, `remoteDownloadVerified=true`,
   `restoreVerified=true`, `restoreIsolation=separate-database-instance`,
   and `scope=reviewed-evidence-tables-not-full-database-backup`.
   The file receipt and persistent DB attempt must match and be fresh.
5. After testing, remove the *temporary runtime copy* of the recovery root
   only if the independently escrowed original remains safely accessible.
   `unseal(..., recovery=True)` is the explicit emergency path to restore
   old archive ciphertext after `PUSH_SERVICE_TOKEN` rotation. It never
   silently tries alternate keys.

If any proof fails, do not migrate historical originals. A missing or
unverified recovery root is a blocker, not an acceptable warning.

## Historical decision pilot (one original array only)

The pre-existing `decision_product_pilot_cli` accepts a *manual* one-use
command and unique durable claim; it has no HTTP route or startup hook.
The source must be an **immutable** decision at least 14 days old, with a
large complete historical `products` array. No open simulation, mutable
position, source quote, stop, order or independent outcome is eligible.

The normal writer now rejects receipts without the exact encryption,
recovery, independent restore and archive scope fields above. When the
verified receipt is less than six hours old, both service readers are
deployed/validated, and an independent Render disk sample is fresher than
five minutes and below the existing budget, an operator may manually run
the existing private preflight, then explicitly authorize *one* source
array with `maxUpdates=1` and its unique non-reused pilot claim ID.
No expanded batch-size gate is added here.

The writer uploads/downloads the original product array and compares its
cryptographic digest, then performs an exact JSONB CAS and read-through in a
short database transaction. The entire original decision ID, timestamps,
rule context and non-product fields remain inline. The external archive
is retained even if a subsequent rollback is needed.

## Explicit rollback of the one pointer

A separate, default-OFF function `decision_product_single_rollback.restore_one`
and terminal-only `decision_product_rollback_cli` can restore exactly one
historical pointer to its original inline JSONB. It freshly downloads the
content-addressed archived object without using a cache and validates the
existing reader, exact product hash, row clock, pointer, and identity-bound
reference. It then CAS-restores the original and removes **only that
one decision's pointer ledger entry** in the same transaction. Shared
archived content remains untouched.

For an explicitly authorized emergency rollback only, privately set
`BOB_DECISION_PRODUCT_ROLLBACK_ENABLED=1` and the one decision ID in
`BOB_DECISION_ROLLBACK_TARGET_ID`, then invoke
`python -m decision_product_rollback_cli execute --acknowledge-one-original`
in an authorized isolated operator terminal. IDs and original data are
not printed. Never wire this command to Render startup or a scheduler.
Rollback also requires a fully verified original chunk; it fails closed
if the Drive object is missing or corrupted. An operator should verify
read-through and unchanged audit outputs before any further pilot.

## Physical Render capacity (separate evidence)

Measure a fresh, **provider-reported** physical volume value before and
after the pilot and after any separately approved maintenance, recording
timestamps, unit, and associated database relation sizes. Changing JSONB
does **not** automatically return WAL, TOAST, or provider volume bytes.
For a single small pointer, zero physical byte savings is entirely possible.
No `VACUUM FULL`, reindex, broad purge, or mass migration is introduced.

Keep the existing one-row pilot disabled until all the above is proven in
GitHub CI + isolated PostgreSQL tests and reviewed on both deployed
services. Do not treat successful code CI as permission to erase originals.
