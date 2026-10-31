"""Verified private storage for old analysis payloads, preserving SQL status fields."""
import copy
import gzip
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
import cold_metrics as codec

TAG = '_bobColdAnalysisV1'
_LOCATION = OrderedDict()
_LOCK = threading.Lock()
_THREAD = None


def projection(payload):
    out = {}
    if 'timeframe' in payload:
        out['timeframe'] = payload['timeframe']
    result = payload.get('result')
    if isinstance(result, dict):
        out['result'] = {key: result[key] for key in ('ready','priceFresh','dataAt') if key in result}
    return out


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_cold_analysis_batches (
        batch_key TEXT PRIMARY KEY, file_id TEXT NOT NULL, sha256 TEXT NOT NULL,
        verified_at TIMESTAMPTZ NOT NULL DEFAULT now(), moved_rows INTEGER NOT NULL,
        original_json_bytes BIGINT NOT NULL, reference_json_bytes BIGINT NOT NULL,
        row_ids TEXT[] NOT NULL)''')


def rows_for(conn, key, drive=None):
    if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{32}',key):
        raise codec.ColdArchiveUnavailable('Invalid analysis batch identity')
    with _LOCK:
        location = _LOCATION.get(key)
    if location is None:
        location = conn.execute('SELECT file_id,sha256 FROM bob_cold_analysis_batches WHERE batch_key=%s',(key,)).fetchone()
        if not location:
            raise codec.ColdArchiveUnavailable('Analysis archive index unavailable')
        with _LOCK:
            _LOCATION[key] = location
            while len(_LOCATION)>64:
                _LOCATION.popitem(last=False)
    return codec.read_chunk(drive, *location, conn=conn)


def resolve(conn, payload, identity, *, drive=None, verified_rows=None):
    if not isinstance(payload,dict) or TAG not in payload:
        return payload
    try:
        ref=payload[TAG]
        if not isinstance(ref,list) or len(ref)!=2 or type(ref[1]) is not int or not 0<=ref[1]<codec.MAX_ROWS:
            raise ValueError('Invalid analysis reference')
        rows=rows_for(conn,ref[0],drive) if verified_rows is None else verified_rows
        row=rows[ref[1]]
        if row[:4]!=list(identity) or row[1]!='analysis':
            raise ValueError('Analysis identity mismatch')
        if codec.encoded({k:v for k,v in payload.items() if k!=TAG}) != codec.encoded(projection(row[4])):
            raise ValueError('Analysis SQL status projection mismatch')
        return copy.deepcopy(row[4])
    except Exception:
        raise codec.ColdArchiveUnavailable('Original analysis unavailable; report is incomplete') from None


def get(conn, row_id, *, drive=None):
    """Exact payload lookup, also after normal diagnostic journal retention."""
    row=conn.execute('SELECT id,stage,observed_at,build,payload FROM bob_diagnostic_history WHERE id=%s',(row_id,)).fetchone()
    if row:
        return resolve(conn,row[4],row[:4],drive=drive)
    location=conn.execute('SELECT batch_key FROM bob_cold_analysis_batches WHERE %s=ANY(row_ids) LIMIT 1',(row_id,)).fetchone()
    if not location:
        return None
    for item in rows_for(conn,location[0],drive):
        if item[0]==row_id and item[1]=='analysis':
            return copy.deepcopy(item[4])
    raise codec.ColdArchiveUnavailable('Archived analysis row unavailable')


def offload_batch(conn, drive):
    if not conn.autocommit:
        raise ValueError('Dedicated autocommit connection required')
    candidates=conn.execute('''SELECT id,stage,observed_at,build,payload FROM bob_diagnostic_history
        WHERE stage='analysis' AND recorded_at<now()-interval '6 hours' AND NOT(payload ? %s)
        AND pg_column_size(payload)>512 AND octet_length(payload::text)<65536
        ORDER BY recorded_at,id LIMIT %s''',(TAG,codec.MAX_ROWS)).fetchall()
    rows=[]; size=len(codec.encoded({'format':codec.FORMAT,'rows':[]}))
    for candidate in candidates:
        row=list(candidate); n=len(codec.encoded(row))+(1 if rows else 0)
        if size+n>codec.MAX_RAW:break
        rows.append(row);size+=n
    if not rows:return {'status':'no-eligible-rows','movedRows':0}
    raw=codec.encoded({'format':codec.FORMAT,'rows':rows})
    with tempfile.TemporaryDirectory(prefix='bob-analysis-cold-') as tmp:
        path=Path(tmp)/('analysis-'+uuid.uuid4().hex+'.gz')
        blob=gzip.compress(raw,mtime=0)
        if len(blob)>codec.MAX_FILE:raise ValueError('Archive size limit')
        path.write_bytes(blob);os.chmod(path,0o600)
        checksum=codec.digest(blob);file_id=drive.upload(path,checksum)
    restored=codec.read_chunk(drive,file_id,checksum,cached=False)
    if codec.encoded(restored)!=codec.encoded(rows):
        raise codec.ColdArchiveUnavailable('Original analysis download differs')
    key=uuid.uuid4().hex; moved=[];original=references=0
    with conn.transaction():
        for index,row in enumerate(rows):
            pointer={TAG:[key,index],**projection(row[4])}
            updated=conn.execute('''UPDATE bob_diagnostic_history SET payload=%s::jsonb
                WHERE id=%s AND stage=%s AND observed_at=%s AND build IS NOT DISTINCT FROM %s
                AND payload=%s::jsonb RETURNING payload''',
                (codec.encoded(pointer).decode(),*row[:4],codec.encoded(row[4]).decode())).fetchone()
            if updated:
                if codec.encoded(resolve(conn,updated[0],row[:4],verified_rows=restored))!=codec.encoded(row[4]):
                    raise codec.ColdArchiveUnavailable('Original analysis read-through differs')
                moved.append(row[0]);original+=len(codec.encoded(row[4]));references+=len(codec.encoded(pointer))
        conn.execute('''INSERT INTO bob_cold_analysis_batches
            (batch_key,file_id,sha256,moved_rows,original_json_bytes,reference_json_bytes,row_ids)
            VALUES(%s,%s,%s,%s,%s,%s,%s)''',(key,file_id,checksum,len(moved),original,references,moved))
    return {'status':'verified-offload','movedRows':len(moved),'originalJsonBytes':original,
            'referenceJsonBytes':references,'readThroughVerified':True,'diskBytesFreed':None}


def status(conn):
    try:
        with conn.transaction():
            r=conn.execute('''SELECT count(*),coalesce(sum(moved_rows),0),coalesce(sum(original_json_bytes),0),
                coalesce(sum(reference_json_bytes),0),max(verified_at) FROM bob_cold_analysis_batches''').fetchone()
        return dict(status='observed',verifiedBatches=int(r[0]),offloadedRows=int(r[1]),
                    originalJsonBytes=int(r[2]),referenceJsonBytes=int(r[3]),lastVerifiedAt=str(r[4]) if r[4] else None,
                    diskBytesFreed=None,sqlStatusFieldsRetained=True)
    except Exception:return {'status':'not-observed','diskBytesFreed':None}


def run_once(factory=codec.connect):
    with factory() as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('bob_cold_analysis_v1'))").fetchone()[0]:
            return {'status':'busy'}
        init(conn);drive=codec.runtime_drive(conn);results=[];deadline=time.monotonic()+120
        for _ in range(64):
            result=offload_batch(conn,drive);results.append(result)
            if not result.get('movedRows') or time.monotonic()>=deadline:break
        return {'status':'checked','batches':results}


def start():
    global _THREAD
    if os.environ.get('BOB_COLD_ANALYSIS_ENABLED')!='1' or _THREAD is not None:return
    def loop():
        time.sleep(300)
        while True:
            try:
                if __import__('archive_worker').status().get('status')=='running':
                    result={'status':'archive-running'}
                else:result=run_once()
            except Exception as exc:result={'status':'deferred','errorType':type(exc).__name__}
            print('BOB_COLD_ANALYSIS '+json.dumps(result,sort_keys=True),flush=True)
            time.sleep(60 if result.get('status')=='archive-running' else 3600)
    _THREAD=threading.Thread(target=loop,name='bob-cold-analysis',daemon=True);_THREAD.start()
