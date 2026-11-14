# Bob – independent archive-key custody and provider-volume before/after evidence

**Status (07 Nov 2026): NON-PRODUCTION PROCEDURE / draft only.** This
document and `storage_provider_volume_pair.py` do not authorize or execute
maintenance. The code is deliberately **not** imported by Bob's startup,
storage worker, archive worker, simulation scheduler or web endpoints. Do not
enable, reset, replay or alter `BOB_STORAGE_TAIL_RECLAIM_ONCE`, and do not
run any more VACUUM, VACUUM FULL, pg_repack, DELETE or database migration.

## A. What is known, and what is not

The private Bob storage view on 07 Nov 2026 reported a persistently verified
reviewed-evidence archive at `2026-11-07T00:58:15Z` with encryption,
remote-download, separate-DB restore, source-scope and runtime recovery-key
checks true. **This is not a full-database backup.** The status cannot
certify that an offline encrypted vault remains accessible after theft or
loss of a phone, the Render account or a separate passphrase.

**Completed key-recovery evidence (operator-verified, 04–05 Nov):**
The encrypted original root vault created in Samsung Termux was independently
downloaded again from the owner's email and unlocked with the separate vault
passphrase. It yielded the same historical root, authenticated the real
downloaded AES-GCM archive, and matched its recorded original ZIP SHA-256.
The subsequently persisted server archive receipts, including
07 Nov 00:58:15Z, independently report
`recoveryKeyVerified=true`, `remoteDownloadVerified=true`,
`restoreVerified=true` and separate-DB restore isolation. **Do not rerun
these already completed technical recovery checks by default.** This is
real key recovery evidence, not merely a synthetic test.

A more demanding **disaster-proof custody** claim (independent recovery even
after losing the phone *and* email account) would require separately evidenced
off-device custody; two physical offline media have not been confirmed by
accessible records. This is a separate optional resilience acceptance, not a
reason to mark the already completed cryptographic key recovery as failed.
Do not conflate either proof with full-database backup coverage or permission
to migrate/delete originals.

## B. Optional stronger disaster-loss key-custody rehearsal (owner, offline; no repetition required for completed technical proof)

1. Privately confirm the *original* historical archive root is contained in
   the existing encrypted `bob-archive-root.vault`, without opening or
   displaying the root in ChatGPT, GitHub, Render logs, screenshots or email.
   Preserve current secrets untouched. Do not generate a substitute root.
2. Transfer **only the encrypted vault** to at least two independently held
   offline media (e.g. two separately stored USB drives). Keep the vault
   passphrase under separate, recoverable custody. Do not rely solely on an
   emailed copy or phone storage. Do not put the only copy in Google Drive.
3. On a **different trusted computer** without active Render credentials and
   preferably without network access, copy the vault back **from each
   medium separately**. Download the real matching historical
   `bob-evidence-<time>.zip.aesgcm` and
   `bob-evidence-<time>-verified.json` ahead of time; check matching dates
   and exact scope, never substitute another archive.
4. With only the project's trusted `bob_offline_key_escrow.py` and the
   `cryptography` dependency, run for **each media copy**:

   ```bash
   python bob_offline_key_escrow.py verify \
     --escrow /private/usb-copy/bob-archive-root.vault \
     --archive /private/archive/bob-evidence-<time>.zip.aesgcm \
     --receipt /private/archive/bob-evidence-<time>-verified.json
   ```

   Enter the separate vault passphrase into the hidden local prompt only.
   Require `encryptedOriginalAuthenticated=true` and
   `originalSha256Verified=true` on each separately imported copy. The
   tool intentionally reports `offlineBackupDurabilityVerified=false`
   and `independentPostgresRestorePerformed=false`; do not forge or
   override them. If any test fails, preserve all originals and stop.
5. Preserve a **private**, non-secret acceptance record with the two
   independent media/custodians, test date, archive version/scope, and test
   outcomes, *without secret material, archive identifiers, hashes or
   plaintext*. Regularly rehearse after device replacement or vault-medium
   refresh. A tested independent full recovery of the reviewed-evidence
   tables into a disposable isolated database is a **separate future
   authorization**, not part of the current no-SQL-mutation request.
6. A test that does not depend on the active Render `PUSH_SERVICE_TOKEN`
   demonstrates retrieval after hypothetical rotation without actually
   rotating any productive secret. Do **not** rotate for this exercise.
   Production secrets and deletion permissions remain unchanged.

Until additional media custody is independently documented, label only
the **additional disaster-loss resilience** `offline-escrow-custody-unverified`.
The already completed real encrypted-vault/archive recovery remains
`technical-key-recovery-verified`. Do not assert either as a full-DB backup
or use it to override storage/pilot/deletion preflight gates.

## C. Provider-volume snapshots for a *future separately authorized* operation

The existing `render_disk_metrics.report()` queries Render's **physical
disk-usage API** and normalizes explicit units to bytes. CPU, RAM,
`pg_database_size`, TOAST and relation allocations cannot substitute for
a Render-provider volume sample. This code only reads the existing provider
endpoint; it does not change credentials, configuration or service state.

On an already authorized maintenance date, in a trusted environment that
already has legitimate **read-only** Render metric access:

```bash
python -m storage_provider_volume_pair before \
  --id separately-authorized-maintenance-unique-id \
  --receipt /private/bob-volume-pair.json
# Now execute ONLY the independently approved operation, outside this tool.
python -m storage_provider_volume_pair end \
  --receipt /private/bob-volume-pair.json
python -m storage_provider_volume_pair after \
  --receipt /private/bob-volume-pair.json
```

- Run **before** immediately before any operation; it creates a local
  `0600` receipt exclusively. It refuses an existing path or unknown
  units/source/resource. The provider sample must be at most 120 seconds old.
- Run **end** immediately after the *separately controlled* operation,
  capturing the end boundary without connecting to the database.
- Run **after** when the provider has published a genuinely newer sample
  timestamp **after** the end boundary. Render's sampling can lag the
  end time: if `provider-post-sample-not-yet-available` appears, repeat
  the **read-only after command only**, within 15 minutes. Never repeat
  the maintenance action to get a measurement. After that interval,
  leave the result unverified; do not manufacture a matching value.
- Require the exact same resource, provider source, explicit byte units,
  fresh timestamps and two distinguishable observations. The receipt
  records the before/end/after boundaries and measured provider net
  decrease, including **zero** if usage did not fall. Any insufficient
  pair is a **blocker**, not an estimate.
- `physicalVolumeNetDecreaseBytes` is the **net change across the measured
  Render volume**, not a guarantee that a particular table operation
  alone caused it: unrelated concurrent writes can affect the total.
  Accordingly `diskBytesFreedByMaintenance` remains **null** even with
  a positive provider net decrease unless independent attribution is
  subsequently established. Never label relation-size reductions or
  RAM metrics as physically freed bytes.
- Store the final local receipt in private durable operator records; the
  script does **not** upload to Google Drive, GitHub, the Bob DB or Render,
  and does not start or schedule any work. Do not paste secret material into
  a public issue.

## D. Unchanged hard blockers

The 07 Nov weekend tail reclaim claim `reclaim-observations-20261107-v1`
is already consumed. **Do not reset, retry or claim an additional
maintenance operation.** Future approval still requires independently
documented offline key custody, actual WAL/scratch/volume headroom,
lock/statement-timeout checks, a fresh scoped restore proof, and explicit
operator authorization. Only the archived reviewed-evidence-tables are
covered; no evidence or simulation source deletion is licensed by this
document. Pairing measurements does not grant an authorization gate.
