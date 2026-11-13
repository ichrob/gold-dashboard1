# Future-only history manifest scope in reviewed-evidence archives

**07.11.2026 – DRAFT, no merge, no deployment, no real archive or restore run.**

## Problem isolated by #1329

The current `evidence_archive` export already includes `bob_diagnostic_history`
and `bob_decision_audit`, but not the two evaluation tables
`bob_history_eval_segments` and `bob_history_eval_cursor`. Therefore,
historical SHA page manifests and the durable end cursor are not carried in
the same reviewed-evidence ZIP as original source snapshots. A successful
source restore alone cannot bind those independently generated evaluations
to the exact archive capture.

## Prepared future-only change

The existing fixed, reviewed-evidence table allowlist gains **only** those
two evaluation tables. The existing exporter still uses the same single
`REPEATABLE READ READ ONLY` snapshot for source rows and all present manifest
tables. Existing manifest format v3, compression/encryption, Drive path,
restore identity, file/segment hashes, missing-table accounting, source
retention, SQL limits and `deletionPermitted=false` remain unchanged.

The evaluation tables include original identifier references and timestamps
inside the **privately encrypted source backup**. They are not logged to
GitHub, exposed in a public report, or sent to a new service.

A CI-only synthetic PostgreSQL scenario verifies that a newly generated
private test ZIP includes all four tables, the same export record counts,
and that the existing temporary-table restore reproduces them while source
rows remain unchanged. This does not touch any live credentials, Render
resource, Google Drive backup, or actual archived original.

## Explicit limits

- Past ZIP archives and their immutable receipts **are not modified**. A
  missing historic original prefix cannot be reconstructed merely by
  including a manifest in future snapshots.
- A manifest exported with its source snapshot is valuable evidence, but
  **does not by itself prove** full temporal coverage, file-to-batch identity,
  independently replayed historical rows, Reader equality, or Rollback.
- A future archive attempt/restore would be a **new productive storage
  operation and is forbidden** until a separate, explicit operator approval
  under the 07.11.2026 security hold. This DRAFT is not permission.
- Earlier Termux/email key recovery and actual AES-GCM digest check remain
  **successful** and must not be repeated.
- No new costs, network openings, VACUUM, pg_repack, DELETE, archive retries,
  schema/index changes, source replacement, service restart or real orders.

**Even after a future test passes, keep** `fullOriginalReplayVerified=false`,
`deletionAuthorized=false`, `physicalBytesFreed=null` until separate,
batch-specific evidence is obtained.
