# Device-scoped PNG orphan object lifecycle: isolated rehearsal only

## Why a garbage-collection proof is mandatory

The existing `bob_android_shadow_batch_refs` table links to its source batch
with `ON DELETE CASCADE`. When the 24-hour source importer expires a batch,
its reference ledger row disappears. However `bob_android_shadow_objects`
has no FK back to those rows: object bytes survive unless independently and
carefully reclaimed. Deleting **all** objects from an expired batch could break
another still-valid batch of the SAME device referencing the identical PNG.
Identical imagery across two devices must always retain separate scoped keys.

## Exact scope

`android_image_gc_rehearsal.prune_orphans_in_test_schema(conn)` is only
permitted in an isolated `png_gc_<32-hex>` PostgreSQL test schema, with
synthetic images. It is NOT called by a live handler, worker, startup, API,
cron, CLI or Render maintenance command.

In one bounded transaction it:
- Reads at most 16 references and 64 object metadata rows; larger ledgers
  fail closed without touching anything.
- Verifies every remaining reference is an unexpired, same-device source,
  that pointer shapes/keys are valid, and that each image can fully
  reconstruct via the existing strict content/whole-batch checks.
- Builds device-scoped live object identifiers using `(token_hash,object_key)`
  and removes only absent-from-all-live-references objects.
- Rereads all live references before commit. Any missing, mismatched, cross-
  device or corrupt reference rolls back the entire isolated transaction.
- Never deletes a source or reference batch; source expiry and FK cascade
  are simulated only in the CI fixture.
- Returns only bounded counts and `diskBytesFreed=null`, never original
  PNGs, private hashes, IDs or account information.

CI demonstrates that two batches with the same device-scoped PNG keep their
shared object until the **last** reference is gone; a different device remains
intact, while tampering, stale live sources or mismatched device ownership
blocks cleanup.

## Still not ready for real storage release

This test uses synthetic records with an explicit small bound. A later
production GC implementation would need concurrency tests with new uploads,
separate transaction ownership, object-level retention and revocation,
bounded pagination, all-reader compatibility, reliable encrypted backup
binding, per-batch rollback, WAL/lock/scratch budget, and actual Render
physical disk measurements. Existing 24-hour source expiry remains unchanged.

No new production tables, no live object deletions, no automatic migration,
no `VACUUM FULL`, no paid scaling, no opening database network access.
`migrationAuthorized=false`, `deletionAuthorized=false`,
`diskBytesFreed=null`. Related to #1231, #1233 and #1222.
