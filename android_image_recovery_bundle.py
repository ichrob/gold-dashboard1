"""Offline, bounded, byte-identical Android screenshot recovery bundle.

TEST PREPARATION ONLY: no runtime hook, HTTP endpoint, scheduler, Drive upload,
or production source mutation. A bundle holds sensitive original PNGs and a
device scope; it must never be logged, emailed or uploaded unencrypted.
An isolated restore schema proves format consistency, NOT an independent
server or remotely verified backup.
"""
import gzip
import hashlib
import io
import json
import re
from datetime import datetime

import android_image_persistent_shadow as shadow
import android_image_reference_codec as codec
import android_list

_FORMAT = 'bob-private-android-image-recovery-v1'
_RAW_LIMIT = 18 * 1024 * 1024
_BLOB_LIMIT = 18 * 1024 * 1024
_RESTORE_SCHEMA = re.compile(r'png_restore_[a-f0-9]{32}\Z')
_CHECKSUM = re.compile(r'[a-f0-9]{64}\Z')
_SCOPE = re.compile(r'[a-f0-9]{64}\Z')
_BATCH = re.compile(r'[a-f0-9]{32}\Z')


def _canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),
                      ensure_ascii=False,allow_nan=False).encode('utf8')


def _validate_payload(obj):
    if type(obj) is not dict or set(obj) != {
            'format','deviceScope','batchId','uploadedAt','original',
            'reference','objects','originalSha256','sourceMetadata'}:
        raise ValueError('Invalid recovery manifest')
    scope,batch_id=obj['deviceScope'],obj['batchId']
    if (type(scope) is not str or not _SCOPE.fullmatch(scope)
            or type(batch_id) is not str or not _BATCH.fullmatch(batch_id)
            or type(obj['originalSha256']) is not str
            or not _CHECKSUM.fullmatch(obj['originalSha256'])
            or obj['format']!=_FORMAT
            or type(obj['original']) is not dict
            or type(obj['reference']) is not dict
            or type(obj['objects']) is not list):
        raise ValueError('Invalid recovery identities')
    try:
        uploaded=datetime.fromisoformat(obj['uploadedAt'])
        if uploaded.tzinfo is None:
            raise ValueError('Original upload has no timezone')
    except (TypeError,ValueError,OverflowError):
        raise ValueError('Invalid original upload clock') from None
    original=obj['original']
    metadata=obj['sourceMetadata']
    if (type(metadata) is not dict or set(metadata) != {
            'importReceipt','parsedItems','processingAt','processingAttempts'}
            or metadata['importReceipt'] is not None
               and type(metadata['importReceipt']) is not dict
            or metadata['parsedItems'] is not None
               and type(metadata['parsedItems']) is not list
            or type(metadata['processingAttempts']) is not int
            or not 0 <= metadata['processingAttempts'] <= 1000):
        raise ValueError('Invalid source row metadata')
    if metadata['processingAt'] is not None:
        try:
            recorded=datetime.fromisoformat(metadata['processingAt'])
            if recorded.tzinfo is None:raise ValueError('Naive processing clock')
        except (TypeError,ValueError,OverflowError):
            raise ValueError('Invalid processing clock') from None
    if original.get('batchId')!=batch_id:
        raise ValueError('Original batch ID mismatch')
    if hashlib.sha256(_canonical(original)).hexdigest()!=obj['originalSha256']:
        raise ValueError('Original manifest checksum differs')
    android_list.validate(original,uploaded.timestamp())
    expected,expected_objects=codec.pack_batch(original,scope)
    if expected != obj['reference']:
        raise ValueError('Stored reference differs from original')
    objects={}
    for item in obj['objects']:
        if type(item) is not dict or set(item)!={'key','encodedPng'}:
            raise ValueError('Invalid recovered object')
        key,encoded=item['key'],item['encodedPng']
        if (type(key) is not str or not _CHECKSUM.fullmatch(key)
                or type(encoded) is not str or key in objects):
            raise ValueError('Invalid or duplicated image key')
        objects[key]=encoded
    if objects!=expected_objects:
        raise ValueError('Recovered image bytes or device scope differ')
    if codec.restore_batch(expected,objects,scope)!=original:
        raise ValueError('Recovered full batch mismatch')
    return uploaded


