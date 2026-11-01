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
