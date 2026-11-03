# Bob: independent recovery key escrow — offline procedure

**Important:** This is an *offline utility*, not an automated live backup.
Its existence in GitHub proves neither that the original secret was copied nor
that offline media has been retained. It does not change Render, Google Drive,
PostgreSQL, automated archives, trading signals or source deletion policy.

## Why this needs a local operator

Bob's encrypted ZIP format derives its historical AES-GCM key from the
**exact original** `PUSH_SERVICE_TOKEN` using the domain separator
`bob-drive-evidence-encryption-v1`. A token rotation before saving the old
secret may permanently lock the old archives. Do not rotate or overwrite it.

The original root must be retained **outside Render, GitHub and Google Drive**.
Currently there is no external secret vault connector or user device export
channel to accomplish this automatically. A second Render variable, a GitHub
CI secret, a chat upload or a Drive file would **not** be independent escrow.

Do not paste this token, a passphrase, or an unencrypted backup into ChatGPT,
email, pull requests, screenshots or logs.

## Offline creation and cryptographic verification

On a private, trusted computer with Python 3 and the project's
`cryptography` dependency installed, obtain a copy of
`bob_offline_key_escrow.py` from a trusted copy of this repository.
Do not execute the procedure on Render or in GitHub Actions.

Obtain the exact original root **privately** from the authorized secret
administrator. If it cannot be read back without rotation, **stop**; do not
substitute a new token, guess the original or delete any originals.

Run locally (the secret is prompted using hidden input, never CLI arguments):

```bash
python bob_offline_key_escrow.py create --output /path/on/offline-media/bob-root.vault
```

Enter the original root twice and a **different**, strong private passphrase
twice. A versioned AES-256-GCM encrypted file is created with a random salt
and nonce, `scrypt` password derivation and exclusive permission `0600`.
No cleartext root file is written. Keep at least two independently accessible
copies of the encrypted file on media under your control; store the passphrase
separately. Losing both the escrow passphrase and the original root means old
archives remain unrecoverable. Do not keep the only copy inside this chat.

From the private automatic original archive folder, use the matching
`bob-evidence-<time>.zip.aesgcm` **and** its matching
`bob-evidence-<time>-verified.json`, downloaded onto the same trusted
offline machine. Never assume an unrelated older plaintext ZIP is sufficient.
Confirm the receipt's exact archive date and scope before proceeding.

```bash
python bob_offline_key_escrow.py verify \
  --escrow /path/on/offline-media/bob-root.vault \
  --archive /path/to/bob-evidence-<time>.zip.aesgcm \
  --receipt /path/to/bob-evidence-<time>-verified.json
```

The verifier unlocks the escrow in memory and authenticates the downloaded
AES-GCM original against the decrypted ZIP SHA-256 recorded in the receipt.
It does **not** write a decrypted ZIP, print a root, contact Render, upload
anything, or perform a new PostgreSQL restore. If the password, archive,
checksum or receipt is wrong, it fails closed. The output deliberately keeps
`independentPostgresRestorePerformed=false` and
`offlineBackupDurabilityVerified=false`: those cannot be proven by code.

For a high assurance disaster-recovery acceptance, **separately** complete a
restore on an independent PostgreSQL instance and verify source-equivalent
data there. Until the operator confirms that durable independent custody and
recovery, Bob's production `recoveryKeyVerified` state must stay false,
no original-reference pilot may start, and no new deletion may be permitted.

## Synthetic tests

`python -m unittest test_bob_offline_key_escrow` uses fake test secrets,
reopens an original AES-GCM archive after active-token rotation, and rejects
a wrong password, corrupted ciphertext, changed archive digest and receipt
that permits deletion. It neither reads production environment variables nor
copies real secrets into GitHub.
