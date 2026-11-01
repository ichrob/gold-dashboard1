"""Bounded device-scoped orphan PNG cleanup rehearsal for isolated tests.

NEVER imported by production startup, Android handlers, storage maintenance,
workers or CLI. No production delete, no image retention change, no disk claim.
The only allowed schema is png_gc_<32 lowercase hex> in an isolated test DB.
"""
import re
from datetime import datetime, timezone

import android_image_reference_codec as codec
import android_image_persistent_shadow as shadow

_GC_TEST_SCHEMA = re.compile(r'png_gc_[a-f0-9]{32}\Z')
_MAX_REFERENCES = 16
_MAX_OBJECTS = 64


def prune_orphans_in_test_schema(conn):
    """Safely exercise orphan-object cleanup after synthetic source expiry.

    Source rows are NEVER deleted here. A source expiry must first happen in
    the isolated fixture using existing FK cascade. Only object records
    without any still-stored matching device-scoped reference can be removed.
    """
    try:
        current = conn.execute("SELECT current_schema()").fetchone()
        if (not current or len(current)!=1 or type(current[0]) is not str
                or not _GC_TEST_SCHEMA.fullmatch(current[0])):
            raise ValueError("Isolated image GC schema required")
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='6s'")
            conn.execute("SET LOCAL lock_timeout='500ms'")
            refs = conn.execute("""SELECT r.batch_id,r.token_hash,
                    r.pointer_payload,i.created_at
                FROM bob_android_shadow_batch_refs r
                JOIN bob_android_list_images i ON i.batch_id=r.batch_id
                WHERE r.token_hash=i.token_hash
                LIMIT 17""").fetchall()
            objects = conn.execute("""SELECT token_hash,object_key
                FROM bob_android_shadow_objects LIMIT 65""").fetchall()
            if (type(refs) is not list or type(objects) is not list
                    or len(refs)>_MAX_REFERENCES or len(objects)>_MAX_OBJECTS):
                raise ValueError("Orphan verification exceeds safety budget")
            live = set()
            now = datetime.now(timezone.utc)
            for bid,scope,pointer,uploaded in refs:
                shadow._require_ids(bid,scope)
                if (not isinstance(uploaded,datetime) or uploaded.tzinfo is None
                        or not uploaded <= now
                        or (now-uploaded).total_seconds() >= 86400
                        or type(pointer) is not dict
                        or type(pointer.get('images')) is not list
                        or not 1<=len(pointer['images'])<=4):
                    raise ValueError("Invalid or expired retained reference")
                for img in pointer['images']:
                    if (type(img) is not dict or
                            set(img) not in
                            ({'at',codec._REF},{'at','appText',codec._REF})
                            or type(img[codec._REF]) is not str
                            or not re.fullmatch(r'[a-f0-9]{64}',img[codec._REF])):
                        raise ValueError("Malformed reference blocks cleanup")
                    live.add((scope,img[codec._REF]))
                # Verify every still-referenced PNG before touching even an
                # unrelated orphan. A damaged reference must fail closed.
                shadow._resolve(conn,bid,scope)
            existing = set()
            for entry in objects:
                if (type(entry) not in (tuple,list) or len(entry)!=2
                        or type(entry[0]) is not str or
                        type(entry[1]) is not str):
                    raise ValueError("Invalid private object ledger")
                shadow._require_ids('0'*32,entry[0])
                if not re.fullmatch(r'[a-f0-9]{64}',entry[1]):
                    raise ValueError("Invalid private object key")
                existing.add((entry[0],entry[1]))
            if len(existing)!=len(objects) or not live.issubset(existing):
                raise ValueError("Referenced image object missing")
            orphan = existing - live
            for scope,key in sorted(orphan):
                removed = conn.execute("""DELETE FROM bob_android_shadow_objects
                    WHERE token_hash=%s AND object_key=%s
                    RETURNING object_key""",(scope,key)).fetchone()
                if not removed or removed[0]!=key:
                    raise ValueError("Orphan identity changed")
            # Refuse success unless all live references still reconstruct.
            for bid,scope,_,_ in refs:
                shadow._resolve(conn,bid,scope)
        return {
            'status':'isolated-orphan-gc-verified',
            'removedOrphanObjects':len(orphan),
            'retainedReferencedObjects':len(live),
            'sourceRowsDeleted':False,
            'crossDeviceReferenceReused':False,
            'productionGarbageCollectorEnabled':False,
            'deletionAuthorized':False,
            'migrationAuthorized':False,
            'diskBytesFreed':None,
        }
    except Exception:
        raise ValueError("Isolated image GC rehearsal invalid") from None
