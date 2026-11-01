"""Backward-compatible, device-authenticated PNG reference reader.

Production image writes stay in the original JSONB format. This helper
transparently returns original raw uploads and can *only* restore future
pointer-shaped uploads backed by a verified, device-scoped PostgreSQL shadow.
A missing/corrupt/cross-device pointer always fails closed. No migration,
garbage collection, new route, privilege, or background task.
"""
import hashlib
import re
from datetime import datetime

import android_image_reference_codec as codec
import android_image_persistent_shadow as shadow

_BATCH = re.compile(r'[a-f0-9]{32}\Z')
_REF = codec._REF


def is_reference(payload):
    """Detect any reference (including a forbidden mixed raw/ref batch)."""
    return (type(payload) is dict and type(payload.get('images')) is list
            and any(type(image) is dict and _REF in image
                    for image in payload['images']))


def materialize(conn, batch_id, payload):
    """Return the exact original batch; never return partial/freshened data.

    For legacy uploads: zero extra SQL or data transformations.
    For references: recheck both source row and active paired device, the
    matching shadow record, each device-scoped PNG key, original SHA-256,
    source upload timestamp, and the legacy batch validator.
    """
    if not is_reference(payload):
        return payload
    if (type(batch_id) is not str or not _BATCH.fullmatch(batch_id)
            or type(payload) is not dict or type(payload.get('images')) is not list
            or not 1 <= len(payload['images']) <= 4
            or payload.get('batchId') != batch_id):
        raise ValueError('Invalid private image reference')
    if any(type(img) is not dict or
           set(img) not in ({'at',_REF},{'at','appText',_REF})
           for img in payload['images']):
        raise ValueError('Ambiguous private image reference')
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='3s'")
            conn.execute("SET LOCAL lock_timeout='500ms'")
            source=conn.execute("""SELECT i.token_hash,i.created_at,i.payload
                FROM bob_android_list_images i
                JOIN bob_android_diagnostic_devices d USING(token_hash)
                WHERE i.batch_id=%s AND NOT d.revoked AND d.expires_at>now()
                  AND i.created_at>now()-interval '24 hours'
                  AND i.created_at<=now()
                FOR SHARE OF i""",(batch_id,)).fetchone()
            if (source is None or len(source)!=3
                    or type(source[0]) is not str
                    or not isinstance(source[1],datetime)
                    or source[1].tzinfo is None or type(source[2]) is not dict
                    or source[2]!=payload):
                raise ValueError('Source reference missing or changed')
            scope,at,_=source
            shadow._require_ids(batch_id,scope)
            ref=conn.execute("""SELECT uploaded_at,pointer_payload
                FROM bob_android_shadow_batch_refs
                WHERE batch_id=%s AND token_hash=%s""",
                (batch_id,scope)).fetchone()
            if (not ref or len(ref)!=2 or ref[0]!=at or ref[1]!=payload):
                raise ValueError('Source and reference ledger differ')
            # The existing isolated PG reference library verifies all 1-4
            # scoped objects, the original full-batch SHA-256, and the
            # original upload-clock validation before yielding one batch.
            original=shadow._resolve(conn,batch_id,scope)
            if original.get('batchId')!=batch_id:
                raise ValueError('Reconstructed batch identity differs')
            return original
    except Exception:
        # Never send SQL/PNG/device/account details into responses or logs.
        raise ValueError('Private image reference unavailable') from None
