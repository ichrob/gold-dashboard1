"""Offline/read-only binding of ONE private PNG archive to ONE current source.

This is a testable gate, NOT a production migration controller. Caller must
independently authenticate the private Drive download and receipt. No network,
shell, production image writer, secret logging, scheduler or startup import.
"""
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

import android_image_backup_prepare as prep
import android_image_recovery_bundle as recovery
import android_image_persistent_shadow as shadow

_ID = re.compile(r"[A-Za-z0-9_-]{10,200}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "version", "status", "verifiedAt", "archiveDriveFileId",
    "encryptedSha256", "encryptedBytes", "originalBundleSha256",
    "encryptionVerified", "remoteDownloadVerified",
    "independentServerVerified", "fullBatchRoundTripVerified",
    "allReferencesVerified", "sourcePreserved", "restoredImages",
    "sourceModified", "imageMigrationAuthorized", "deletionAuthorized",
    "diskBytesFreed",
})


def verify_current_source_binding(conn, receipt_bytes, ciphertext, key,
                                  archive_file_id, batch_id, device_scope,
                                  *, now=None):
    """Prove one downloaded original equals the currently authorized source.

    The receipt is a PRIVATE Drive record previously verified by the caller.
    This function checks exact receipt/ciphertext/source identity. It cannot
    prove remote download provenance, restore-server separation, WAL budget,
    other readers, GC safety, or a future authorization to migrate.
    """
    try:
        shadow._require_ids(batch_id, device_scope)
        if (type(receipt_bytes) is not bytes or
                not 0 < len(receipt_bytes) <= 4096 or
                type(ciphertext) is not bytes or
                not 0 < len(ciphertext) <= prep._MAX_CIPHER or
                type(key) is not bytes or len(key) != 32 or
                type(archive_file_id) is not str or
                not _ID.fullmatch(archive_file_id)):
            raise ValueError("Invalid protected archive input")

        receipt = json.loads(receipt_bytes)
        if (type(receipt) is not dict or
                frozenset(receipt) != _FIELDS or
                json.dumps(receipt,sort_keys=True,separators=(",",":"),
                           ensure_ascii=False).encode() != receipt_bytes or
                receipt.get("version") != "bob-private-image-recovery-receipt-v1" or
                receipt.get("status") != "independent-encrypted-original-verified" or
                receipt.get("archiveDriveFileId") != archive_file_id or
                type(receipt.get("encryptedBytes")) is not int or
                receipt["encryptedBytes"] != len(ciphertext) or
                type(receipt.get("restoredImages")) is not int or
                not 1 <= receipt["restoredImages"] <= 4):
            raise ValueError("Untrusted archived image receipt")
        for name in ("encryptionVerified", "remoteDownloadVerified",
                     "independentServerVerified", "fullBatchRoundTripVerified",
                     "allReferencesVerified", "sourcePreserved"):
            if receipt.get(name) is not True:
                raise ValueError("Incomplete image restore attestation")
        for name in ("sourceModified", "imageMigrationAuthorized",
                     "deletionAuthorized"):
            if receipt.get(name) is not False:
                raise ValueError("Original not protected")
        if receipt.get("diskBytesFreed") is not None:
            raise ValueError("Invalid physical savings assertion")

        cipher_sha = receipt.get("encryptedSha256")
        source_sha = receipt.get("originalBundleSha256")
        if (type(cipher_sha) is not str or not _SHA.fullmatch(cipher_sha)
                or type(source_sha) is not str or not _SHA.fullmatch(source_sha)
                or not hmac.compare_digest(
                    hashlib.sha256(ciphertext).hexdigest(),cipher_sha)):
            raise ValueError("Encrypted image hash mismatch")

        verified = datetime.fromisoformat(receipt["verifiedAt"])
        checked = datetime.now(timezone.utc) if now is None else now
        if (not isinstance(checked,datetime) or checked.tzinfo is None
                or verified.tzinfo is None or
                not 0 <= (checked-verified).total_seconds() < 86400):
            raise ValueError("Archive verification age invalid")

        decrypted = prep.open_sealed_bundle(ciphertext,cipher_sha,source_sha,key)
        manifest = recovery.validate_recovery_bundle(decrypted,source_sha)
        upload = datetime.fromisoformat(manifest["uploadedAt"])
        if (manifest["batchId"] != batch_id or
                manifest["deviceScope"] != device_scope or
                receipt["restoredImages"] != len(manifest["original"]["images"]) or
                verified < upload):
            raise ValueError("Archive belongs to a different original")

        # This read is device-bound, non-revoked and less than 24h old,
        # and its deterministic source package includes every image,
        # uploaded time, import receipt, parsed list and processing clock.
        current_blob,current_sha = prep.pack_active_source_readonly(
            conn,batch_id,device_scope)
        if (not hmac.compare_digest(current_sha,source_sha) or
                not hmac.compare_digest(current_blob,decrypted)):
            raise ValueError("Active source no longer matches archived original")
        return {
            "status":"exact-active-original-binding-verified",
            "sourceBatchMatchesArchive":True,
            "deviceScopeMatchesArchive":True,
            "originalAndMetadataUnchanged":True,
            "imageCount":receipt["restoredImages"],
            "readOnly":True,
            "independentRemoteDownloadReverifiedHere":False,
            "independentServerRestoreReverifiedHere":False,
            "keyEscrowVerified":False,
            "productionMigrationAuthorized":False,
            "originalDeletionAuthorized":False,
            "diskBytesFreed":None,
        }
    except Exception:
        # Always suppress all receipt/PNG/connection/key details.
        raise ValueError("Private original image binding not verified") from None
