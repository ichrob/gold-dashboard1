# Private evidence archive — prepared, not activated

The existing private Drive folder is configured using `BOB_ARCHIVE_DRIVE_FOLDER_ID`;
its identity must not be committed to this public repository.
The ChatGPT Drive connection is usable by the connector, but does not provision
OAuth credentials to a Render process. No runtime credentials, scheduler, new
service, plan change or production export are installed by this change.

## Safety and scope

`evidence_archive.py` exports an explicitly reviewed table allowlist and all known
paper portfolio tables. It captures every row and every column of those tables
in one PostgreSQL REPEATABLE READ, READ ONLY transaction, using PostgreSQL COPY
text (not lossy Python float/JSON conversion). The manifest lists included,
absent and excluded tables. Review those lists before claiming complete coverage.
Credentials, sessions, passkeys, OAuth and subscription tables are excluded.
This is an evidence archive, not a full application/database disaster-recovery
backup: constraints, defaults, sequences, privileges and indexes are not restored.

The ZIP has an external SHA-256; each table has a SHA-256, row count, byte count,
and ordered column/type definitions. Stable PostgreSQL text ordering permits
exact comparison after restore, including duplicate records, bytea, Unicode,
NULLs, timestamps and arbitrary precision numbers. Restore uses only validated
built-in types and temporary tables in a separately named isolated test database.
It never executes archived Python or arbitrary SQL. All temporary objects are
rolled back. A valid file checksum alone is NOT a successful restoration.

`drive_evidence_archive.py` runs the sequence:

1. Verify the fixed folder is private and writable and Drive has known capacity.
2. Export a consistent snapshot with a 512 MiB uncompressed budget, bounded
   query/lock timeouts and a local free-space check. Abort without a final ZIP
   if a table is unsupported, export is incomplete, or budget is exceeded.
3. Restore locally into the isolated test database; compare every table bytewise.
4. Upload the ZIP without replacing existing files; check metadata and SHA-256.
5. Download the actual uploaded file and run the full PostgreSQL restore again.
6. Upload a success receipt only after that remote round trip succeeds. It records
   archive/file identity, counts, timestamps, logical database size and Drive quota.

Every receipt explicitly has `deletionPermitted=false`. There is NO source delete,
purge, truncation, retention change, order, email or risk-rule mutation. Failed
uploads or verification produce no success receipt. Local files and any partial
Drive copies are retained for diagnosis; retries can create duplicates and must
be reconciled before scheduling. ZIP compression is lossless, not encryption;
only the verified private folder is used.

The existing `storage_budget.py` continues its 30-minute samples and database
500 MB caution / 700 MB action thresholds. The archive runner also checks Drive
quota and reserves 256 MiB. Database bytes are logical size, NOT physical free
space. No paid scaling or upgrade occurs. Because originals remain in the database,
this phase provides a verified external copy, not database space reclamation.

## Activation prerequisites (still outstanding)

- An existing authorized execution environment with internal production DB access.
  Do not open Render's external database allowlist to enable this task.
- An isolated existing PostgreSQL test database with a distinct database name,
  sufficient scratch space, and the same supported PostgreSQL major version.
  Do not create a paid Render database/service.
- Bob-specific Google OAuth authorization stored securely as
  `BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON` (authorized-user JSON with refresh
  token), scoped to the selected file/folder where possible. Never obtain or
  print ChatGPT connector tokens, and never put credentials in GitHub/chat.
- `DATABASE_URL`, `BOB_ARCHIVE_RESTORE_DATABASE_URL`, and
  `BOB_ARCHIVE_WORK_DIRECTORY` in that execution environment; install
  `requirements-archive.txt` there, not in either running service by default.

Run `python drive_evidence_archive.py` for one bounded trial. CLI output redacts
failure details. Inspect the local manifest and actual downloaded-archive restore
receipt. Only after a real successful run, complete coverage review, idempotent
retry handling and observed resource use may a recurring run be enabled on an
existing no-additional-cost runner. This commit intentionally installs no cron.
A future deletion policy requires separately reviewed per-record export coverage
and proof that mutable/new rows are never removed using an older snapshot.

## Verification

`python -m unittest test_evidence_archive test_drive_evidence_archive`
The PostgreSQL integration test runs in the existing CI PostgreSQL 18 service via
`BOB_TEST_DATABASE_URL`. Synthetic test success is not a production archive proof.
