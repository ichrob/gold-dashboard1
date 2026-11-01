# Android PNG reference shadow: exact live-batch round-trip without database writes

## Purpose

The authenticated Bob image duplication report on 1 November 2026
sampled 8 recent batches / 24 screenshots and proved that **18** of the
screenshots were byte-for-byte repeats (5,394,552 repeated raw PNG bytes,
7,192,760 repeated base64 characters). This justifies testing whether a
device-scoped content-addressed reference scheme can reproduce the
*entire* existing batch, including original PNG text, source timestamps,
app text and session identity, without changing active readers.

PR #1215 supplied a pure, offline `android_image_reference_codec`. This
shadow stage applies that existing codec to a small, actual private
PostgreSQL sample, *without persisting the result*.

## Safeguarded live read-only test

- `storage_budget.report` exposes an additional privately authenticated
  `androidImageReferenceShadow` field. No new HTTP route or public data
  exposure.
- A fixed indexed SQL reads at most **8 newest image batches still within
  the existing 24-hour retention**. Existing import validation permits
  1–4 screenshots per batch. The in-process encoded image total is capped
  at 12,000,000 characters. Failure/cap returns an explicit incomplete
  status, not partial proof or a space claim.
- The query first checks aggregate source JSON text size without returning
  images. Only cohorts with at most eight rows and at most 14 million
  source JSON characters can be transferred for the shadow, and the decoded
  PNG/base64 total is independently capped at 12 million characters.
  Invalid/missing permission or changed row count fails closed.
- Each original is checked using `android_list.validate` **at its
  original `created_at` upload time**, not re-dated to the current clock, then
  converted **in memory only** by `pack_batch(original, token_hash)`.
  The authenticated device's existing 64-hex-character token hash is the
  content-addressing domain. Identical PNG bytes belonging to different
  device scopes must **never** share one stored key or image.
- The shadow merges temporary object maps only if a key maps to the
  **same original encoded PNG string**, not merely the same decoded PNG
  bytes. This prevents changing an original import's representation.
- Every reference batch is restored via `restore_batch(..., scope)`,
  compared to its original full JSON object, and passed again through
  the existing active import validator. A missing/corrupt/ambiguous image
  or mismatched source timestamp is a failure.
- No PNG, content-addressed key, account/device token, session, batch ID,
  ISIN, app text or exception message appears in output/logs.
- The returned numeric sample includes count of devices, source batches,
  images, unique scoped objects, repeated references and comparative
  **serialized JSON size** (compact, deterministic serialization only).
  PostgreSQL TOAST allocations and physically freed Render disk are not
  represented by JSON sizes.
- Query is read-only, with 2.5-second statement / 0.5-second lock timeout,
  process-local 15-minute cache, and no new tables, indices, stored
  objects or background threads.

## Not yet authorized

`fullBatchRoundTripVerified=true` means **only** in-memory reconstruction
of the selected, strictly bounded sample. It does NOT authorize a
production storage migration. `persistentBackupVerified=false`,
`migrationAuthorized=false`, `reclaimableBytes=null`,
`diskBytesFreed=null` are deliberate.

A subsequent separately reviewed pilot would need:
1. Device-scoped transactional object and reference schema, collision
   resistance plus bytewise checks, proven 24-hour expiry.
2. All existing readers (`list-get`, list-status, handoff, processing,
   background jobs, recovery, authenticated device limits) reviewed and
   tested for exact original reconstruction. Missing image = fail closed.
3. Independent source and reference ledger backup with remote download,
   hash/read-through verification on a separate restore instance.
4. One bounded, explicitly authorized original with rollback and no
   fabricated quote timestamps or product evidence.
5. Provider-level physical disk before/after and scratch/WAL/lock budget
   before any rewrite; never claim freed MB from theoretical JSON deltas.

No real trade, paid service, deletion, shortened retention, database IP
opening, ordinary screenshot upload change or `VACUUM FULL` is part of
this proposal.
