"""Versioned encrypted envelope for bounded cold JSON chunks.

The caller verifies the entire envelope hash before decrypting. Legacy gzip
objects remain readable. New decision chunks must use this encrypted format.
"""
import hashlib
import os
from pathlib import Path

import drive_archive_encryption as sealing

MAGIC = b'BOBCOLD1'
HEADER_BYTES = len(MAGIC) + 64


def seal_chunk(source, destination):
    source, destination = Path(source), Path(destination)
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    sealed = destination.with_suffix('.sealed')
    try:
        sealing.seal(source, sealed, checksum)
        with destination.open('xb') as out:
            os.chmod(destination, 0o600)
            out.write(MAGIC + checksum.encode('ascii'))
            with sealed.open('rb') as stream:
                while block := stream.read(sealing.CHUNK_SIZE):
                    out.write(block)
        return hashlib.sha256(destination.read_bytes()).hexdigest()
    finally:
        sealed.unlink(missing_ok=True)


def open_chunk(path, directory):
    """Return authenticated gzip path; never guess another encryption key."""
    path, directory = Path(path), Path(directory)
    with path.open('rb') as stream:
        header = stream.read(HEADER_BYTES)
        if header[:2] == b'\x1f\x8b':
            return path
        if not header.startswith(MAGIC) or len(header) != HEADER_BYTES:
            raise ValueError('Unsupported cold archive format')
        checksum = header[len(MAGIC):].decode('ascii')
        if len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
            raise ValueError('Invalid cold archive digest')
        sealed, plain = directory/'sealed.aesgcm', directory/'authenticated.gz'
        with sealed.open('xb') as out:
            os.chmod(sealed, 0o600)
            while block := stream.read(sealing.CHUNK_SIZE):
                out.write(block)
    sealing.unseal(sealed, plain, checksum)
    return plain
