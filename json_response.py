"""Serialize large responses without retaining full text and byte copies in RAM."""
from contextlib import contextmanager
import json
from tempfile import SpooledTemporaryFile

BUFFER_BYTES = 64 * 1024
SPOOL_BYTES = 256 * 1024


@contextmanager
def encoded_response(payload):
    # Serialize before sending headers so failures cannot produce a partial 200.
    # Small responses stay in memory; larger ones use an automatically removed
    # anonymous temporary file. No response or credential is logged or retained.
    with SpooledTemporaryFile(max_size=SPOOL_BYTES, mode='w+b') as stream:
        pending = []
        size = 0
        for token in json.JSONEncoder(separators=(',', ':')).iterencode(payload):
            # ensure_ascii=True matches the existing wire format exactly.
            for offset in range(0, len(token), BUFFER_BYTES):
                piece = token[offset:offset + BUFFER_BYTES]
                pending.append(piece)
                size += len(piece)
                if size >= BUFFER_BYTES:
                    stream.write(''.join(pending).encode('utf-8'))
                    pending.clear()
                    size = 0
        if pending:
            stream.write(''.join(pending).encode('utf-8'))
        length = stream.tell()
        stream.seek(0)
        yield stream, length