def pack_recovery_bundle(conn,batch_id,scope):
    """Read exactly one valid source+shadow pair and return sensitive bytes.

    A caller is responsible for encryption, off-host transfer, and a separately
    verified restore. This helper only establishes deterministic bytes and a
    content checksum. It refuses a missing unexpired original/shadow pair.
    """
    shadow._require_ids(batch_id,scope)
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='1000ms'")
        uploaded,original=shadow._original(conn,batch_id,scope)
        restored=shadow._resolve(conn,batch_id,scope,
                                 original=(uploaded,original))
        if restored!=original:
            raise ValueError('Source and reference mismatch')
        meta_row=conn.execute("""SELECT import_receipt,parsed_items,
            processing_at,processing_attempts FROM bob_android_list_images
            WHERE batch_id=%s AND token_hash=%s""",(batch_id,scope)).fetchone()
        if not meta_row or len(meta_row)!=4:
            raise ValueError('Original row metadata not observed')
        receipt,items,processed,attempts=meta_row
        metadata={'importReceipt':receipt,'parsedItems':items,
                  'processingAt':processed.isoformat() if processed else None,
                  'processingAttempts':attempts}
        ptr,objs=codec.pack_batch(original,scope)
        payload={
            'format':_FORMAT,'deviceScope':scope,'batchId':batch_id,
            'uploadedAt':uploaded.isoformat(),
            'original':original,'sourceMetadata':metadata,'reference':ptr,
            'objects':[{'key':key,'encodedPng':value}
                       for key,value in sorted(objs.items())],
            'originalSha256':hashlib.sha256(_canonical(original)).hexdigest(),
        }
        raw=_canonical(payload)
        if len(raw)>_RAW_LIMIT:
            raise ValueError('Recovery bundle raw limit')
        blob=gzip.compress(raw,mtime=0)
        if len(blob)>_BLOB_LIMIT:
            raise ValueError('Recovery bundle compressed limit')
        return blob,hashlib.sha256(blob).hexdigest()


def validate_recovery_bundle(blob,checksum):
    """Bounded decompress; return private manifest only inside trusted tests."""
    if (type(blob) is not bytes or len(blob)==0 or len(blob)>_BLOB_LIMIT
            or type(checksum) is not str or not _CHECKSUM.fullmatch(checksum)
            or hashlib.sha256(blob).hexdigest()!=checksum):
        raise ValueError('Recovery artifact integrity mismatch')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(blob),mode='rb') as stream:
            raw=stream.read(_RAW_LIMIT+1)
        if len(raw)>_RAW_LIMIT:
            raise ValueError('Expanded recovery bundle limit')
        obj=json.loads(raw)
        if _canonical(obj)!=raw:
            raise ValueError('Recovery JSON not canonical')
        _validate_payload(obj)
        return obj
    except Exception:
        # Do not include object/PNG/corrupt archive details in error messages.
        raise ValueError('Recovery artifact invalid') from None


def restore_to_isolated_test_schema(conn,blob,checksum):
    """Transactionally restore only under a fresh png_restore_<uuid> schema.

    No production schema, no network access, no implicit backup approval.
    The caller must pre-create only the test source table; this function adds
    test reference tables and verifies recovered originals before commit.
    """
    manifest=validate_recovery_bundle(blob,checksum)
    row=conn.execute('SELECT current_schema()').fetchone()
    if (not row or type(row[0]) is not str
            or not _RESTORE_SCHEMA.fullmatch(row[0])):
        raise ValueError('Separate test restore schema required')
    from psycopg.types.json import Jsonb
    scope,bid=manifest['deviceScope'],manifest['batchId']
    uploaded=datetime.fromisoformat(manifest['uploadedAt'])
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='1000ms'")
        shadow.init_test_schema(conn)
        metadata=manifest['sourceMetadata']
        processing=(datetime.fromisoformat(metadata['processingAt'])
                    if metadata['processingAt'] else None)
        conn.execute("""INSERT INTO bob_android_list_images
            (batch_id,token_hash,created_at,payload,import_receipt,
             parsed_items,processing_at,processing_attempts)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (bid,scope,uploaded,Jsonb(manifest['original']),
             Jsonb(metadata['importReceipt']) if metadata['importReceipt'] is not None else None,
             Jsonb(metadata['parsedItems']) if metadata['parsedItems'] is not None else None,
             processing,metadata['processingAttempts']))
        for item in manifest['objects']:
            conn.execute("""INSERT INTO bob_android_shadow_objects
                (token_hash,object_key,encoded_png)
                VALUES(%s,%s,%s)""",
                (scope,item['key'],item['encodedPng']))
        conn.execute("""INSERT INTO bob_android_shadow_batch_refs
            (batch_id,token_hash,uploaded_at,pointer_payload,original_sha256)
            VALUES(%s,%s,%s,%s,%s)""",
            (bid,scope,uploaded,Jsonb(manifest['reference']),
             manifest['originalSha256']))
        reconstructed=shadow._resolve(conn,bid,scope,
                                     original=(uploaded,manifest['original']))
        if reconstructed!=manifest['original']:
            raise ValueError('Isolated original restoration differs')
        before=conn.execute("""SELECT payload,import_receipt,parsed_items,
            processing_at,processing_attempts FROM bob_android_list_images
            WHERE batch_id=%s AND token_hash=%s""",(bid,scope)).fetchone()
        if (not before or before[0]!=reconstructed
                or before[1]!=metadata['importReceipt']
                or before[2]!=metadata['parsedItems']
                or before[3]!=processing
                or before[4]!=metadata['processingAttempts']):
            raise ValueError('Isolated original row differs')
    return {'status':'isolated-test-restore-verified',
            'restoredImages':len(manifest['original']['images']),
            'fullBatchRoundTripVerified':True,
            'sourcePreserved':True,
            'independentServerVerified':False,
            'remoteDownloadVerified':False,
            'encryptionVerified':False,
            'deletionAuthorized':False,
            'reclaimableBytes':None,
            'diskBytesFreed':None}
