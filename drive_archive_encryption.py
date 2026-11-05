"""Streaming authenticated encryption for private Google Drive evidence ZIPs.

Opt-in only. No original deletion, plaintext Drive upload, secret logging,
additional network destination, or whole-archive RAM buffering. The existing
PUSH_SERVICE_TOKEN is the long-lived root for the separately domain-separated
encryption key; rotating it WITHOUT preserving the former secret makes old
encrypted archives impossible to restore.
"""
import hashlib
import os
from pathlib import Path

MAGIC = b"BOBAES01"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024
FORMAT = "aes-256-gcm-stream-v1"
OVERHEAD = len(MAGIC) + NONCE_SIZE + TAG_SIZE
MAX_PLAINTEXT_BYTES = 512 * 1024 * 1024


def _key(key_name="PUSH_SERVICE_TOKEN"):
    # Explicit recovery path only. Never silently try a different key on upload.
    if key_name not in ("PUSH_SERVICE_TOKEN", "BOB_ARCHIVE_RECOVERY_ROOT_TOKEN"):
        raise ValueError("Unsupported archive key source")
    root = os.environ.get(key_name, "")
    if type(root) is not str or len(root) < 32 or len(root) > 4096:
        raise ValueError("Private archive encryption key unavailable")
    return hashlib.sha256(
        b"bob-drive-evidence-encryption-v1\x00" + root.encode("utf-8")
    ).digest()


def seal(source, destination, expected_sha256):
    """Encrypt with random AES-GCM nonce, authenticate version and source."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    src, dst = Path(source), Path(destination)
    if src.resolve() == dst.resolve():
        raise ValueError("In-place archive encryption prohibited")
    size = src.stat().st_size
    if not 0 < size <= MAX_PLAINTEXT_BYTES:
        raise ValueError("Archive outside encryption byte budget")
    if type(expected_sha256) is not str or len(expected_sha256) != 64:
        raise ValueError("Original archive digest unavailable")
    nonce = os.urandom(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(_key()), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    original_hash, ciphertext_hash = hashlib.sha256(), hashlib.sha256()
    header = MAGIC + nonce
    try:
        with open(src, "rb") as stream, open(dst, "xb") as encrypted:
            os.chmod(dst, 0o600)
            encrypted.write(header)
            ciphertext_hash.update(header)
            copied = 0
            while block := stream.read(CHUNK_SIZE):
                copied += len(block)
                if copied > MAX_PLAINTEXT_BYTES:
                    raise ValueError("Archive grew during encryption")
                original_hash.update(block)
                piece = encryptor.update(block)
                encrypted.write(piece)
                ciphertext_hash.update(piece)
            final = encryptor.finalize()
            if final:
                encrypted.write(final)
                ciphertext_hash.update(final)
            tag = encryptor.tag
            encrypted.write(tag)
            ciphertext_hash.update(tag)
        if copied != size or original_hash.hexdigest() != expected_sha256:
            raise ValueError("Source archive changed before encryption")
    except Exception:
        dst.unlink(missing_ok=True)
        raise
    return {"format": FORMAT, "ciphertextSha256": ciphertext_hash.hexdigest(),
            "plaintextSha256": expected_sha256, "ciphertextBytes": dst.stat().st_size}


def unseal(source, destination, expected_sha256, *, recovery=False):
    """Reject modified ciphertext before any restore or acceptance receipt."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.exceptions import InvalidTag
    if type(recovery) is not bool:
        raise ValueError("Invalid recovery selector")
    src, dst = Path(source), Path(destination)
    if src.resolve() == dst.resolve():
        raise ValueError("In-place archive decryption prohibited")
    size = src.stat().st_size
    if not OVERHEAD < size <= MAX_PLAINTEXT_BYTES + OVERHEAD:
        raise ValueError("Encrypted archive outside byte budget")
    if type(expected_sha256) is not str or len(expected_sha256) != 64:
        raise ValueError("Archive proof digest unavailable")
    plain_hash = hashlib.sha256()
    try:
        with open(src, "rb") as ciphertext:
            header = ciphertext.read(len(MAGIC) + NONCE_SIZE)
            if len(header) != len(MAGIC) + NONCE_SIZE or not header.startswith(MAGIC):
                raise ValueError("Unsupported encrypted archive format")
            ciphertext.seek(-TAG_SIZE, os.SEEK_END)
            tag = ciphertext.read(TAG_SIZE)
            ciphertext.seek(len(MAGIC) + NONCE_SIZE)
            decryptor = Cipher(
                algorithms.AES(_key("BOB_ARCHIVE_RECOVERY_ROOT_TOKEN" if recovery else "PUSH_SERVICE_TOKEN")),
                modes.GCM(header[len(MAGIC):], tag)
            ).decryptor()
            decryptor.authenticate_additional_data(MAGIC)
            remaining = size - OVERHEAD
            with open(dst, "xb") as plain:
                os.chmod(dst, 0o600)
                while remaining:
                    block = ciphertext.read(min(CHUNK_SIZE, remaining))
                    if not block:
                        raise ValueError("Truncated encrypted archive")
                    remaining -= len(block)
                    chunk = decryptor.update(block)
                    plain.write(chunk)
                    plain_hash.update(chunk)
                try:
                    final = decryptor.finalize()
                except InvalidTag as error:
                    raise ValueError("Encrypted archive authentication failed") from error
                plain.write(final)
                plain_hash.update(final)
        if plain_hash.hexdigest() != expected_sha256:
            raise ValueError("Decrypted original archive digest mismatch")
    except Exception:
        dst.unlink(missing_ok=True)
        raise
    return {"format": FORMAT, "encryptionVerified": True,
            "plaintextSha256": expected_sha256}


