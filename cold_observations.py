"""Content-addressed private archive for old learning evidence; SQL fields stay hot."""
import copy
import gzip
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import cold_metrics as codec

TAG = '_bobColdObservationV1'
_THREAD = None


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_cold_observation_objects (
        content_hash TEXT PRIMARY KEY, file_id TEXT NOT NULL, sha256 TEXT NOT NULL,
        row_index INTEGER NOT NULL, verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        moved_rows BIGINT NOT NULL DEFAULT 0, original_json_bytes BIGINT NOT NULL DEFAULT 0,
        reference_json_bytes BIGINT NOT NULL DEFAULT 0)''')


def evidence(conn, key, drive=None, verified=None):
    if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key):
        raise codec.ColdArchiveUnavailable('Invalid observation content address')
    if verified is not None and key in verified:
        value = verified[key]
    else:
        location=conn.execute('SELECT file_id,sha256,row_index FROM bob_cold_observation_objects WHERE content_hash=%s',(key,)).fetchone()
        if not location or type(location[2]) is not int or not 0<=location[2]<codec.MAX_ROWS:
            raise codec.ColdArchiveUnavailable('Observation archive index unavailable')
        rows=codec.read_chunk(drive,location[0],location[1],conn=conn)
        try:
            row=rows[location[2]]
            if row[:4]!=[key,'observation-evidence',0,None] or set(row[4])!={'evidence'}:
                raise ValueError('Identity mismatch')
            value=row[4]['evidence']
        except (IndexError,KeyError,ValueError):
            raise codec.ColdArchiveUnavailable('Observation archive identity mismatch') from None
    if codec.digest(codec.encoded(value))!=key:
        raise codec.ColdArchiveUnavailable('Observation content hash mismatch')
    return copy.deepcopy(value)


def resolve(conn, payload, *, drive=None, verified=None):
    if not isinstance(payload,dict) or TAG not in payload:return payload
    if 'evidence' in payload:
        raise codec.ColdArchiveUnavailable('Ambiguous observation evidence')
    return {**{k:v for k,v in payload.items() if k!=TAG},
            'evidence':evidence(conn,payload[TAG],drive,verified)}


def offload_batch(conn,drive,now=None):
    if not conn.autocommit:raise ValueError('Dedicated autocommit connection required')
    now=int(time.time()*1000) if now is None else now
    candidates=conn.execute('''SELECT campaign,slot,payload FROM bob_improvement_observations
        WHERE slot<%s AND payload ? 'evidence' AND NOT(payload ? %s)
        AND pg_column_size(payload)>512 AND octet_length(payload::text)<65536
        ORDER BY slot,campaign LIMIT %s''',(now-86400000,TAG,codec.MAX_ROWS)).fetchall()
    selected=[];unique={};size=100
    for campaign,slot,payload in candidates:
        value=payload['evidence'];key=codec.digest(codec.encoded(value))
        pointer={k:v for k,v in payload.items() if k!='evidence'};pointer[TAG]=key
        if len(codec.encoded(pointer))>=len(codec.encoded(payload)):continue
        if key not in unique:
            row=[key,'observation-evidence',0,None,{'evidence':value}]
            n=len(codec.encoded(row))+1
            if size+n>codec.MAX_RAW:break
            size+=n;unique[key]=row
        selected.append((campaign,slot,payload,key,pointer))
    if not selected:return {'status':'no-eligible-rows','movedRows':0}
    existing=dict((r[0],r[1:]) for r in conn.execute('''SELECT content_hash,file_id,sha256,row_index
        FROM bob_cold_observation_objects WHERE content_hash=ANY(%s::text[])''',(list(unique),)).fetchall())
    verified={key:evidence(conn,key,drive) for key in existing}
    for key,value in verified.items():
        if codec.encoded(value)!=codec.encoded(unique[key][4]['evidence']):
            raise codec.ColdArchiveUnavailable('Observation hash collision')
    new_rows=[row for key,row in unique.items() if key not in existing]
    locations={}
    if new_rows:
        raw=codec.encoded({'format':codec.FORMAT,'rows':new_rows})
        if len(raw)>codec.MAX_RAW:raise ValueError('Archive raw limit')
        blob=gzip.compress(raw,mtime=0);checksum=codec.digest(blob)
        if len(blob)>codec.MAX_FILE:raise ValueError('Archive compressed limit')
        with tempfile.TemporaryDirectory(prefix='bob-observations-') as tmp:
            path=Path(tmp)/('observations-'+checksum+'.gz');path.write_bytes(blob);os.chmod(path,0o600)
            file_id=drive.upload(path,checksum)
        restored=codec.read_chunk(drive,file_id,checksum,cached=False)
        if codec.encoded(restored)!=codec.encoded(new_rows):
            raise codec.ColdArchiveUnavailable('Observation remote download differs')
        for i,row in enumerate(restored):
            verified[row[0]]=row[4]['evidence'];locations[row[0]]=(file_id,checksum,i)
    moved=original=references=0
    with conn.transaction():
        for key,location in locations.items():
            conn.execute('''INSERT INTO bob_cold_observation_objects(content_hash,file_id,sha256,row_index)
                VALUES(%s,%s,%s,%s)''',(key,*location))
        for campaign,slot,payload,key,pointer in selected:
            changed=conn.execute('''UPDATE bob_improvement_observations SET payload=%s::jsonb
                WHERE campaign=%s AND slot=%s AND payload=%s::jsonb RETURNING payload''',
                (codec.encoded(pointer).decode(),campaign,slot,codec.encoded(payload).decode())).fetchone()
            if not changed:continue
            if codec.encoded(resolve(conn,changed[0],verified=verified))!=codec.encoded(payload):
                raise codec.ColdArchiveUnavailable('Observation read-through differs')
            a=len(codec.encoded(payload));b=len(codec.encoded(pointer))
            conn.execute('''UPDATE bob_cold_observation_objects SET moved_rows=moved_rows+1,
                original_json_bytes=original_json_bytes+%s,reference_json_bytes=reference_json_bytes+%s
                WHERE content_hash=%s''',(a,b,key))
            moved+=1;original+=a;references+=b
    return {'status':'verified-offload','movedRows':moved,'newUniqueObjects':len(locations),
            'reusedUniqueObjects':len(existing),'originalJsonBytes':original,'referenceJsonBytes':references,
            'readThroughVerified':True,'diskBytesFreed':None}


def status(conn):
    try:
        with conn.transaction():
            r=conn.execute('''SELECT count(*),coalesce(sum(moved_rows),0),coalesce(sum(original_json_bytes),0),
                coalesce(sum(reference_json_bytes),0),max(verified_at) FROM bob_cold_observation_objects''').fetchone()
        return dict(status='observed',uniqueObjects=int(r[0]),offloadedRows=int(r[1]),originalJsonBytes=int(r[2]),
                    referenceJsonBytes=int(r[3]),lastVerifiedAt=str(r[4]) if r[4] else None,diskBytesFreed=None)
    except Exception:return {'status':'not-observed','diskBytesFreed':None}


def run_once(factory=codec.connect):
    with factory() as conn:
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('bob_cold_observations_v1'))").fetchone()[0]:return {'status':'busy'}
        init(conn);drive=codec.runtime_drive(conn);results=[];deadline=time.monotonic()+120
        for _ in range(32):
            result=offload_batch(conn,drive);results.append(result)
            if not result.get('movedRows') or time.monotonic()>=deadline:break
        return {'status':'checked','batches':results,'pressure':__import__('storage_pressure').observe(conn)}


def start():
    global _THREAD
    if os.environ.get('BOB_COLD_OBSERVATIONS_ENABLED')!='1' or _THREAD is not None:return
    def loop():
        time.sleep(420)
        while True:
            try:
                if __import__('archive_worker').status().get('status')=='running':result={'status':'archive-running'}
                else:
                    result=run_once()
                    if result.get('status')=='checked':
                        result['maintenance']=__import__('storage_maintenance').run_once(reclaim_observation_tail=True)
            except Exception as exc:result={'status':'deferred','errorType':type(exc).__name__}
            print('BOB_COLD_OBSERVATIONS '+json.dumps(result,sort_keys=True),flush=True)
            time.sleep(__import__('storage_pressure').delay(result))
    _THREAD=threading.Thread(target=loop,name='bob-cold-observations',daemon=True);_THREAD.start()
