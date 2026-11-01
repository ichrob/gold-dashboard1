# Android original PNG read-through compatibility (pre-migration)

## Observed capacity and reason

The authenticated Bob metrics from Sunday 1 November 2026 at about 16:42 UTC
show physical Render database volume **678,580,200 bytes** of a 1 GB allocation,
logical database size **568,489,663 bytes** and the previous verified
**eight-batch / 24-image** screenshot cohort (18 repeated exact PNGs).
The in-memory JSON serialization could save approximately 7.19 MB in those
eight batches, but that is not PostgreSQL or Render physical free space.
The existing persistent shadow from PR #1218 is **isolated test code only**,
and production imports currently still store full original PNGs.

## Reader compatibility without modifying source writes

New `android_image_readthrough.materialize` is used only by the two code
paths which currently consume `bob_android_list_images.payload` directly:

- Authenticated browser `android_list.handle('list-get')`, including its
  `current` and explicit-batch paths.
- Authorized `handset_list_worker.tick` before calling OCR / app-text
  parsing, for a previously selected and still live device.

Every legacy raw JSONB batch passes through **as the very same original
Python dict** with zero new SQL queries and no extra decoding/encoding.
This avoids perturbing the currently working 10-product/DEGIRO workflow.

A hypothetical future pointer-shaped row is not returned to either
client/worker. The helper instead checks one unexpired source row and an
active, nonrevoked device, locks the source row for a short read, verifies
the exact source pointer JSON equals its token-scoped, original-time
`bob_android_shadow_batch_refs` ledger record, then invokes the
previously isolated `android_image_persistent_shadow._resolve`.
That resolver verifies content-addressed PNG bytes, exact original
encoded image strings, original full-batch SHA-256 and original admission
clock. No current quote timestamp is invented or refreshed.

Pointer/reference mixing, a different device, missing objects, expired
originals, mismatched ledger, corrupted checksums and invalid PNGs **fail
closed**. Browser calls never receive a partially reconstructed batch,
and the OCR worker records a sanitized `read-failed` receipt instead
of handing corrupted evidence to the parser. Public responses never
include SHA-256 keys, SQL exceptions, token hashes, application text or
private object locations.

No new database schema, writer, scheduled worker, environment variable,
public endpoint, account permission, paid service or database port is
created. The existing source batch expiry remains 24 hours. Import
uploads and stored original quote/ISIN/provenance fields are unchanged.

## Remaining release gate before storage is actually reduced

This read-compatible code alone **does not persist a reference** or free
space. The isolated shadow objects of PR #1218 are not installed on
production. Only a separate opt-in change with comprehensive, independently
restored backups of the source **and** object/reference ledgers can enable
a bounded transactional single-batch writer. That pilot must preserve
the original raw image until source and all reader round-trips are
independently confirmed, supply an atomic rollback, verify the 24-hour
expiry and reference garbage collection, estimate scratch/WAL/locks, and
measure physical Render volume before and after. The current archive
receipt for other reviewed evidence is **not** a complete database image
backup and does not authorize deleting screenshots.

No `VACUUM FULL`, unverified source deletion, shorter retention, change
to DEGIRO product calculations or claim of recovered physical space.
