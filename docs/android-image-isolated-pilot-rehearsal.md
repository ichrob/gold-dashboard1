# Isolated PNG CAS + exact rollback rehearsal (no production writer)

## Scope

This module is **strictly a test-only exercise** for the next step of issue
#1231. It has NO startup hook, API endpoint, manual production CLI, environment
switch, scheduled worker or Render deployment action. It is not imported by the
existing Bob Android list handler, OCR worker or maintenance process.

The previous real operator backup from #1222 contains three original images
and has an independently downloaded and matched private AES-GCM archive plus
the service-produced separate-PostgreSQL restore receipt. This does **not**
bind that receipt to every future batch, give permanent object references,
or authorize replacement of any live PostgreSQL source.

## Procedure (fresh isolated PostgreSQL test schema ONLY)

1. A caller creates a *fresh* `png_restore_<32-hex>` schema with the test
   device and source table, and uses `restore_to_isolated_test_schema` with
   an already validated **private in-memory** plaintext recovery bundle to
   populate the original, receipt, processing metadata and object/ref ledger.
   Test fixture data is synthetic, and real PNGs/keys must not be sent to CI.
2. `rehearse_test_schema(conn, blob, sha256)` rejects any other schema before
   interpreting the image contents. It requires an active unrevoked device,
   source age younger than 24 hours, the exact original batch, upload time,
   processing receipt/time/attempts, parsed rows, and existing valid
   device-scoped reference ledger.
3. In a single bounded transaction with short statement/lock limits it does
   one compare-and-swap original-to-pointer update for exactly one batch,
   performs full byte-identical `android_image_readthrough.materialize` and
   authenticated legacy `list-get` logic, then CAS restores the full original
   image payload. It verifies all six original DB fields match the initial
   row before reporting success.
4. Failure at any point rolls back the transaction. Missing objects, revoked
   device, altered metadata or mismatched reference fail closed.
5. Results contain only aggregate flags; no account, device, ISIN, PNG, token,
   object key or batch ID is returned or logged. Test sources are destroyed
   separately by the CI test fixture.

## Explicitly unproven and blocked

This is NOT a production migration. The test does not prove live OCR,
import-status, other SQL writers, 24h object garbage collection, race/reader
locking, permanent backup/restore binding to the **same current batch**,
distinct-operator key escrow, or physical Render disk savings.

The shadow ledger schema still lacks a tested lifecycle for orphan objects
and pointer expiration; no production table will be created until every
consumer, cleanup path, key/device scope and rollback from a **separately
verified encrypted remote archive** is established. In particular, a copy
of object data inside PostgreSQL can initially INCREASE disk use, and a
SQL pointer replacement does not immediately reclaim filesystem space.

No `VACUUM FULL`, shortened screenshot retention, automatic bulk migration,
original deletion, extra paid service or open database IP firewall.
`migrationAuthorized=false`, `deletionAuthorized=false`,
`diskBytesFreed=null` remain nonnegotiable until a separate operator
approval for a production one-batch pilot and physical storage measurement.
