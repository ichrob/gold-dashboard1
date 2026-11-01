"""Isolated persistent screenshot-reference shadow; NOT connected to production.

This module defines a transactionally verified secondary copy. It is *not*
imported by the Android handlers, scheduled workers, or startup. It never
updates or deletes a source row. Only isolated PG tests invoke its writers.
A production pilot would need a fresh, independently restored backup and
separate explicit approval; staging alone does not free database pages.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

import android_image_reference_codec as codec
import android_list

_SCOPE = re.compile(r'[a-f0-9]{64}\Z')
_BATCH = re.compile(r'[a-f0-9]{32}\Z')
_MAX_BATCH_JSON = 8_100_000


def _require_ids(batch_id, scope):
    if (type(batch_id) is not str or not _BATCH.fullmatch(batch_id)
            or type(scope) is not str or not _SCOPE.fullmatch(scope)):
        raise ValueError('Invalid private batch or device scope')


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),
                      ensure_ascii=False,allow_nan=False).encode('utf8')


def init_test_schema(conn):
    """Explicit schema setup only: never called in normal application paths.

    The source table is intentionally NOT created here. The caller must use
    an isolated DB/schema containing the same source table shape as Bob.
    No DDL runs on import or against a normal production startup.
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_android_shadow_objects (
        token_hash TEXT NOT NULL,
        object_key TEXT NOT NULL,
        encoded_png TEXT NOT NULL,
        stored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(token_hash,object_key)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_android_shadow_batch_refs (
        batch_id TEXT PRIMARY KEY REFERENCES bob_android_list_images(batch_id)
            ON DELETE CASCADE,
        token_hash TEXT NOT NULL,
        uploaded_at TIMESTAMPTZ NOT NULL,
        pointer_payload JSONB NOT NULL,
        original_sha256 TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")


def _original(conn,batch_id,scope,*,lock=False):
    suffix = ' FOR SHARE OF i' if lock else ''
    row = conn.execute("""SELECT i.created_at,i.payload FROM bob_android_list_images i
        WHERE i.batch_id=%s AND i.token_hash=%s
          AND i.created_at>now()-interval '24 hours'
          AND i.created_at<=now()""" + suffix,(batch_id,scope)).fetchone()
    if row is None:
        raise ValueError('Image source missing or expired')
    if (not isinstance(row[0],datetime) or row[0].tzinfo is None
            or type(row[1]) is not dict):
        raise ValueError('Invalid source image record')
    if len(_canonical(row[1])) > _MAX_BATCH_JSON:
        raise ValueError('Oversized original batch')
    return row


def _resolve(conn,batch_id,scope,*,original=None):
    row=conn.execute("""SELECT uploaded_at,pointer_payload,original_sha256
        FROM bob_android_shadow_batch_refs
        WHERE batch_id=%s AND token_hash=%s""",(batch_id,scope)).fetchone()
    if not row or len(row)!=3:
        raise ValueError('Shadow reference missing')
    uploaded,pointers,checksum=row
    if (not isinstance(uploaded,datetime) or uploaded.tzinfo is None
            or type(pointers) is not dict or type(checksum) is not str):
        raise ValueError('Invalid stored shadow reference')
    keys=[image.get(codec._REF) for image in pointers.get('images',[])
          if type(image) is dict]
    if not 1<=len(keys)<=4 or len(keys)!=len(pointers.get('images',[])):
        raise ValueError('Unverifiable shadow references')
    if any(type(key) is not str or not re.fullmatch(r'[a-f0-9]{64}',key)
           for key in keys) or len(set(keys))!=len(keys):
        raise ValueError('Invalid or duplicate image keys')
    objects=dict(conn.execute("""SELECT object_key,encoded_png
        FROM bob_android_shadow_objects
        WHERE token_hash=%s AND object_key=ANY(%s::text[])""",
        (scope,keys)).fetchall())
    restored=codec.restore_batch(pointers,objects,scope)
    if hashlib.sha256(_canonical(restored)).hexdigest()!=checksum:
        raise ValueError('Original batch checksum mismatch')
    if android_list.validate(restored,uploaded.timestamp())!=restored:
        raise ValueError('Restored original invalid')
    if original is not None:
        if original[0]!=uploaded or restored!=original[1]:
            raise ValueError('Source/shadow identity mismatch')
    return restored


def verify_shadow(conn,batch_id,scope):
    """Trusted internal-only read-through; require source to be live too."""
    _require_ids(batch_id,scope)
    with conn.transaction():
        original=_original(conn,batch_id,scope)
        restored=_resolve(conn,batch_id,scope,original=original)
    return restored


def stage_copy_test_only(conn,batch_id,scope):
    """One bounded, atomic SHADOW COPY. Never replace or delete source data.

    It only executes when explicitly called on isolated PostgreSQL tests.
    There is no startup hook, HTTP handler, flag, CLI or automation invoking
    it on production. Copying into a second ledger would INCREASE disk use
    until separately approved migration and measured physical reclamation.
    """
    _require_ids(batch_id,scope)
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout='5s'")
        conn.execute("SET LOCAL lock_timeout='1000ms'")
        original=_original(conn,batch_id,scope,lock=True)
        uploaded,payload=original
        android_list.validate(payload,uploaded.timestamp())
        pointer,objects=codec.pack_batch(payload,scope)
        checksum=hashlib.sha256(_canonical(payload)).hexdigest()

        # A SHA-256 key must always refer to the same ORIGINAL encoded PNG.
        # An existing row never gets overwritten by ON CONFLICT.
        for key,encoded in objects.items():
            conn.execute("""INSERT INTO bob_android_shadow_objects
                (token_hash,object_key,encoded_png) VALUES(%s,%s,%s)
                ON CONFLICT(token_hash,object_key) DO NOTHING""",
                (scope,key,encoded))
            found=conn.execute("""SELECT encoded_png FROM bob_android_shadow_objects
                WHERE token_hash=%s AND object_key=%s""",
                (scope,key)).fetchone()
            if not found or found[0]!=encoded:
                raise ValueError('Stored image object differs')

        conn.execute("""INSERT INTO bob_android_shadow_batch_refs
            (batch_id,token_hash,uploaded_at,pointer_payload,original_sha256)
            VALUES(%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT(batch_id) DO NOTHING""",
            (batch_id,scope,uploaded,_canonical(pointer).decode(),checksum))
        restored=_resolve(conn,batch_id,scope,original=original)
        if restored!=payload:
            raise ValueError('Stored shadow round-trip mismatch')
        # Only aggregates: never return source, scope, content keys or hashes.
        return {'status':'isolated-shadow-copy-verified','readOnly':False,
                'sourceUnchanged':True,'fullBatchRoundTripVerified':True,
                'sampledImages':len(payload['images']),
                'attemptedImageObjects':len(objects),
                'migrationAuthorized':False,'persistentBackupVerified':False,
                'diskBytesFreed':None,'reclaimableBytes':None}
