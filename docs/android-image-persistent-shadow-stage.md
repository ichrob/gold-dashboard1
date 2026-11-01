# Android / DEGIRO original PNG object-reference pilot – isolated database stage

## Current evidence and why this exists

On 1 Nov 2026, private Bob diagnostics sampled eight active screenshot batches
with 24 PNGs, **18 byte-for-byte repeats** among the 24 PNG records,
and a device-scoped in-memory roundtrip of all eight batches. The compact
logical JSON difference was **7,190,371 bytes**; this is NOT physically
available Render volume space.

To get from an in-memory design to real persistent storage without risking
the DEGIRO reader, this stage builds the reference/object ledgers only in
the **isolated PostgreSQL CI integration environment**. It explicitly
does **not** wire them to Bob's application startup, Android upload/receipt,
OCR handoff, list-get/list-status, Render scheduled worker or private HTTP
routes. Production originals are untouched; there is no disk saving yet.

## Proposed durable schema – still disconnected

`android_image_persistent_shadow.py` exports
`init_test_schema(conn)`, `stage_copy_test_only(conn,batch_id,scope)`,
and `verify_shadow(conn,batch_id,scope)`, all designed for controlled,
isolated tests. There is no live CLI or feature flag.

- `bob_android_shadow_objects`: original base64 PNG text with a
  **device-scoped, domain-separated SHA-256 content key** and a
  `PRIMARY KEY(token_hash,object_key)`. A conflict can never silently
  replace stored bytes: the exact encoding is re-read and compared.
- `bob_android_shadow_batch_refs`: the pointer batch, original SHA-256 of
  canonical complete JSON, original `created_at` and an FK on original
  `batch_id` with `ON DELETE CASCADE`. The original row must still
  exist and be younger than its existing **24-hour** period for any
  restoration.
- Each stage is a **single database transaction**, with a fixed one-second
  lock timeout and five-second statement timeout, source `FOR SHARE`,
  existing `android_list.validate` before and after reconstruction,
  content-key collision checks, same-device ownership and complete
  original JSON equality. Every error must roll back the staging changes.
- A repeated PNG belonging to the same device may reuse its existing
  shadow object, but the same PNG from another device gets a **different**
  scoped key. No cross-device read.
- Tests also simulate source expiry and FK cascade; an object whose last
  reference expired remains a separately identifiable **orphan** for a
  future, *separately reviewed* verified garbage-collection operation.
  The current prototype never deletes objects automatically.

The only stage result is a small sanitized count/status such as
`isolated-shadow-copy-verified`; no PNG, scope, key, ISIN, batch identity,
account information, app text, archive credential or price clock leaves
the test result. `migrationAuthorized=false`,
`persistentBackupVerified=false`, `diskBytesFreed=null`.

## Crucial blocker before any actual production copy or migration

The existing 1 Nov 2026 verified private Drive backup covers **reviewed
evidence tables, not the complete PostgreSQL database**, and is not a
verified complete backup of temporary handset PNG originals plus the new
reference/object ledgers. The exact PNG object mapping, its owner
authorization and a separate **restore test** must be included in a
protected backup before any live source replacement. A copy of an
object ledger does not by itself make it safe to delete a source batch.

A safe next, separate PR/pilot requires:

1. An explicit inventory of all producers and readers of
   `bob_android_list_images`: `android_list.handle` upload, list-get,
   list-status and details; `handset_list_worker` OCR reads/processing;
   private list handoff and diagnostic metadata.
2. A backward-compatible *resolver* that faithfully recreates the **exact
   original** `payload.images[].png` string, image source time, batch
   identity and app text, with row/device authorization and fail-closed
   behavior if a pointer/object cannot be accessed. Product quote
   timestamps must never be refreshed by reconstruction.
3. An independently verified, private, durable **backup and remote
   restore** of the original single batch, objects, and reference rows,
   with checksums and restrictive device owner permissions.
4. A separately authorized **one-batch, write-once** trial with a
   transactional rollback plan, distinct pilot claim and independent
   Render volume measurement. Both the original and restored source must
   compare byte-for-byte.
5. A safe 24h expiry and object orphan-cleanup strategy, with crash,
   concurrency, tamper, device revocation and failure-injection tests.
6. Only after proving read-through for every caller and net physical
   Render volume savings should a broader source replacement be enabled.
   Any physical Postgres rewrite additionally needs WAL, scratch, lock
   duration and restore-margin approval.

No `VACUUM FULL`, `REINDEX`, deletion of active original PNGs,
retention reduction, public database IP allowance, paid tier, live
trading operation or autonomous migration is part of this change.
