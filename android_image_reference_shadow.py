"""Bounded read-only rehearsal of device-scoped screenshot references.

A safe next step, NOT the database writer. Originals, SQL rows and temporary
24-hour screenshot availability are unchanged. Only aggregated byte counts
leave this module, never screenshots, hashes or device/batch identities.
"""
import json
from datetime import datetime
import threading
import time

import android_image_reference_codec as codec
import android_list

_MAX_BATCHES = 8
_MAX_IMAGES = 32
_MAX_ENCODED = 12_000_000
_MAX_ROW_JSON = 14_000_000
_CACHE_SECONDS = 900
_lock = threading.Lock()
_cache = None
_cache_at = 0

_SAMPLE = """SELECT token_hash,created_at,payload
FROM bob_android_list_images
WHERE created_at >= now()-interval '24 hours'
ORDER BY created_at DESC,batch_id DESC LIMIT 8"""

_PROBE = """WITH newest AS MATERIALIZED (
    SELECT payload FROM bob_android_list_images
    WHERE created_at >= now()-interval '24 hours'
    ORDER BY created_at DESC,batch_id DESC LIMIT 8)
SELECT count(*)::bigint,coalesce(sum(octet_length(payload::text)),0)::bigint
FROM newest"""

_SQL = """WITH newest AS MATERIALIZED (
    SELECT token_hash,created_at,payload FROM bob_android_list_images
    WHERE created_at >= now()-interval '24 hours'
    ORDER BY created_at DESC,batch_id DESC LIMIT 8)
SELECT token_hash,created_at,payload FROM newest
WHERE (SELECT coalesce(sum(octet_length(payload::text)),0)
       FROM newest) <= 14000000"""


def _encoded_size(obj):
    # Deterministic short JSON representation for comparative **logical**
    # sizes only. PostgreSQL JSONB/TOAST on disk is unrelated to this size.
    return len(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False).encode('utf8'))


