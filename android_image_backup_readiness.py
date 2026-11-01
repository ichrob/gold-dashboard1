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
