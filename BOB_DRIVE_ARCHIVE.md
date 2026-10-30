# Private evidence archive

Implementation includes an internal worker and a zero-additional-service restore
mode. Production activation is blocked until Bob-specific Google OAuth access is
securely provisioned. A ChatGPT connector login does not supply runtime credentials.
No production archive is implied by successful synthetic tests.

## Existing services, private access

`archive_worker` runs inside the EXISTING push service using its internal
DATABASE_URL. No new Render service, paid database, external allowlist opening or
cron job is needed. It is disabled by default. On activation it waits five minutes
and claims at most one attempt per UTC day via `bob_archive_runs`. Failed or
interrupted attempts cannot be automatically replayed on the same day. Small
operational receipts are separate from original evidence. `/storage-health`
exposes readiness/current state without secrets.

## Export and restore proof

`evidence_archive.py` exports every row/column of its reviewed evidence allowlist,
including all known paper portfolios, in one REPEATABLE READ, READ ONLY snapshot.
PostgreSQL COPY text retains exact numeric, bytea, timestamp, Unicode and JSON
values. The manifest lists included, absent and excluded tables. Review this
coverage before claiming completeness. OAuth, credentials, passkeys, subscriptions
and sessions are excluded. This is an evidence archive, not a full database
application recovery image: constraints/defaults/indexes/privileges/sequences are
not recreated.

SHA-256 covers the whole ZIP and each table stream; the manifest records ordered
columns/types, row counts, bytes, database size, timestamp and build. The verifier
accepts only validated built-in PostgreSQL types and never executes archived code.
Stable text ordering allows bytewise comparison after PostgreSQL restoration.

The internal worker restores into session-local TEMP tables on the existing server.
It restores, verifies and drops ONE scratch table at a time, always in pg_temp.
This isolates names/data from original tables; it still shares CPU and disk.
Query/lock deadlines, a single daily claim, 512 MiB export limit and scratch-space
checks bound work. Observe real resource impact before relying on ongoing operation.
The standalone verifier rejects same-database restore unless the explicit
`temporary_session=True` option is supplied. PostgreSQL major versions must match.

`drive_evidence_archive.py` verifies that the configured folder is private/writable
and that Drive has known space plus a 256 MiB reserve. It exports, restores locally,
uploads without replacing files, checks uploaded metadata/SHA-256, downloads the
actual remote file, and restores that download again. Only then does it upload a
success receipt. Failure yields no success receipt. Retrying manually may leave
orphan/duplicate Drive copies; never delete those or source records automatically.

Every receipt has `deletionPermitted=false`. No source purge, retention change,
order, email, risk-rule change or paid scaling exists. After a successful remote
restore AND receipt upload, only redundant local ZIP scratch copies are removed.
Failed work remains for diagnosis; disk exhaustion blocks further work safely.
ZIP compression is lossless, not encryption; the Drive folder must remain private.

## Secure activation

Install requirements-archive.txt (included by requirements-push.txt). Configure on
the existing push service through secure environment settings:

- BOB_ARCHIVE_DRIVE_FOLDER_ID: existing private folder (never commit its identity).
- BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON: Google authorized-user JSON including
  refresh token from a separately authorized OAuth client; never put it in chat,
  logs or GitHub. Prefer access scoped to the selected files/folder.
- BOB_ARCHIVE_ENABLED=1 only after valid credentials are configured.
- BOB_ARCHIVE_WORK_DIRECTORY optionally selects scratch storage (default /tmp/bob-archive).

No extra restore database URL is required for internal mode. The standalone CLI
can still use a distinct BOB_ARCHIVE_RESTORE_DATABASE_URL. The worker is not enabled
by this commit. Google client registration and user consent must happen via
Google's supported setup; ChatGPT connector tokens must never be extracted.

The existing 30-minute database samples and 500/700 MB caution/action thresholds
continue. Logical database size does not mean physical free disk space. Preserving
originals means this phase provides external backup, not database reclamation.

## Tests

`python -m unittest test_archive_worker test_evidence_archive test_drive_evidence_archive`
The existing CI PostgreSQL service checks actual COPY restore, same-database TEMP
isolation, exact values, duplicate preservation, corruption rejection and untouched
source rows. Mock tests cover quota failure, remote proof gating and daily claims.
Synthetic success is not proof of production export or restoration.
