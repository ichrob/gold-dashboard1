"""Opt-in, verified and bounded writer for immutable decision product arrays.

No scheduler or startup registration. Defaults to OFF. Exact original JSON stays
inline unless a separate future operator explicitly approves verified archival.
Readers must be deployed on BOTH services before enabling this writer.
"""
import gzip
import os
from pathlib import Path
import tempfile
import time
from datetime import datetime, timezone

import cold_metrics as codec
import cold_decision_products as reader

MIN_AGE_SECONDS = 14 * 86400
PAGE_ROWS = 20
MIN_PRODUCT_JSON_BYTES = 256
LOCK = 'bob_cold_decision_products_v1'


def init(conn):
    """Explicit, non-startup setup. Never delete referenced source records."""
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_cold_decision_product_objects (
        content_hash TEXT PRIMARY KEY, file_id TEXT NOT NULL, sha256 TEXT NOT NULL,
        row_index INTEGER NOT NULL CHECK(row_index>=0 AND row_index<500),
        verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        moved_rows BIGINT NOT NULL DEFAULT 0,
        original_json_bytes BIGINT NOT NULL DEFAULT 0,
        reference_json_bytes BIGINT NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_cold_decision_product_refs (
        decision_id TEXT PRIMARY KEY REFERENCES bob_decision_audit(id) ON DELETE RESTRICT,
        content_hash TEXT NOT NULL REFERENCES bob_cold_decision_product_objects(content_hash),
        verified_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_cold_decision_product_scan (
        id INTEGER PRIMARY KEY CHECK (id=1),
        recorded_at TIMESTAMPTZ NOT NULL, decision_id TEXT NOT NULL)""")


def _approved(approval, now_seconds):
    """A specific, fresh, independently verified backup is required.

    No password, connection URI or arbitrary untrusted data is accepted here.
    Approval is supplied only to a manual caller; it is not persisted or loaded
    from a public route, so a config flag alone cannot start archival.
    """
    return (type(approval) is dict and
            approval.get('restoreVerified') is True and
            approval.get('remoteDownloadVerified') is True and
            type(approval.get('observedAt')) in (int,float) and
            0 <= now_seconds-approval['observedAt'] <= 900)


def _proof_state(proof, seconds, max_age_seconds=6*3600):
    """Only a persisted restore/download receipt, never caller-provided claims."""
    # Never let an incomplete rolling-deploy attempt erase the older, genuine
    # verified receipt. The timestamp window still applies, so stale backups
    # cannot grant write permission.
    receipt = ((proof or {}).get('latestVerifiedAttempt') or
               (proof or {}).get('latestPersistedAttempt') or {})
    if (receipt.get('status') != 'verified' or
            receipt.get('restoreVerified') is not True or
            receipt.get('remoteDownloadVerified') is not True or
            receipt.get('evidenceDeleted') is True):
        return 'no-verified-restore'
    try:
        updated = datetime.fromisoformat(str(receipt['updatedAt']).replace('Z', '+00:00'))
        if updated.tzinfo is None:
            return 'timestamp-unavailable'
        age = seconds - updated.timestamp()
    except (ValueError, TypeError, KeyError, OverflowError):
        return 'timestamp-unavailable'
    return 'verified-fresh' if 0 <= age <= max_age_seconds else 'verified-but-stale'


def preview(conn, *, now=None, archive_proof=None):
    """Bounded, nonmutating rehearsal on live old decisions; no Drive traffic.

    This is **not** authorization to call run_once. It does not create ledgers,
    inspect archives, derive missing prices, or compute physical disk savings.
    A distinct true backup proof is required for a subsequent manual run.
    """
    seconds=time.time() if now is None else now
    proof_state=_proof_state(archive_proof,seconds)
    try:
        cutoff=datetime.fromtimestamp(seconds-MIN_AGE_SECONDS,timezone.utc)
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='2s'")
            rows=conn.execute("""WITH page AS MATERIALIZED (
                SELECT recorded_at,id FROM bob_decision_audit
                WHERE recorded_at<%s ORDER BY recorded_at,id LIMIT %s)
                SELECT a.payload FROM page p
                JOIN bob_decision_audit a ON a.id=p.id
                ORDER BY p.recorded_at,p.id""",(cutoff,PAGE_ROWS)).fetchall()
        selected=0;original=0;references=0;arrays=set();max_array=0
        for (payload,) in rows:
            if type(payload) is not dict or reader.TAG in payload:
                continue
            products=payload.get('products')
            if type(products) is not list or not products:
                continue
            array=codec.encoded(products)
            key=codec.digest(array)
            pointer=_pointer(payload,key)
            current=codec.encoded(payload)
            compact=codec.encoded(pointer)
            if len(array)<MIN_PRODUCT_JSON_BYTES or len(compact)>=len(current):
                continue
            selected+=1
            original+=len(current)
            references+=len(compact)
            max_array=max(max_array,len(array))
            arrays.add(key)
        return dict(
            status='sampled',readOnly=True,sourceChanges=0,uploadedFiles=0,
            method='oldest-index-page-max-20-older-than-14d',
            scannedRows=len(rows),eligibleRows=selected,
            distinctProductArrays=len(arrays),
            sharedArrayRows=max(0,selected-len(arrays)),
            originalJsonBytes=original,referenceJsonBytes=references,
            sampleJsonByteDifference=max(0,original-references),
            largestProductArrayJsonBytes=max_array,
            backupProofState=proof_state,
            writerConfigurationEnabled=(os.environ.get('BOB_COLD_DECISION_PRODUCTS_ENABLED')=='1'),
            manualRunAuthorized=False,
            diskBytesFreed=None,
            note='Only logical sizes on up to twenty oldest rows. No new SQL '
                 'table, Google Drive access, updates, or physical space claim. '
                 'A fresh verified restore and distinct manual authorization '
                 'are required before any productive offload.'
        )
    except Exception:
        return dict(status='not-observed',readOnly=True,sourceChanges=0,
                    uploadedFiles=0,backupProofState=proof_state,
                    manualRunAuthorized=False,diskBytesFreed=None)


def _page(conn, cutoff):
    cursor = conn.execute("""SELECT recorded_at,decision_id
        FROM bob_cold_decision_product_scan WHERE id=1""").fetchone()
    if cursor is None:
        lower = datetime(1,1,1,tzinfo=timezone.utc), ''
    else:
        lower = cursor
    # Use indexed recorded_at/id before touching JSONB/TOAST data.
    return conn.execute("""WITH page AS MATERIALIZED (
            SELECT recorded_at,id FROM bob_decision_audit
            WHERE recorded_at<%s AND (recorded_at,id)>(%s,%s)
            ORDER BY recorded_at,id LIMIT %s)
        SELECT p.recorded_at,p.id,a.payload FROM page p
        JOIN bob_decision_audit a ON a.id=p.id
        ORDER BY p.recorded_at,p.id""",
        (cutoff,lower[0],lower[1],PAGE_ROWS)).fetchall()


def _pointer(payload,key):
    return {**{k:v for k,v in payload.items() if k!='products'},
            reader.TAG:key}


def _validate_row(key,arr,row):
    if (type(row) is not list or len(row)!=5 or
            row[:4]!=[key,reader.SCOPE,0,None] or
            type(row[4]) is not dict or set(row[4])!={'products'} or
            type(row[4]['products']) is not list or
            codec.encoded(row[4]['products'])!=codec.encoded(arr) or
            codec.digest(codec.encoded(row[4]['products']))!=key):
        raise codec.ColdArchiveUnavailable('Verified decision original differs')


def offload_batch(conn,drive,*,approval=None,now=None):
    """Upload and verify outside SQL tx, then pointer/reference CAS in one tx."""
    seconds=time.time() if now is None else now
    if os.environ.get('BOB_COLD_DECISION_PRODUCTS_ENABLED')!='1' or not _approved(approval,seconds):
        return {'status':'disabled','movedRows':0}
    if not conn.autocommit:
        raise ValueError('Dedicated autocommit connection required')
    cutoff=datetime.fromtimestamp(seconds-MIN_AGE_SECONDS,timezone.utc)
    candidates=_page(conn,cutoff)
    if not candidates:
        with conn.transaction():
            conn.execute('DELETE FROM bob_cold_decision_product_scan WHERE id=1')
        return {'status':'sweep-completed','movedRows':0,'scannedRows':0}
    pending=[]; unique={}; bytes_used=len(codec.encoded({'format':codec.FORMAT,'rows':[]}))
    last=None
    for at,decision_id,payload in candidates:
        arr=payload.get('products') if type(payload) is dict else None
        if type(arr) is list and arr and reader.TAG not in payload:
            key=codec.digest(codec.encoded(arr))
            new_pointer=_pointer(payload,key)
            if (len(codec.encoded(arr)) >= MIN_PRODUCT_JSON_BYTES and
                    len(codec.encoded(new_pointer)) < len(codec.encoded(payload))):
                if key not in unique:
                    row=[key,reader.SCOPE,0,None,{'products':arr}]
                    increment=len(codec.encoded(row))+1
                    if bytes_used+increment>codec.MAX_RAW or len(unique)>=codec.MAX_ROWS:
                        break
                    bytes_used+=increment
                    unique[key]=row
                pending.append((at,decision_id,payload,key,new_pointer))
        last=(at,decision_id)
    if last is None:
        raise codec.ColdArchiveUnavailable('Unbounded decision product row')
    def advance():
        conn.execute("""INSERT INTO bob_cold_decision_product_scan
            (id,recorded_at,decision_id) VALUES(1,%s,%s)
            ON CONFLICT(id) DO UPDATE SET
            recorded_at=EXCLUDED.recorded_at,decision_id=EXCLUDED.decision_id""",last)
    if not pending:
        with conn.transaction():
            advance()
        return {'status':'page-scanned','movedRows':0,'scannedRows':len(candidates)}

    existing=dict((row[0],row[1:]) for row in conn.execute("""SELECT content_hash,
        file_id,sha256,row_index FROM bob_cold_decision_product_objects
        WHERE content_hash=ANY(%s::text[])""",(list(unique),)).fetchall())
    verified={}; locations={}
    for key,loc in existing.items():
        rows=codec.read_chunk(drive,loc[0],loc[1],cached=False,conn=conn)
        if type(loc[2]) is not int or not 0<=loc[2]<len(rows):
            raise codec.ColdArchiveUnavailable('Original product archive location invalid')
        _validate_row(key,unique[key][4]['products'],rows[loc[2]])
        verified[key]=rows[loc[2]][4]['products']
        locations[key]=tuple(loc)

    new=[row for key,row in unique.items() if key not in existing]
    if new:
        raw=codec.encoded({'format':codec.FORMAT,'rows':new})
        if len(raw)>codec.MAX_RAW:raise codec.ColdArchiveUnavailable('Decision archive raw size exceeded')
        blob=gzip.compress(raw,mtime=0)
        if len(blob)>codec.MAX_FILE:raise codec.ColdArchiveUnavailable('Decision archive file too large')
        checksum=codec.digest(blob)
        with tempfile.TemporaryDirectory(prefix='bob-cold-decision-') as tmp:
            path=Path(tmp)/('decision-products-'+checksum+'.gz')
            path.write_bytes(blob)
            os.chmod(path,0o600)
            file_id=drive.upload(path,checksum)
        restored=codec.read_chunk(drive,file_id,checksum,cached=False,conn=conn)
        if codec.encoded(restored)!=codec.encoded(new):
            raise codec.ColdArchiveUnavailable('Remote decision product originals differ')
        for idx,row in enumerate(restored):
            key=row[0]
            _validate_row(key,unique[key][4]['products'],row)
            verified[key]=row[4]['products']
            locations[key]=(file_id,checksum,idx)
    moved=original_bytes=ref_bytes=0
    with conn.transaction():
        for key,location in locations.items():
            if key not in existing:
                inserted=conn.execute("""INSERT INTO bob_cold_decision_product_objects
                    (content_hash,file_id,sha256,row_index) VALUES(%s,%s,%s,%s)
                    ON CONFLICT(content_hash) DO NOTHING RETURNING content_hash""",
                    (key,*location)).fetchone()
                if not inserted:
                    raise codec.ColdArchiveUnavailable('Concurrent decision object claim')
        for at,decision_id,old,key,pointer in pending:
            changed=conn.execute("""UPDATE bob_decision_audit SET payload=%s::jsonb
                WHERE id=%s AND recorded_at=%s AND recorded_at<%s
                AND payload=%s::jsonb RETURNING payload""",
                (codec.encoded(pointer).decode(),decision_id,at,cutoff,
                 codec.encoded(old).decode())).fetchone()
            if not changed:
                continue
            inserted=conn.execute("""INSERT INTO bob_cold_decision_product_refs
                (decision_id,content_hash) VALUES(%s,%s)
                ON CONFLICT(decision_id) DO NOTHING RETURNING decision_id""",
                (decision_id,key)).fetchone()
            if not inserted:
                raise codec.ColdArchiveUnavailable('Concurrent decision reference claim')
            resolved=reader.resolve(conn,decision_id,changed[0],verified=verified)
            if codec.encoded(resolved)!=codec.encoded(old):
                raise codec.ColdArchiveUnavailable('Decision product read-through comparison failed')
            a=len(codec.encoded(old));b=len(codec.encoded(pointer))
            conn.execute("""UPDATE bob_cold_decision_product_objects SET
                moved_rows=moved_rows+1,
                original_json_bytes=original_json_bytes+%s,
                reference_json_bytes=reference_json_bytes+%s
                WHERE content_hash=%s""",(a,b,key))
            moved+=1;original_bytes+=a;ref_bytes+=b
        advance()
    return {'status':'verified-offload','movedRows':moved,
            'newUniqueObjects':len(new),'reusedUniqueObjects':len(existing),
            'scannedRows':len(candidates),'originalJsonBytes':original_bytes,
            'referenceJsonBytes':ref_bytes,'readThroughVerified':True,
            'diskBytesFreed':None}


def run_once(*,factory=codec.connect,approval=None,now=None):
    """Manual-only invocation. No startup hook, polling or default writer."""
    seconds=time.time() if now is None else now
    if os.environ.get('BOB_COLD_DECISION_PRODUCTS_ENABLED')!='1' or not _approved(approval,seconds):
        return {'status':'disabled','movedRows':0}
    with factory() as conn:
        # Never trust a caller's assertion alone: independently read the
        # persisted, remote-restored backup receipt before creating any table.
        from storage_budget import archive_status
        with conn.transaction():
            proof = archive_status(conn)
        if _proof_state(proof, seconds) != 'verified-fresh':
            return {'status':'backup-proof-not-fresh','movedRows':0}
        volume = __import__('render_disk_metrics').report()
        observed = volume.get('observedAt')
        if (volume.get('status') != 'observed' or
                volume.get('resource') != 'dpg-datjno1srm7s738vv500-a' or
                volume.get('unit') != 'bytes' or
                type(observed) not in (int,float) or
                not 0 <= seconds-observed <= 300 or
                type(volume.get('diskUsage')) is not int or
                volume['diskUsage'] > 750_000_000):
            return {'status':'fresh-volume-proof-unavailable','movedRows':0}
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))",(LOCK,)).fetchone()[0]:
            return {'status':'busy','movedRows':0}
        init(conn)
        return offload_batch(conn,codec.runtime_drive(conn),approval=approval,now=seconds)


def status(conn):
    """No table creation: optional ledger is unobserved until explicitly setup."""
    try:
        with conn.transaction():
            row=conn.execute("""SELECT count(*),coalesce(sum(moved_rows),0),
                coalesce(sum(original_json_bytes),0),
                coalesce(sum(reference_json_bytes),0)
                FROM bob_cold_decision_product_objects""").fetchone()
        return {'status':'observed','uniqueObjects':int(row[0]),
                'offloadedRows':int(row[1]),
                'originalJsonBytes':int(row[2]),
                'referenceJsonBytes':int(row[3]),
                'diskBytesFreed':None}
    except Exception:
        return {'status':'not-observed','diskBytesFreed':None}
