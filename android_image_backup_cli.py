"""Operator-only CLI for ONE encrypted original PNG backup.

NO startup import, environment-only trigger, HTTP route or scheduler. An
authorized operator must explicitly run the exact acknowledged command inside
the existing private Bob service, with a separately escrowed encryption key.
Status/preflight are read-only. Execution never updates/deletes image rows.
"""
import json
import os
import re
import sys

_USAGE = ("Usage: python -m android_image_backup_cli "
          "status | preflight | execute --acknowledge-one-batch-only")
_REDACTED = frozenset({"ready", "blocked", "no-active-image", "source-not-observed",
                       "preflight-verified", "verified", "failed"})
_ERROR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}\Z")
_READ_OPTIONS = "-c default_transaction_read_only=on -c statement_timeout=4000 -c lock_timeout=500"


def configuration():
    """Presence only. Never return values, tokens, URLs or batch identifiers."""
    required = ("DATABASE_URL", "BOB_ARCHIVE_RESTORE_DATABASE_URL")
    missing = [name for name in required if not os.environ.get(name)]
    stored = os.environ.get("BOB_ARCHIVE_CREDENTIAL_SOURCE") == "encrypted-store"
    if stored:
        if not os.environ.get("BOB_ARCHIVE_PARENT_FOLDER_ID"):
            missing.append("BOB_ARCHIVE_PARENT_FOLDER_ID")
    else:
        for name in ("BOB_ARCHIVE_DRIVE_FOLDER_ID",
                     "BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON"):
            if not os.environ.get(name):
                missing.append(name)
    key = os.environ.get("BOB_PNG_BACKUP_KEY_HEX", "")
    has_key = bool(re.fullmatch("[0-9a-fA-F]{64}", key))
    return {"status": "blocked" if missing else "ready",
            "missingConfiguration": missing,
            "separateEncryptionKeyConfigured": has_key,
            "acknowledgementConfigured": os.environ.get(
                "BOB_PNG_BACKUP_EXPLICIT_ACK") == "one-batch-only",
            "productionImageMutationEnabled": False,
            "deletionAuthorized": False}


def _latest_batch(source_dsn):
    """Select one completed, current, active private device source by index.

    Never print or persist the batch/device identifiers. A missing completed
    batch blocks the manual backup rather than exporting a partial capture.
    """
    import psycopg
    with psycopg.connect(source_dsn, connect_timeout=10,
                         application_name="bob_png_cli_select_readonly",
                         options=_READ_OPTIONS) as conn:
        conn.execute("SET LOCAL statement_timeout='3s'")
        conn.execute("SET LOCAL lock_timeout='500ms'")
        row = conn.execute("""SELECT i.batch_id,i.token_hash
            FROM bob_android_list_images i
            JOIN bob_android_diagnostic_devices d USING(token_hash)
            WHERE i.created_at>now()-interval '24 hours'
              AND i.created_at<=now() AND NOT d.revoked AND d.expires_at>now()
              AND i.import_receipt->>'stage'='synced'
              AND i.parsed_items IS NOT NULL
            ORDER BY i.created_at DESC,i.batch_id DESC LIMIT 1""").fetchone()
    if not row:
        raise LookupError("No active complete image batch")
    from android_image_persistent_shadow import _require_ids
    if type(row) not in (tuple,list) or len(row) != 2:
        raise ValueError("Invalid private source selection")
    _require_ids(row[0], row[1])
    return row


def _drive():
    """Reuse Bob's existing private archive connector; no new Google consent."""
    if os.environ.get("BOB_ARCHIVE_CREDENTIAL_SOURCE") == "encrypted-store":
        from archive_runtime import drive_client
        from archive_worker import metadata_db
        return drive_client(metadata_db)
    from drive_evidence_archive import GoogleDrive
    return GoogleDrive()


def _preflight():
    cfg = configuration()
    if cfg["status"] != "ready":
        return {"status": "blocked", "missingConfiguration": cfg["missingConfiguration"],
                "separateEncryptionKeyConfigured": cfg["separateEncryptionKeyConfigured"]}
    from drive_evidence_archive import verify_restore_isolation
    from android_image_backup_prepare import _MAX_CIPHER
    if verify_restore_isolation(os.environ["DATABASE_URL"],
                                os.environ["BOB_ARCHIVE_RESTORE_DATABASE_URL"]) != "separate-database-instance":
        raise ValueError("Independent restore target unavailable")
    _drive().preflight(_MAX_CIPHER)
    try:
        _latest_batch(os.environ["DATABASE_URL"])
    except LookupError:
        return {"status": "no-active-image",
                "separateEncryptionKeyConfigured": cfg["separateEncryptionKeyConfigured"]}
    return {"status": "preflight-verified", "sourceAvailable": True,
            "independentRestoreTargetAccessible": True,
            "privateDriveWritable": True,
            "separateEncryptionKeyConfigured": cfg["separateEncryptionKeyConfigured"],
            "imageBackupExecuted": False, "deletionAuthorized": False}


def _execute():
    cfg = configuration()
    if (cfg["status"] != "ready" or
            not cfg["separateEncryptionKeyConfigured"] or
            not cfg["acknowledgementConfigured"]):
        return {"status": "blocked", "imageBackupExecuted": False,
                "deletionAuthorized": False}
    key = bytes.fromhex(os.environ["BOB_PNG_BACKUP_KEY_HEX"])
    from android_image_backup_runner import run_once
    batch_id, scope = _latest_batch(os.environ["DATABASE_URL"])
    result = run_once(os.environ["DATABASE_URL"],
                      os.environ["BOB_ARCHIVE_RESTORE_DATABASE_URL"],
                      _drive(), key, batch_id, scope)
    if (result.get("status") != "independent-encrypted-original-verified" or
            result.get("deletionAuthorized") is not False or
            any(result.get(name) is not True for name in (
                "sourcePreserved", "encryptionVerified",
                "remoteDownloadVerified", "independentServerVerified",
                "fullBatchRoundTripVerified", "allReferencesVerified"))):
        raise ValueError("Private remote proof insufficient")
    return {"status": "verified", "imageBackupExecuted": True,
            "encryptionVerified": True,
            "remoteDownloadVerified": True,
            "independentServerVerified": True,
            "fullBatchRoundTripVerified": True,
            "sourcePreserved": True,
            "deletionAuthorized": False,
            "diskBytesFreed": None}


def main(argv=None):
    args = tuple(sys.argv[1:] if argv is None else argv)
    if args not in (("status",), ("preflight",),
                    ("execute", "--acknowledge-one-batch-only")):
        print(_USAGE)
        return 2
    try:
        outcome = (configuration() if args[0] == "status" else
                   _preflight() if args[0] == "preflight" else
                   _execute())
        if outcome.get("status") not in _REDACTED:
            raise ValueError("Unsafe status")
        print(json.dumps(outcome, sort_keys=True))
        return 0 if outcome["status"] not in ("blocked", "failed", "no-active-image") else 3
    except Exception as error:
        # Never include credentials, SQL, hashes, batch/session IDs, app text,
        # PNGs, or private Drive URLs in logs or stdout.
        kind = type(error).__name__
        print(json.dumps({"status": "failed", "errorType":
                          kind if _ERROR.fullmatch(kind) else "Error",
                          "imageBackupExecuted": False,
                          "deletionAuthorized": False,
                          "diskBytesFreed": None}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
