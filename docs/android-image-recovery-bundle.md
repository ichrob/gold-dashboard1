# DEGIRO image recovery package: source + reference + object bytes

## Purpose and strict non-production scope

This change takes the next step beyond the isolated device-scoped PostgreSQL
reference proof in PR #1218 and production reader compatibility in PR #1219:
produce **one bounded, self-contained restoration package** holding the original
Android screenshot batch, its exact reference manifest, every referenced PNG
object, its original upload time, and the original processing/parse/receipt
metadata. Prove the package can reconstruct both the source and references
within a *different, fresh isolated PostgreSQL test schema*.

It deliberately creates **no** production startup hook, route, scheduled
worker, DB schema migration, public export, Drive upload or automatic
screenshot overwrite/deletion. No bytes are copied out of the production
runtime by this module. It is an internal-only helper for isolated testing.

## Format and safety checks

- `pack_recovery_bundle(conn,batch_id,device_scope)` requires a currently live
  original PNG batch and an existing shadow reference whose device scope,
  object bytes, timestamps and whole-batch SHA-256 are already verified.
  It reads only the matching batch and metadata; the source remains unchanged.
- The bounded private manifest contains the **original full PNG/base64 and
  app-text JSON**, original batch/session ID, original token_hash scope,
  source-created timestamp, original import receipt, parsed rows, processing
  time/attempt count, device-scoped reference payload and all referenced
  encoded image objects. Sensitive data must **never be logged or shown**.
- A deterministic canonical JSON representation is gzip-compressed in
  memory (`mtime=0`) and accompanied by a SHA-256 digest. Maximum raw and
  compressed bundle size are each **18 MiB**. The decoder verifies the
  checksum before bounded decompression; rejects excess expansion, noncanonical
  JSON, unexpected fields, wrong scope, duplicate keys and missing/tampered
  PNG bytes, then calls the existing source and reference validators.
- `restore_to_isolated_test_schema` requires a freshly selected schema
  `png_restore_<32 lowercase hex>`, not `public`, and a caller-prepared test
  source table. It atomically writes only to that test schema and reruns
  the full original/reference roundtrip before commit. It returns **only**
  small, non-sensitive validation flags, with
  `independentServerVerified=false`, `remoteDownloadVerified=false`,
  `encryptionVerified=false` and `deletionAuthorized=false`.
- Tests cover original-source immutability, source + metadata + reference
  equality on restore, corrupt bundle/checksum, different device scope,
  forged image objects, excessive expansion and refusal to restore to
  `public` or overwrite an existing isolated row. An unhandled failure
  rolls back test-schema changes.
- The package is **not encrypted**. It must not be uploaded to Google Drive,
  sent over email, committed to GitHub, written to public logs, or treated as
  a remotely verified backup. It must not be transferred outside a
  protected, separately approved encryption/backup stage.

## Actual remaining gates to physical savings

1. A separate authenticated, private, **encrypted** backup of exactly one
   source image batch plus object/reference ledger, with independent remote
   download, payload checksum and restoration into a **different database
   server** (different schema on the same server is not independent).
2. Full scope/ACL verification and byte-identical read-through for every
   current consumer (`list-get`, OCR worker, import-status, recovery).
3. Separate, explicit consented reversible single-batch production writer
   which leaves the original untouched until source + destination
   verification. No old evidence deletion or any automatic bulk mode.
4. An exact 24h expiry and object-reference garbage-collection policy
   proved not to leak another user's images or strand a live reader.
5. Independent Render physical-volume before/after measurement, and a
   verified scratch/WAL/lock budget before any table rewrite/reclamation.

The earlier review-evidence-only Google Drive restoration receipt is not
a **full image+reference+object** backup. It cannot authorize screenshot
deletion. The actual live volume was approximately **679.8 MB / 1 GB** when
this work began; theoretical compact-JSON savings of roughly 7.19 MB in
8 active batches are not physically recovered storage.
