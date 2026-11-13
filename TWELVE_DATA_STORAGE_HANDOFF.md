# Bob – Twelve Data research storage handoff (13 Nov 2026)

**State:** isolated review branch only. No scheduled Twelve Data calls, no paid
services, no live Bob UI data, no real-money trades, no Aiven writes.

## Findings from original connected infrastructure

- Aiven's existing free PostgreSQL restore target is reachable through the
  push service's read-only health canary. The 13 Nov 07:07 UTC sample reported
  9,500,351 bytes, 1/20 client connections, no recorded deadlocks or findings.
  **Host memory/RSS/OOM attribution was not available**. This does NOT qualify
  the same instance for a new research writer or global quota ledger.
- Google Drive contains Bob's private long-term archive and the existing
  app-owned original archive. An additional, currently **empty**, private
  folder for Twelve Data research was created on 13 Nov via the connected
  ChatGPT Google Drive account, under the existing long-term archive.
  Metadata confirms `shared=false` and the intended parent. **This is not
  proof that Bob's different `drive.file` OAuth token can access it.**
  Do not store either Drive folder ID or Google OAuth credentials in this repo.

## Implemented manual safety bridge

`twelve_research_storage_bridge.py`:

1. Reuses the existing Aiven *read-only* `aiven_health.inspect`, reporting
   observed/busy/unverified. It always sets `writesEnabled=false` and
   `readyForQuotaLedger=false` because Aiven RAM/restore isolation are not
   established. No PostgreSQL table or production schema is created.
2. Reuses Bob's existing AES-256-GCM streaming encryption from
   `drive_archive_encryption` and `drive_evidence_archive.GoogleDrive`.
   It can manually upload exactly one **synthetic**, non-vendor canary to a
   separately configured private folder, download the remote bytes, compare
   SHA-256 and decrypt/authenticate them. No vendor bars, indicator outputs,
   API credentials or private strategy data enter the cloud test.
3. In encrypted-store mode reads Bob's existing narrowed Google OAuth
   credentials through a short `default_transaction_read_only=on` database
   connection, then opens the selected research folder through Google's API.
   This is only an access path, **not** a claim that the ChatGPT-created
   folder is accessible to Bob's separate OAuth application.
4. An explicit `BOB_TWELVE_DRIVE_SYNTHETIC_TEST=1` and nonempty
   `BOB_TWELVE_RESEARCH_DRIVE_FOLDER_ID` /
   `BOB_TWELVE_RESEARCH_PRIVATE_PARENT_ID` are mandatory.
   The research folder must not be the existing evidence folder.
   GoogleDrive's standard preflight rejects shared, trashed, non-writable,
   wrong-parent or low-free-space targets. A secret missing/error fails closed.
5. The bridge has no import by Bob startup, cron, scanner, simulation, trading
   signals or push. It is an **operator-invoked CLI**; its return object
   contains status only, never vendor data or credentials. Uploaded
   synthetic samples are not automatically deleted, to preserve evidence
   of the remote roundtrip and avoid accidental Drive deletion.

Use only after the Bob OAuth app truly has access to the research folder and
a human operator can invoke a one-off backend command in an authorized
environment (not GitHub Actions secrets):

```sh
# private runtime env, not committed
BOB_TWELVE_DRIVE_SYNTHETIC_TEST=1
BOB_TWELVE_RESEARCH_DRIVE_FOLDER_ID=(private Drive folder ID)
BOB_TWELVE_RESEARCH_PRIVATE_PARENT_ID=(private archive parent ID)
BOB_ARCHIVE_CREDENTIAL_SOURCE=encrypted-store
# plus already configured production secrets
python twelve_research_storage_bridge.py
```

The CLI **does not use or need a Twelve Data API key**. A valid Bob Google
OAuth connection alone will not make the Twelve Data API authenticated.

## Compliance and next gates

- **Basic permits occasional internal non-display evaluation**, not
  unattended scheduled polling or any displayed vendor bars/derived outputs
  in Bob Handy. XAU/USD 1m/5m/15m/30m/1h/1day permission has written support
  evidence; direct EUR/CHF/CHF/EUR and 4h/8h remain unconfirmed/blocked.
- **Raw vendor data requires an erasure path:** when access ends, all original
  bars and archived copies must be deleted within 30 days. Do not enable
  real-data Drive uploads until an audited, bounded file inventory and
  deletion-verification procedure exists and is tested with synthetic files.
  Current bridge **only accepts synthetic data**.
- **Persistent quota ledger:** existing Twelve Data one-off adapter uses an
  isolated local SQLite ledger. Never describe that as a globally shared
  account quota. Aiven should be considered for a durable ledger only after
  host RAM/restore safety is proven, quota credit weights are verified, and
  exclusive execution is established. Do not write into Bob's Aiven restore
  target by default.
- **Authenticated vendor test:** after verifying the specific Basic usage
  rights, a narrowly authorized single request requires a real API key
  already available in Bob's private runtime. No key has been copied into
  GitHub, messages or this folder; CI uses synthetic requests only.
- **Independent runtime OAuth:** the user's ChatGPT Drive account and Bob's
  deployed Google OAuth app are different connections. If the new folder is
  not visible to Bob's token, use its established app-owned-folder preparation
  protocol and move the new app-owned folder into the private archive before
  trying the one-off test.

Test locally without vendor or cloud network:

```sh
python -m unittest test_twelve_research_storage_bridge \
  test_twelve_research_extension test_gold_fallback
```

Keep PR #1636 **DRAFT, unmerged and undeployed** while these gates remain.
