# Exact encrypted PNG archive ↔ active source binding (isolated/read-only)

## Purpose
The operator's successfully encrypted remote backup from #1222 is evidence
for **that exact original screenshot batch only**. A subsequent unrelated or
newer DEGIRO capture must never inherit its approval, even if two PNGs look
identical. The existing privacy-safe readiness field reports configuration
presence, NOT a verified backup or a production writer authorization.

`android_image_backup_binding.verify_current_source_binding(...)` is a
**standalone, protected-process helper**; it has NO CLI, HTTP route, service
startup import, scheduler, upload/delete code, production schema migration or
Render environment update.

## Required, caller-verified inputs
- Bytes of the **private, canonical 4-KiB-bounded verification receipt**,
  obtained only via the already authorized private Drive identity.
- The exact archived **AES-256-GCM ciphertext bytes** downloaded from Drive,
  and the actual Drive file ID obtained through that private authenticated
  channel. The identity must match the receipt's archive file.
- An escrowed 32-byte key provided only in the protected runtime; NEVER
  print it, commit it, attach it to the receipt or send it into CI/ChatGPT.
- The exact caller-authorized `batch_id` and authenticated device scope,
  and a live read-only database connection.

## Checks
1. Refuse unrecognized fields, noncanonical receipt, missing verification
   flags, claimed migration/deletion/disk-savings, mismatched file/size/hashes
   or altered/aged receipt timestamps.
2. Check cipher SHA-256, AES-GCM authentication and strict existing bounded
   full-manifest + all PNG objects/references validation.
3. Require the decrypted manifest's original batch ID, device scope, timestamp,
   complete original receipt and image count to match the intended source.
4. Rebuild the **deterministic** source/references recovery package using a
   short, read-only SELECT from the *current*, active, unrevoked, less-than-24h
   PostgreSQL source. Compare the full canonical compressed package **bytes**
   and SHA-256 to the downloaded archive. Any new batch, expired capture,
   revoked device, changed original PNG, changed receipt/parsed rows or even a
   processing-attempt difference must fail closed.
5. Return ONLY safe flags. In particular
   `independentServerRestoreReverifiedHere=false`,
   `keyEscrowVerified=false`, `productionMigrationAuthorized=false`,
   `originalDeletionAuthorized=false` and `diskBytesFreed=null`.

## Deliberate limits
This function alone cannot establish **where** the caller downloaded the
receipt/ciphertext, cannot reverify the remote restore-server's independence,
cannot certify separate key escrow, and cannot freeze or lock a row for a
later production CAS. A successful read-only binding check may become stale
immediately due to concurrent OCR updates, capture expiry or device revocation.
A future **distinct operator-consented** maintenance pilot must check the
same immutable source/receipt **again inside its CAS transaction**, pass
all-reader/concurrency/GC safety, and measure WAL/lock/scratch + physical
Render volume before any productive pointer write.

CI tests use synthetic keys and PNGs only. No production original is
modified, no new storage is allocated, no deletion or bulk migration enabled.
See #1231 and #1222.
