"""Isolated, manually invoked PNG recovery preparation and authenticated sealing.

No application import/hook, worker, endpoint, schedule, Drive upload, production
DDL, image replacement, deletion, or restore. Sensitive source + key never log.
A complete external verified backup still requires a separately approved runner.
"""
import gzip
import hashlib
import re
import secrets

import android_image_recovery_bundle as recovery
import android_image_reference_codec as codec
import android_image_persistent_shadow as shadow
import android_list

_PREFIX = b"BOB-ANDROID-PNG-R1\x00"
_NONCE_SIZE = 12
_KEY_SIZE = 32
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_MAX_CIPHER = recovery._BLOB_LIMIT + len(_PREFIX) + _NONCE_SIZE + 16


def pack_active_source_readonly(conn, batch_id, device_scope):
    """Read ONE active owner-bound original, deriving its ledger only in RAM.

    Unlike the earlier isolated-shadow encoder, this does not require
    production shadow tables. It preserves all original source fields and
    captures prospective reference/object data in the same bounded package.
    """
    shadow._require_ids(batch_id, device_scope)
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='5s'")
            conn.execute("SET LOCAL lock_timeout='1000ms'")
            row = conn.execute("""SELECT i.created_at,i.payload,i.import_receipt,
                i.parsed_items,i.processing_at,i.processing_attempts
                FROM bob_android_list_images i
                JOIN bob_android_diagnostic_devices d USING(token_hash)
                WHERE i.batch_id=%s AND i.token_hash=%s
                  AND NOT d.revoked AND d.expires_at>now()
                  AND i.created_at>now()-interval '24 hours'
                  AND i.created_at<=now()""",
                (batch_id, device_scope)).fetchone()
            if not row or len(row) != 6:
                raise ValueError("Active original unavailable")
            uploaded, original, receipt, items, processed, attempts = row
            if (type(original) is not dict or
                    not hasattr(uploaded, 'isoformat') or
                    uploaded.tzinfo is None or
                    processed is not None and
                    (not hasattr(processed, 'isoformat') or processed.tzinfo is None)):
                raise ValueError("Invalid original source metadata")
            if len(recovery._canonical(original)) > shadow._MAX_BATCH_JSON:
                raise ValueError("Original exceeds bounded export")
            android_list.validate(original, uploaded.timestamp())
            pointers, objects = codec.pack_batch(original, device_scope)
            manifest = {
                'format': recovery._FORMAT,
                'deviceScope': device_scope,
                'batchId': batch_id,
                'uploadedAt': uploaded.isoformat(),
                'original': original,
                'sourceMetadata': {
                    'importReceipt': receipt, 'parsedItems': items,
                    'processingAt': processed.isoformat() if processed else None,
                    'processingAttempts': attempts
                },
                'reference': pointers,
                'objects': [{'key': key, 'encodedPng': value}
                            for key, value in sorted(objects.items())],
                'originalSha256': hashlib.sha256(
                    recovery._canonical(original)).hexdigest()
            }
            recovery._validate_payload(manifest)
            raw = recovery._canonical(manifest)
            if len(raw) > recovery._RAW_LIMIT:
                raise ValueError("Raw recovery package too large")
            blob = gzip.compress(raw, mtime=0)
            if len(blob) > recovery._BLOB_LIMIT:
                raise ValueError("Compressed recovery package too large")
            digest = hashlib.sha256(blob).hexdigest()
            recovery.validate_recovery_bundle(blob, digest)
            return blob, digest
    except Exception:
        # Never echo database errors, PNGs, token hashes or app text.
        raise ValueError("Private image source backup unavailable") from None


def seal_bundle(blob, digest, key):
    """Authenticated ciphertext for an approved external private archive.

    key: 32 random bytes from a separate runtime secret. Not derived from
    OAuth/Push tokens and NEVER stored alongside the encrypted archive.
    """
    if type(key) is not bytes or len(key) != _KEY_SIZE:
        raise ValueError("Private image encryption key unavailable")
    recovery.validate_recovery_bundle(blob, digest)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(_NONCE_SIZE)
    cipher = _PREFIX + nonce + AESGCM(key).encrypt(nonce, blob, _PREFIX)
    if len(cipher) > _MAX_CIPHER:
        raise ValueError("Sealed backup exceeds bounded size")
    return cipher, hashlib.sha256(cipher).hexdigest()


def open_sealed_bundle(cipher, cipher_sha256, original_sha256, key):
    """Integrity-check and decrypt ONLY inside a protected restore process.

    Returns the compressed sensitive original; never a public response.
    """
    if (type(key) is not bytes or len(key) != _KEY_SIZE or
            type(cipher) is not bytes or not 0 < len(cipher) <= _MAX_CIPHER or
            type(cipher_sha256) is not str or not _SHA256.fullmatch(cipher_sha256) or
            type(original_sha256) is not str or not _SHA256.fullmatch(original_sha256) or
            hashlib.sha256(cipher).hexdigest() != cipher_sha256 or
            not cipher.startswith(_PREFIX) or
            len(cipher) <= len(_PREFIX) + _NONCE_SIZE + 16):
        raise ValueError("Private image encrypted backup invalid")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        start = len(_PREFIX)
        nonce = cipher[start:start + _NONCE_SIZE]
        blob = AESGCM(key).decrypt(nonce, cipher[start + _NONCE_SIZE:], _PREFIX)
        recovery.validate_recovery_bundle(blob, original_sha256)
        return blob
    except Exception:
        # No caller-supplied object locations or authentication details.
        raise ValueError("Private image encrypted backup invalid") from None
