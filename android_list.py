"""Private, bounded handset list-image handoff; never product/trade approval."""
import base64
import hashlib
import json
import re
import struct
from datetime import datetime
from android_telemetry import token_hash

MAX_BODY=8100000

def validate(value, now):
    if not isinstance(value,dict) or set(value)!={'batchId','sessionId','images'}:
        raise ValueError('Invalid list batch')
    if any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{32}',value[k]) for k in ('batchId','sessionId')):
        raise ValueError('Invalid list identity')
    images=value['images']
    if not isinstance(images,list) or not 1<=len(images)<=4:raise ValueError('One to four images required')
    seen=set();previous=0
    for image in images:
        if not isinstance(image,dict) or set(image)!={'at','png'}:raise ValueError('Invalid image')
        stamp=datetime.fromisoformat(image['at'].replace('Z','+00:00'))
        if stamp.tzinfo is None or not now-86400<=stamp.timestamp()<=now+5 or stamp.timestamp()<previous:raise ValueError('Invalid capture time')
        previous=stamp.timestamp()
        if not isinstance(image['png'],str) or len(image['png'])>2000000:raise ValueError('Image too large')
        raw=base64.b64decode(image['png'],validate=True)
        if len(raw)<33 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError('PNG required')
        w,h=struct.unpack('>II',raw[16:24])
        if not 200<=w<=5000 or not 200<=h<=5000 or w*h>16000000:raise ValueError('Invalid dimensions')
        digest=hashlib.sha256(raw).hexdigest()
        if digest in seen:raise ValueError('Duplicate screenshots')
        seen.add(digest)
    return value

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_android_list_images (
        batch_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL REFERENCES bob_android_diagnostic_devices(token_hash) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL)''')
    conn.execute("ALTER TABLE bob_android_list_images ADD COLUMN IF NOT EXISTS import_receipt JSONB")
    conn.execute("ALTER TABLE bob_android_list_images ADD COLUMN IF NOT EXISTS parsed_items JSONB")
    conn.execute("ALTER TABLE bob_android_list_images ADD COLUMN IF NOT EXISTS processing_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE bob_android_list_images ADD COLUMN IF NOT EXISTS processing_attempts INTEGER NOT NULL DEFAULT 0")

IMPORT_STAGES = frozenset(('fetching','images-ready','reading','stored','synced','fetch-failed','read-failed','store-failed','superseded'))

def receipt(value, now):
    if not isinstance(value,dict) or set(value)!={'batchId','stage','count'}:
        raise ValueError('Invalid import receipt')
    if not isinstance(value['batchId'],str) or not re.fullmatch('[a-f0-9]{32}',value['batchId']):
        raise ValueError('Invalid batch')
    if value['stage'] not in IMPORT_STAGES or type(value['count']) is not int or not 0<=value['count']<=10:
        raise ValueError('Invalid import stage')
    return {**value,'at':datetime.fromtimestamp(now).astimezone().isoformat()}

def status(conn):
    if not conn.execute("SELECT to_regclass('bob_android_list_images')").fetchone()[0]:return []
    rows=conn.execute("""SELECT i.batch_id, i.created_at, jsonb_array_length(i.payload->'images'), i.import_receipt, i.processing_attempts, i.processing_at
        FROM bob_android_list_images i JOIN bob_android_diagnostic_devices d USING(token_hash)
        WHERE NOT d.revoked AND d.expires_at>now() AND i.created_at>now()-interval '24 hours'
        ORDER BY i.created_at DESC LIMIT 5""").fetchall()
    return [{'batchId':r[0],'uploadedAt':r[1].isoformat(),'imageCount':r[2],'import':r[3],'processingAttempts':r[4],'processingAt':r[5].isoformat() if r[5] else None} for r in rows]

def handle(conn,payload,now):
    conn.execute("DELETE FROM bob_android_list_images WHERE created_at<now()-interval '24 hours'")
    if payload['action']=='list-receipt':
        value=receipt(payload.get('value'),now)
        row=conn.execute('''UPDATE bob_android_list_images i SET import_receipt=CASE WHEN i.import_receipt->>'stage' IN ('synced','superseded') THEN i.import_receipt ELSE %s::jsonb END
            FROM bob_android_diagnostic_devices d WHERE i.token_hash=d.token_hash AND i.batch_id=%s
            AND NOT d.revoked AND d.expires_at>now() RETURNING i.batch_id''',
            (json.dumps(value),value['batchId'])).fetchone()
        if not row:raise ValueError('Unknown batch')
        return {'ok':True}
    if payload['action']=='list-get':
        batch=payload.get('batchId')
        if batch=='current':
            row=conn.execute("""SELECT i.payload,i.parsed_items,i.import_receipt FROM bob_android_list_images i
                JOIN bob_android_diagnostic_devices d USING(token_hash)
                WHERE NOT d.revoked AND d.expires_at>now() AND i.import_receipt->>'stage'='synced'
                AND i.parsed_items IS NOT NULL ORDER BY i.created_at DESC LIMIT 1""").fetchone()
        else:
            if not isinstance(batch,str) or not re.fullmatch('[a-f0-9]{32}',batch):raise ValueError('Invalid batch')
            row=conn.execute("""SELECT i.payload,i.parsed_items,i.import_receipt FROM bob_android_list_images i
                JOIN bob_android_diagnostic_devices d USING(token_hash)
                WHERE i.batch_id=%s AND NOT d.revoked AND d.expires_at>now()""",(batch,)).fetchone()
        return {'ok':True,'batch':row[0] if row else None,'items':row[1] if row else None,'import':row[2] if row else None}
    digest=token_hash(payload.get('token'))
    device=conn.execute('SELECT token_hash FROM bob_android_diagnostic_devices WHERE token_hash=%s AND NOT revoked AND expires_at>now() FOR UPDATE',(digest,)).fetchone()
    if not device:raise PermissionError('Device not paired')
    if payload['action']=='list-status':
        batch=payload.get('value',{}).get('batchId')
        if not isinstance(batch,str) or not re.fullmatch('[a-f0-9]{32}',batch):raise ValueError('Invalid batch')
        row=conn.execute('SELECT import_receipt, parsed_items FROM bob_android_list_images WHERE batch_id=%s AND token_hash=%s',(batch,digest)).fetchone()
        details=[]
        if row and row[0] and row[0].get('stage')=='synced':
            saved=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
            products=(saved[0] or {}).get('products',[]) if saved else []
            candidates={x['isin'] for x in (row[1] or []) if not x.get('listRow',{}).get('excluded')}
            details=[p['isin'] for p in products if p.get('isin') in candidates
                     and any(not isinstance(p.get(k),(int,float)) or isinstance(p.get(k),bool) or p[k]<=0 for k in ('price','leverage','ko'))]
        return {'ok':True,'batchId':batch,'import':row[0] if row else None,'detailIsins':details}
    value=validate(payload.get('value'),now)
    row=conn.execute('SELECT state FROM bob_android_remote WHERE token_hash=%s FOR UPDATE',(digest,)).fetchone()
    state=row[0] if row else {}
    if state.get('sessionId')!=value['sessionId'] or not state.get('active') or state.get('expiresAt',0)<=now or now-state.get('seenAt',0)>30:
        raise PermissionError('No active handset session')
    old=conn.execute('SELECT token_hash,payload FROM bob_android_list_images WHERE batch_id=%s',(value['batchId'],)).fetchone()
    if old:
        if old[0]!=digest or old[1]['images']!=value['images']:raise ValueError('Conflicting batch')
    else:
        count=conn.execute("SELECT count(*) FROM bob_android_list_images WHERE token_hash=%s AND created_at>now()-interval '1 hour'",(digest,)).fetchone()[0]
        if count>=12:raise ValueError('Capture rate limit')
        conn.execute('INSERT INTO bob_android_list_images(batch_id,token_hash,payload) VALUES(%s,%s,%s::jsonb)',(value['batchId'],digest,json.dumps(value)))
    return {'ok':True,'batchId':value['batchId']}