def _simulate(rows, now):
    """Fail closed if real originals cannot round-trip exactly in memory."""
    if type(rows) is not list or len(rows) > _MAX_BATCHES:
        return {'status': 'not-observed', 'readOnly': True,
                'diskBytesFreed':None,'reclaimableBytes':None}
    if not rows:
        return {'status': 'empty','readOnly':True,
                'sampledBatches':0,'sampledImages':0,
                'diskBytesFreed':None,'reclaimableBytes':None}

    original_chars = unique_chars = 0
    before_json = after_json = 0
    object_store = {}
    sources = []
    images = 0
    repeated = 0
    device_scopes = set()
    try:
        for row in rows:
            if type(row) not in (list,tuple) or len(row)!=3:
                raise ValueError('Invalid image row')
            scope, uploaded_at, original = row
            if (type(uploaded_at) is not datetime
                    or uploaded_at.tzinfo is None
                    or not -2 <= now-uploaded_at.timestamp() <= 86400):
                raise ValueError('Unverifiable original upload clock')
            if (type(scope) is not str or type(original) is not dict
                    or type(original.get('images')) is not list):
                raise ValueError('Invalid sample shape')
            device_scopes.add(scope)
            count=len(original['images'])
            if not 1 <= count <= 4 or images+count > _MAX_IMAGES:
                raise ValueError('Sample image cap')
            encoded=[i.get('png') for i in original['images']]
            if any(type(e) is not str or not 1 <= len(e) <= 2_000_000
                   for e in encoded):
                raise ValueError('Invalid image encoding')
            original_chars += sum(len(e) for e in encoded)
            if original_chars > _MAX_ENCODED:
                return {'status':'sample-too-large','readOnly':True,
                        'diskBytesFreed':None,'reclaimableBytes':None}

            # Validate original batch admission rules, including original
            # timestamps. This does not redate or refresh source quotes.
            android_list.validate(original, uploaded_at.timestamp())
            pointer, objects = codec.pack_batch(original,scope)
            before_json += _encoded_size(original)
            after_json += _encoded_size(pointer)
            for key,encoded in objects.items():
                # Byte-addressed keys may map to different base64 textual
                # representations: unless the ORIGINAL encoded string is
                # also identical, don't silently rewrite a historic batch.
                if key in object_store:
                    if object_store[key] != encoded:
                        return {'status':'encoding-conflict','readOnly':True,
                                'diskBytesFreed':None,'reclaimableBytes':None}
                    repeated += 1
                else:
                    object_store[key]=encoded
                    unique_chars += len(encoded)
            images += count
            sources.append((pointer, original, scope, uploaded_at))

        for pointer, original, scope, uploaded_at in sources:
            restored=codec.restore_batch(pointer,object_store,scope)
            if restored != original:
                raise ValueError('Exact image reconstruction mismatch')
            # Round-trip through the existing active importer validator.
            if android_list.validate(restored,uploaded_at.timestamp()) != original:
                raise ValueError('Original import validation mismatch')
        # Store each identical device-scoped image once, but this model does
        # NOT include database row, table, index, WAL or migration costs.
        after_json += _encoded_size(object_store)
        if after_json > 32_000_000:
            raise ValueError('Bounded shadow budget exceeded')
        return {'status':'verified-in-memory','readOnly':True,
                'sampledBatches':len(rows),'sampledImages':images,
                'deviceScopeCount':len(device_scopes),
                'uniqueScopedImageObjects':len(object_store),
                'repeatedImageReferences':repeated,
                'originalEncodedCharacters':original_chars,
                'uniqueObjectEncodedCharacters':unique_chars,
                'serializedJsonBytesBefore':before_json,
                'serializedJsonBytesAfter':after_json,
                'serializedJsonDifferenceBytes':before_json-after_json,
                'fullBatchRoundTripVerified':True,
                'persistentBackupVerified':False,
                'migrationAuthorized':False,
                'diskBytesFreed':None,'reclaimableBytes':None,
                'scope':'in-process-sample-only-no-persistent-objects',
                'note':'Exact original batch read-through verified in memory only. '
                       'Logical JSON bytes, not physical PostgreSQL/Render savings. '
                       'Full durable backup, device access, atomic migration, '
                       'rollback, expiration and all production readers '
                       'must pass independent gates before any live writes.'}
    except Exception:
        # No raw values, exception messages, scope IDs or hashes are logged.
        return {'status':'not-observed','readOnly':True,
                'diskBytesFreed':None,'reclaimableBytes':None}


def report(conn,now=None):
    """One read-only 8-batch scan, TTL cache, fail-closed and no side effects."""
    global _cache, _cache_at
    at=time.time() if now is None else now
    if _cache is not None and 0 <= at-_cache_at < _CACHE_SECONDS:
        return dict(_cache)
    if not _lock.acquire(blocking=False):
        return {'status':'busy','readOnly':True,
                'diskBytesFreed':None,'reclaimableBytes':None}
    try:
        if _cache is not None and 0 <= at-_cache_at < _CACHE_SECONDS:
            return dict(_cache)
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='2500ms'")
                conn.execute("SET LOCAL lock_timeout='500ms'")
                probe=conn.execute(_PROBE).fetchone()
                if (type(probe) not in (tuple,list) or len(probe)!=2
                        or any(type(v) is not int or v < 0 for v in probe)
                        or probe[0] > _MAX_BATCHES):
                    result={'status':'not-observed','readOnly':True,
                            'diskBytesFreed':None,'reclaimableBytes':None}
                elif probe[1] > _MAX_ROW_JSON:
                    result={'status':'sample-too-large','readOnly':True,
                            'diskBytesFreed':None,'reclaimableBytes':None}
                else:
                    rows=conn.execute(_SQL).fetchall()
                    if len(rows)!=probe[0]:
                        result={'status':'cohort-changed','readOnly':True,
                                'diskBytesFreed':None,'reclaimableBytes':None}
                    else:
                        result=_simulate(rows,at)
        except Exception:
            result={'status':'not-observed','readOnly':True,
                    'diskBytesFreed':None,'reclaimableBytes':None}
        _cache=dict(result)
        _cache_at=at
        return result
    finally:
        _lock.release()
