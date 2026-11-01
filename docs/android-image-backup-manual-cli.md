# Manual operator path for a real one-batch PNG original backup

This module is a deliberate execution boundary **not connected to Bob
startup, Render deployment, HTTP APIs, GitHub Actions or the archive scheduler**.
Deploying this file alone cannot read, upload, replace or delete a production
image. No one-shot service is created and no scheduled work is installed.

## Existing approved facilities

The existing scanner/push services are already deployed, the existing private
Google Drive evidence archive is configured, and the separate
`bob-archive-restore-test` PostgreSQL instance is available. These are
**necessary but not sufficient** for a verified image archive.

`android_image_backup_cli` supplies three EXACT operator commands:

- `python -m android_image_backup_cli status` — configuration *presence*
  only; no network or SQL.
- `python -m android_image_backup_cli preflight` — read-only separation,
  private writable Drive quota and an already synchronized, authorized,
  younger-than-24h PNG batch. No image contents are read/exported.
- `python -m android_image_backup_cli execute --acknowledge-one-batch-only`
  — runs the previously reviewed manual runner, after all gates below.

The commands are intended for an **authorized terminal on the existing private
push service**, never GitHub Actions or a remote external database client.
There is no Render MCP shell-action; ordinary connector access to Render does
not execute this command.

## Execution requirements

1. Existing `DATABASE_URL`, `BOB_ARCHIVE_RESTORE_DATABASE_URL` and
   existing private Drive credential configuration. Prefer
   `BOB_ARCHIVE_CREDENTIAL_SOURCE=encrypted-store` with the configured
   `BOB_ARCHIVE_PARENT_FOLDER_ID` rather than duplicating Google tokens.
2. Separately created, **independently recoverable and securely escrowed**
   random AES-256 key stored as the Render protected environment secret
   `BOB_PNG_BACKUP_KEY_HEX` (64 hex characters). Do **not** put the key
   in chat, GitHub, public logs, Drive receipts, command arguments or screenshots.
   A key stored only on Render is insufficient for disaster recovery.
3. An intentionally configured exact `BOB_PNG_BACKUP_EXPLICIT_ACK=one-batch-only`
   **and** the explicit acknowledged terminal argument. Neither variable
   causes any automatic execution. Execute only after the operator validates
   the device/scope, the private Drive folder and the independent restore
   server; `preflight` must succeed without revealing identifiers.
4. Existing protected source/runtime access and free memory/scratch capacity.
   The backend enforces max 18 MiB compressed source and AES-GCM checksum,
   mode-0600 local ciphertext files, Drive 256-MiB reserve,
   independent-source/target database host checks, and 24-hour source validity.
5. The latest authorized `synced` screenshot batch must have saved parsed
   items. The query fetches **only one** batch+device identity in a
   short read-only query; it never discloses identifiers via CLI output.
   Missing or incomplete batches fail closed. Changing image contents or
   processing metadata during the upload fails the final source-recheck.
6. The independent server restores all original bytes, metadata and
   SHA-256-scoped references to a temporary randomly named schema and rolls
   the schema back. A private Drive receipt is uploaded and re-downloaded
   only **after** remote ciphertext integrity, authenticated decryption,
   entire original roundtrip and final source recheck are proven.

The CLI intentionally returns only fixed statuses and boolean proof fields.
A failed attempt may leave an **encrypted private orphan** in Drive;
never silently delete it or claim success. This is still an explicit
manual action: do not automate repeated runs. A read-compatible,
atomic, reversible **production reference writer** remains a separate,
not-yet-approved project. Even a successful image backup does **not**
authorize modifying or deleting original evidence. Physical Render
space freed remains unknown until a separate measured safe migration.

## Operator-blocking reasons

- A Render MCP integration with only service/deploy/environment controls
  cannot launch an arbitrary terminal command.
- A ChatGPT Google Drive connection does **not** supply the running Bob
  process with new encryption secrets.
- No AES key may be invented in source or committed to GitHub.
- A "success" from CI mocks is *not* an actual independent encrypted Drive
  + PostgreSQL restore proof.
- A backup kept only in Render's own environment without independently
  recoverable key custody is not disaster-recovery-ready.

Related: #1222, #1001, #1224.
