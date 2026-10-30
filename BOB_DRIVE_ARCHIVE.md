# Private evidence archive

Implementation includes an internal worker. Production activation requires
Bob-specific Google OAuth access and a separately provisioned restore server.
The automatic worker never restores into the production database instance. A ChatGPT connector login does not supply runtime credentials.
No production archive is implied by successful synthetic tests.

## Existing worker, separate restore server

`archive_worker` runs inside the existing push service. The source DATABASE_URL
is used only for read-only snapshot export. BOB_ARCHIVE_RESTORE_DATABASE_URL must
point to a different server and a differently named database. Before export,
read-only probes reject equal configured hosts or equal observed server addresses,
including aliases. No credentials or addresses appear in the receipt.

Restoration still creates only session temporary tables, one table at a time,
and rolls back afterwards. These use the separate test server's disk and compute.
PostgreSQL major versions must match. A missing restore connection blocks the
worker before claiming an archive day. No automatic paid provisioning exists.

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
- BOB_ARCHIVE_RESTORE_DATABASE_URL: secure internal URL of the separate test server.
- BOB_ARCHIVE_ENABLED=1 only after target isolation, capacity and credentials are verified.
- BOB_ARCHIVE_WORK_DIRECTORY optionally selects scratch storage (default /tmp/bob-archive).

For encrypted owner consent, set BOB_ARCHIVE_CREDENTIAL_SOURCE=encrypted-store
and BOB_ARCHIVE_PARENT_FOLDER_ID instead of supplying a separate Google JSON.
BOB_ARCHIVE_PREPARE=1 with BOB_ARCHIVE_ENABLED=0 prepares one empty private
app-owned folder using a preallocated persisted ID. Move it through the owner's
Drive connection into the configured private archive parent; Bob verifies the
exact parent and private writable status. Preparation does not export data.

A free Render Postgres instance can support an initial isolated test, but expires
after 30 days. It is not a permanent free restore service. An unavailable test
server fails closed; never silently fall back to production or upgrade the plan.
Google OAuth in Testing also requires review before claiming durable authorization.

The existing 30-minute database samples and 500/700 MB caution/action thresholds
continue. Logical database size does not mean physical free disk space. Preserving
originals means this phase provides external backup, not database reclamation.

## Tests

`python -m unittest test_archive_worker test_evidence_archive test_drive_evidence_archive`
The existing CI PostgreSQL service checks actual COPY restore, same-database TEMP
isolation, exact values, duplicate preservation, corruption rejection and untouched
source rows. Mock tests cover quota failure, remote proof gating and daily claims.
Synthetic success is not proof of production export or restoration.

## Owner Google connection page

`https://bob-private-scanner.onrender.com/archive/connect` requires the existing
Bob browser login and enrolled daily factor. Register the fixed callback
`https://bob-private-scanner.onrender.com/archive/connect/callback` on the Google
**Web application** client. Upload its downloaded JSON using the page's file
picker, never a chat, issue, repository, or email. Endpoint URLs in uploaded JSON
are ignored. The push service stores only Fernet-encrypted configuration in
`bob_settings`, using a domain-separated key derived from its existing runtime
secret. Rotating that secret requires reconnecting Google. Settings are excluded
from evidence exports.

The owner explicitly starts Google consent. Only `drive.file` is requested, with
offline consent, PKCE, ten-minute state bound to the Bob browser session, and
transactional one-use consumption before token exchange. Provider errors and
credentials are redacted. Upload and start require exact Origin and CSRF checks.
No new service, paid resource, email, source deletion or archive activation occurs.
If login expires, log into Bob and reopen `/archive/connect` to restart consent.

This page is the credential bootstrap, not archive activation. The encrypted-store
runtime bridge loads the credentials internally. A folder ID alone does not grant
`drive.file` access; the preparation flow creates an app-owned folder and verifies
its placement. Real production export, remote download and isolated restore must
still pass before reporting a verified archive. Synthetic tests do not prove it.

## Bounded v2 canonicalization

Source COPY performs no SQL sort. The worker sorts escaped COPY records in
2 MiB chunks with a 16 MiB single-record ceiling, then pairwise merges scratch
files. The 512 MiB total raw-byte limit remains enforced; no row is omitted or
truncated to fit. Export and restore use identical byte ordering, preserving
duplicates. Insufficient scratch space, oversized rows or incomplete streams fail
closed. Production never allocates a temporary sort file for this export.

The changed canonical order uses manifest v2. The worker uses a new
`bob_archive_runs_v2` daily claim ledger, retaining the old v1 ledger unchanged
for diagnosis. This allows one corrected v2 attempt after a failed v1 attempt;
failed v2 attempts are not automatically repeated on the same UTC day. Safe
phase names identify export/restore/upload failures without exposing credentials.
