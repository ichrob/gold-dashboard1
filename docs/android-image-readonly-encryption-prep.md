# One-image-batch read-only preparation and authenticated encryption

## What this change enables

`android_image_backup_prepare.pack_active_source_readonly(conn,batch_id,device_scope)`
can build the existing versioned recovery format directly from exactly one
**active** original screenshot batch. The trusted, server-internal caller must
already possess the authenticated device scope and the specific batch ID.

It makes just one bounded SQL SELECT of the original PNG data and metadata,
joined to an unrevoked, unexpired device. Missing, stale, malformed, cross-scope
or oversized source evidence fails closed. It does **not** create production
reference tables: exact per-device PNG object keys and pointers are generated
**in process memory**, packed together with full original bytes, original
upload time, parsed items, import receipt, processing time and attempt count,
then validated by the existing recovery decoder. Return is a compressed
in-memory blob plus its SHA-256, not an archive receipt.

`seal_bundle(blob,sha256,key)` uses AES-256-GCM with a fresh random 96-bit nonce,
versioned authenticated header and separate caller-provided 32-byte key.
`open_sealed_bundle(cipher,cipher_sha256,original_sha256,key)` verifies
ciphertext SHA-256 and the authentication tag, then validates the full
compressed source/reference/object bundle. Any invalid input fails closed.
Never write raw plaintext to disk or to logs, GitHub, email or Drive.
A separate, independently controlled long-lived encryption key is required;
do not derive it from Push/OAuth tokens or save it in an archive receipt.
Keys must be managed and rotated separately, with a tested recovery procedure.

## What it deliberately does NOT do

There is **no** application hook, live command, endpoint, flag, scheduled job,
database writer/schema change, archive upload, restore-server connection,
or automated migration in this PR. Nothing will happen on Render after a
merge without a separate reviewed runner. The helper makes **no live backup**
and cannot show remote download, encryption, independent-server restore, or
physical storage reclaimed. In-memory derived reference rows are not
production-stored reference rows, which do not yet exist.

Next: a separately approved manual runner on the trusted Render service must
validate runtime memory/scratch/lock budgets and free private Drive quota,
load an isolated encryption key via secure secret storage, export no more
than one currently active 24-hour batch, send **only ciphertext** to a private
authorized Drive folder, independently download it and verify both ciphertext
and plaintext hashes. A separate PostgreSQL *server*, such as the existing
free `bob-archive-restore-test` before its expiry, must restore all original,
object and reference data and compare exact timestamps, parse/receipt and
pixel bytes. The restore test must itself have correctly isolated permissions
and no readable secrets in logs.

Only a **subsequent** separately authorized one-batch production reference
pilot can update an actual source row, with CAS, roll-back, original and
reader proof, 24-hour expiry and garbage collection. No original deletion,
automatic bulk mode, shorter retention, `VACUUM FULL` or paid scaling is
authorized. These are prerequisites to **future** independent Render
physical-volume measurements; logical JSON bytes are not disk bytes freed.

Related: #1001, #1222, #1218, #1219, #1220.

## Manual remote restore coordinator (still disconnected)

`android_image_backup_runner.run_once` is **a function, not a CLI, app hook,
service endpoint, scheduler, or automatic job**. It requires separate, caller-
authorized source and restore DSNs, the exact authenticated active batch/device,
a 32-byte secret key managed outside GitHub and a preflight-capable private
Drive adapter. No UI/HTTP method exposes it.

It checks `verify_restore_isolation` against a separate database host **before
reading images**. Source connections enforce PostgreSQL read-only mode. Only
encrypted AES-GCM bytes are written to mode-0600 scratch and uploaded; the
independently downloaded encrypted bytes must match SHA-256, pass GCM tag
verification, match original compressed SHA-256 and reconstruct every referenced
object, PNG and metadata field. The restore occurs in a randomly named fresh
`png_restore_<uuid>` schema on the **other** PostgreSQL server and is rolled
back in the outer transaction: no source or test records are permanently
replaced. After remote restore, the current source batch is re-read and must
still equal the initial original snapshot. Only then may the runner create a
small **private** JSON receipt with ciphertext and original archive hashes,
remote file ID, verified clock and explicit no-delete/no-migration flags.
The receipt itself is uploaded only to the authorized private Drive folder
and independently downloaded and SHA-256-verified. Public/user-facing
status excludes the private file ID and content checksums. A failed remote
restore, source recheck or receipt upload cannot yield a success status.

If the backup fails after an upload, an orphaned **encrypted** private Drive
object may remain. It must not be reported as successful and must not be
automatically deleted. Do not call the runner until Drive runtime credentials,
encryption key and independently reachable restore server are authorized and
verified. This module does not change Render env/secrets and cannot perform
that setup through a normal code merge; the existing closed IP-Allowlist
must never be relaxed just to make hosted external SQL tooling work.

The integration test uses the CI PostgreSQL instance solely to prove the
isolated schema is created, verified and rolled back. The unit transport
adapter is simulated. **Neither is a live Google Drive remote backup** or a
true independent-server test; `independentServerVerified=true` in a live
receipt requires a successful actual verified production-to-separate-server
runtime invocation. No source cleanup, compacting, replacing or disk saving
is approved by these tests.