def verify_recovery(source, expected_sha256):
    """Verify an independently supplied recovery root against original ciphertext.

    Processes downloaded AES-GCM bytes in 1-MiB chunks; never creates a
    plaintext copy, logs key material or grants deletion authority. The
    operator must escrow the original root OUTSIDE the Render deployment.
    The root must be explicitly supplied in BOB_ARCHIVE_RECOVERY_ROOT_TOKEN.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.exceptions import InvalidTag
    src = Path(source)
    size = src.stat().st_size
    if not OVERHEAD < size <= MAX_PLAINTEXT_BYTES + OVERHEAD:
        raise ValueError("Encrypted archive outside recovery byte budget")
    if type(expected_sha256) is not str or len(expected_sha256) != 64:
        raise ValueError("Original archive digest unavailable")
    original_hash = hashlib.sha256()
    with open(src, "rb") as ciphertext:
        header = ciphertext.read(len(MAGIC) + NONCE_SIZE)
        if len(header) != len(MAGIC) + NONCE_SIZE or not header.startswith(MAGIC):
            raise ValueError("Unsupported encrypted archive format")
        ciphertext.seek(-TAG_SIZE, os.SEEK_END)
        tag = ciphertext.read(TAG_SIZE)
        ciphertext.seek(len(MAGIC) + NONCE_SIZE)
        decryptor = Cipher(
            algorithms.AES(_key("BOB_ARCHIVE_RECOVERY_ROOT_TOKEN")),
            modes.GCM(header[len(MAGIC):], tag)
        ).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        remaining = size - OVERHEAD
        while remaining:
            block = ciphertext.read(min(CHUNK_SIZE, remaining))
            if not block:
                raise ValueError("Truncated encrypted archive")
            remaining -= len(block)
            original_hash.update(decryptor.update(block))
        try:
            original_hash.update(decryptor.finalize())
        except InvalidTag as error:
            raise ValueError("Recovery archive authentication failed") from error
    if original_hash.hexdigest() != expected_sha256:
        raise ValueError("Recovered archive digest mismatch")
    return {"recoveryKeyVerified": True, "encryptionVersion": FORMAT}
