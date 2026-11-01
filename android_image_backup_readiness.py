"""Sanitized, configuration-only status of the manual original PNG backup.

Imported by the private storage report; MUST NEVER open any connection,
touch files, read image rows, run a CLI, or start a background backup.
A configured key is NOT proof of independent escrow or an actual backup.
"""
def report():
    # Keep all potentially sensitive config processing confined to the
    # existing operator-only CLI; project a strict allowlist of booleans.
    try:
        from android_image_backup_cli import configuration
        state = configuration()
        if type(state) is not dict or state.get("status") not in ("ready","blocked"):
            raise ValueError("Invalid readiness")
        credentials = state["status"] == "ready"
        key = state.get("separateEncryptionKeyConfigured") is True
        ack = state.get("acknowledgementConfigured") is True
        return {
            "status": "operator-gated" if credentials else "configuration-incomplete",
            "privateArchiveConfigurationPresent": credentials,
            "imageEncryptionKeyPresent": key,
            "manualOneBatchAcknowledgementConfigured": ack,
            "manualExecutionConfigurationComplete": credentials and key and ack,
            "sourceBatchCurrentlyAvailable": None,
            "privateDrivePreflightVerified": None,
            "independentRestorePreflightVerified": None,
            "remoteOriginalBatchBackupVerified": None,
            "independentOriginalBatchRestoreVerified": None,
            "originalImageMigrationAuthorized": False,
            "originalImageDeletionAuthorized": False,
            "diskBytesFreed": None,
            "readOnly": True,
            "note": "Configuration presence only: no independent key escrow, live image "
                    "availability, remote backup or restore is established by this report."
        }
    except Exception:
        return {
            "status": "not-observed",
            "readOnly": True,
            "remoteOriginalBatchBackupVerified": None,
            "independentOriginalBatchRestoreVerified": None,
            "originalImageMigrationAuthorized": False,
            "originalImageDeletionAuthorized": False,
            "diskBytesFreed": None,
        }


def synced_source_candidate_present(conn):
    """Small, index-friendly existence probe; never read PNG or device IDs.

    This is NOT a source validity/authorization/backup proof. Unknown on
    missing tables, lock contention, error or budget exhaustion.
    """
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='750ms'")
            conn.execute("SET LOCAL lock_timeout='200ms'")
            row=conn.execute("""SELECT EXISTS (
                SELECT 1 FROM bob_android_list_images i
                JOIN bob_android_diagnostic_devices d USING(token_hash)
                WHERE i.created_at > now()-interval '24 hours'
                  AND i.created_at <= now()
                  AND NOT d.revoked AND d.expires_at > now()
                  AND i.import_receipt->>'stage'='synced'
                  AND i.parsed_items IS NOT NULL
                LIMIT 1
            )""").fetchone()
        if (type(row) not in (tuple,list) or len(row)!=1 or
                type(row[0]) is not bool):
            return None
        return row[0]
    except Exception:
        # SQL diagnostics, owners and batch/device values must never escape.
        return None
