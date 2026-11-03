"""Explicit OFFLINE escrow and archive verification: never upload a secret.

No network connections, production changes, scheduler, automatic cloud storage,
or claim that offline media survives. Use hidden interactive input only.
The original root MUST be stored outside Render, GitHub and Google Drive.
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = "bob-offline-root-escrow-v1"
ARCHIVE_VERSION = "aes-256-gcm-stream-v1"
SCOPE = "reviewed-evidence-tables-not-full-database-backup"
AAD = VERSION.encode()
MAGIC = b"BOBAES01"
DOMAIN = b"bob-drive-evidence-encryption-v1\x00"
MAX_SIZE = 512 * 1024 * 1024


def _kdf(password, salt):
    if type(password) is not str or not 16 <= len(password) <= 2048:
        raise ValueError("Independent long passphrase required")
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15,
                          r=8, p=1, dklen=32, maxmem=128*1024*1024)


def _b64(blob):
    return base64.b64encode(blob).decode("ascii")


def _decode(value, limit):
    if type(value) is not str or len(value) > 12000:
        raise ValueError("Invalid escrow")
    data = base64.b64decode(value, validate=True)
    if len(data) > limit:
        raise ValueError("Escrow field too large")
    return data


def create_escrow(root, password, output):
    """Exclusive 0600 output holds authenticated ciphertext only."""
    if type(root) is not bytes or not 32 <= len(root) <= 4096 or b"\x00" in root:
        raise ValueError("Invalid original archive root")
    salt, nonce = os.urandom(16), os.urandom(12)
    payload = AESGCM(_kdf(password, salt)).encrypt(nonce, root, AAD)
    record = {"version": VERSION, "salt": _b64(salt),
              "nonce": _b64(nonce), "ciphertext": _b64(payload)}
    path = Path(output)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as output_stream:
            json.dump(record, output_stream, sort_keys=True, separators=(",", ":"))
            output_stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"status": "escrow-ciphertext-created",
            "independentOfflineRetentionVerified": False,
            "recoveryVerified": False, "productionDataChanged": False}


def unlock_escrow(path, password):
    source = Path(path)
    if source.stat().st_size > 12000:
        raise ValueError("Escrow file too large")
    record = json.loads(source.read_text(encoding="ascii"))
    if type(record) is not dict or set(record) != {
            "version", "salt", "nonce", "ciphertext"} or record["version"] != VERSION:
        raise ValueError("Unrecognized escrow envelope")
    salt, nonce = _decode(record["salt"], 16), _decode(record["nonce"], 12)
    payload = _decode(record["ciphertext"], 4112)
    if len(salt) != 16 or len(nonce) != 12 or not 48 <= len(payload) <= 4112:
        raise ValueError("Invalid escrow field lengths")
    try:
        root = AESGCM(_kdf(password, salt)).decrypt(nonce, payload, AAD)
    except InvalidTag as error:
        raise ValueError("Wrong passphrase or corrupted escrow") from error
    if not 32 <= len(root) <= 4096 or b"\x00" in root:
        raise ValueError("Invalid recovered root")
    return root


def verified_receipt_digest(path):
    source = Path(path)
    if source.stat().st_size > 32768:
        raise ValueError("Receipt too large")
    data = json.loads(source.read_text(encoding="utf-8"))
    if (type(data) is not dict
            or data.get("version") != "bob-evidence-archive-v3"
            or data.get("scope") != SCOPE
            or data.get("encryptionVerified") is not True
            or data.get("encryptionVersion") != ARCHIVE_VERSION
            or data.get("remoteDownloadVerified") is not True
            or data.get("restoreVerified") is not True
            or data.get("restoreIsolation") != "separate-database-instance"
            or data.get("deletionPermitted") is not False):
        raise ValueError("Archive receipt incomplete or wrong scope")
    digest = data.get("archiveSha256")
    if type(digest) is not str or len(digest) != 64:
        raise ValueError("Missing archive digest")
    try:
        bytes.fromhex(digest)
    except ValueError as error:
        raise ValueError("Malformed archive digest") from error
    return digest.lower()


def verify_archive(encrypted_path, root, expected_digest):
    """Stream-authenticate original encrypted ZIP without writing plaintext."""
    if type(root) is not bytes or not 32 <= len(root) <= 4096:
        raise ValueError("Missing original root")
    if type(expected_digest) is not str or len(expected_digest) != 64:
        raise ValueError("Invalid original digest")
    try:
        bytes.fromhex(expected_digest)
    except ValueError as error:
        raise ValueError("Invalid original digest") from error
    size = Path(encrypted_path).stat().st_size
    header_bytes = len(MAGIC) + 12
    if not header_bytes + 16 < size <= MAX_SIZE + header_bytes + 16:
        raise ValueError("Encrypted file size invalid")
    with open(encrypted_path, "rb") as ciphertext:
        header = ciphertext.read(header_bytes)
        if len(header) != header_bytes or not header.startswith(MAGIC):
            raise ValueError("Wrong archive envelope")
        ciphertext.seek(-16, os.SEEK_END)
        tag = ciphertext.read(16)
        ciphertext.seek(header_bytes)
        key = hashlib.sha256(DOMAIN + root).digest()
        decryptor = Cipher(algorithms.AES(key),
                           modes.GCM(header[len(MAGIC):], tag)).decryptor()
        decryptor.authenticate_additional_data(MAGIC)
        digest = hashlib.sha256()
        remaining = size - header_bytes - 16
        while remaining:
            block = ciphertext.read(min(1024*1024, remaining))
            if not block:
                raise ValueError("Truncated archive")
            remaining -= len(block)
            digest.update(decryptor.update(block))
        try:
            digest.update(decryptor.finalize())
        except InvalidTag as error:
            raise ValueError("Wrong key or corrupted encrypted archive") from error
    if not hmac.compare_digest(digest.hexdigest(), expected_digest.lower()):
        raise ValueError("Original archive digest mismatch")
    return {"encryptedOriginalAuthenticated": True,
            "originalSha256Verified": True,
            "independentPostgresRestorePerformed": False,
            "offlineBackupDurabilityVerified": False,
            "productionDataChanged": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline Bob recovery; no secrets in arguments")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--output", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--escrow", required=True)
    verify.add_argument("--archive", required=True)
    verify.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            root = getpass.getpass("Original root (hidden): ").encode()
            confirmation = getpass.getpass("Repeat original root (hidden): ").encode()
            if not hmac.compare_digest(root, confirmation):
                raise ValueError("Root confirmation mismatch")
            password = getpass.getpass("Separate offline passphrase (hidden): ")
            again = getpass.getpass("Repeat passphrase (hidden): ")
            if not hmac.compare_digest(password.encode("utf-8"), again.encode("utf-8")):
                raise ValueError("Passphrase confirmation mismatch")
            result = create_escrow(root, password, args.output)
        else:
            password = getpass.getpass("Offline escrow passphrase (hidden): ")
            root = unlock_escrow(args.escrow, password)
            digest = verified_receipt_digest(args.receipt)
            result = verify_archive(args.archive, root, digest)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Do not print exception messages or any private paths.
        print(json.dumps({"status": "blocked", "errorType": type(error).__name__,
                          "productionDataChanged": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
