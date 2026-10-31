"""Read-only, fail-closed adapter for future cold decision product arrays.

No archive writer, schema migration, cleanup or startup worker exists here.
Inline historical decisions remain byte-for-byte unchanged. The optional
reference format is reserved for a later, separately tested writer rollout.
"""
import copy
import re

TAG = '_bobColdDecisionProductsV1'
SCOPE = 'decision-products'
_HASH = re.compile(r'[a-f0-9]{64}\Z')


def resolve(conn, decision_id, payload, *, drive=None, verified=None):
    """Resolve an immutable archived product list, or pass inline JSON through.

    The future writer must atomically commit a decision->content-hash ledger,
    content-addressed object location and a pointer in the original row.
    Exact source data is verified from immutable private Drive storage.
    """
    if not isinstance(payload, dict) or TAG not in payload:
        return payload

    import cold_metrics as codec
    try:
        content_hash = payload[TAG]
        if (type(decision_id) is not str or not decision_id or
                type(content_hash) is not str or not _HASH.fullmatch(content_hash) or
                'products' in payload):
            raise ValueError('Malformed cold decision pointer')

        bound = conn.execute(
            'SELECT content_hash FROM bob_cold_decision_product_refs '
            'WHERE decision_id=%s', (decision_id,)).fetchone()
        if not bound or bound[0] != content_hash:
            raise ValueError('Decision identity does not match archived product hash')

        location = conn.execute(
            'SELECT file_id,sha256,row_index FROM bob_cold_decision_product_objects '
            'WHERE content_hash=%s', (content_hash,)).fetchone()
        if (not location or len(location) != 3 or
                type(location[2]) is not int or
                not 0 <= location[2] < codec.MAX_ROWS):
            raise ValueError('Cold decision object location missing')

        if verified is None:
            rows = codec.read_chunk(drive, location[0], location[1], conn=conn)
            row = rows[location[2]]
        else:
            # Only a writer which already downloaded and verified remote chunks
            # may supply this pre-verified in-memory array inside its CAS tx.
            if type(verified) is not dict or content_hash not in verified:
                raise ValueError('Verified original product content missing')
            row = [content_hash, SCOPE, 0, None, {'products':verified[content_hash]}]
        if (not isinstance(row, list) or len(row) != 5 or
                row[:4] != [content_hash, SCOPE, 0, None] or
                type(row[4]) is not dict or set(row[4]) != {'products'} or
                type(row[4]['products']) is not list or
                codec.digest(codec.encoded(row[4]['products'])) != content_hash):
            raise ValueError('Archived decision product identity or checksum differs')
        return {**{key:value for key,value in payload.items() if key != TAG},
                'products':copy.deepcopy(row[4]['products'])}
    except Exception:
        # No silent [] fallback: missing Drive or corrupted evidence means the
        # entire historical result is incomplete, not a valid empty product list.
        raise codec.ColdArchiveUnavailable(
            'Original historical decision products unavailable; report incomplete') from None
