"""Private, bounded handset list-image handoff; never product/trade approval."""
import base64
import hashlib
import json
import re
import struct
import math
from datetime import datetime
from android_telemetry import token_hash

MAX_BODY=8100000

# Product-screen reading is only supplementary. A complete, non-expired source
# snapshot is NEVER re-read just because its ISIN appeared in a new list.
DETAIL_FIELDS = ('Geld', 'Brief', 'Anzeigezeit', 'Hebel', 'KO-Schwelle',
                 'Basispreis', 'Bv', 'Währung')

def detail_plan(items, products, now):
    """Request only still-missing/expired fields, preserving exact list order.

    This is a read-only *research* plan, never a trading approval. Original
    source clocks are required; an upload timestamp is not a quote time.
    """
    from product_quotes import valid_isin
    by_id = {p.get('isin'): p for p in products if isinstance(p, dict)}
    result, seen = [], set()

    def positive(v):
        return type(v) in (int, float) and math.isfinite(v) and v > 0

    def recent(raw):
        if not isinstance(raw, str):
            return False
        try:
            at = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            return at.tzinfo is not None and 0 <= now - at.timestamp() <= 14 * 3600
        except (ValueError, OverflowError):
            return False

    for item in items:
        if not isinstance(item, dict):
            continue
        isin = item.get('isin')
        if (not isinstance(isin, str) or not valid_isin(isin) or isin in seen or
                (isinstance(item.get('listRow'), dict) and item['listRow'].get('excluded'))):
            continue
        seen.add(isin)
        p = by_id.get(isin, {})
        # Missing input values are independent; don't re-read a proven KO or
        # ratio just because the current bid/ask pair has expired.
        missing = [label for key, label in
                   (('leverage','Hebel'), ('ko','KO-Schwelle'),
                    ('basisPrice','Basispreis'), ('ratio','Bv'))
                   if not positive(p.get(key))]
        if p.get('currency') not in ('EUR', 'CHF'):
            missing.append('Währung')
        q = p.get('quote') if isinstance(p.get('quote'), dict) else {}
        bid, ask = positive(q.get('bid')), positive(q.get('ask'))
        if not bid:
            missing.append('Geld')
        if not ask:
            missing.append('Brief')
        if bid and ask and q['bid'] > q['ask']:
            # Both sides need a new ORIGINAL pair; no arithmetic repair.
            missing.extend(('Geld', 'Brief'))
        # Quoted source time is a minimum requirement. If two provider side
        # clocks are supplied, both must independently be current.
        clocks = ('quoteAt',) + tuple(k for k in ('bidAt', 'askAt') if k in q)
        if not all(recent(q.get(k)) for k in clocks):
            missing.append('Anzeigezeit')
        needed = [name for name in DETAIL_FIELDS if name in missing]
        if needed:
            result.append({'isin': isin, 'missingFields': needed})
        if len(result) == 10:
            break
    return result

def validate(value, now):
    if not isinstance(value,dict) or set(value)!={'batchId','sessionId','images'}:
        raise ValueError('Invalid list batch')
    if any(not isinstance(value[k],str) or not re.fullmatch('[a-f0-9]{32}',value[k]) for k in ('batchId','sessionId')):
        raise ValueError('Invalid list identity')
    images=value['images']
    if not isinstance(images,list) or not 1<=len(images)<=4:raise ValueError('One to four images required')
    seen=set();previous=0
    for image in images:
        if not isinstance(image,dict) or set(image) not in ({'at','png'},{'at','png','appText'}):raise ValueError('Invalid image')
        if 'appText' in image:
            text=image['appText']
            if not isinstance(text,dict) or set(text)!={'before','after'}:raise ValueError('Invalid app text')
            for readings in text.values():
                if not isinstance(readings,list) or not 1<=len(readings)<=10:raise ValueError('Invalid app rows')
                if any(not isinstance(row,str) or not 1<=len(row)<=800 or '\x00' in row for row in readings):raise ValueError('Invalid app row')
            if text['before']!=text['after']:raise ValueError('App text changed during capture')
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

IMPORT_STAGES = frozenset(('waiting-memory','fetching','images-ready','reading','stored','synced','fetch-failed','read-failed','store-failed','superseded'))

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
    if payload['action']=='list-details':
        value=payload.get('value')
        if not isinstance(value,dict) or set(value)!={'batchId','run'} or not isinstance(value['batchId'],str) or not re.fullmatch('[a-f0-9]{32}',value['batchId']):raise ValueError('Invalid detail batch')
        row=conn.execute('SELECT import_receipt, parsed_items FROM bob_android_list_images WHERE batch_id=%s AND token_hash=%s',(value['batchId'],digest)).fetchone()
        if not row or not row[0] or row[0].get('stage') not in ('synced','superseded'):raise PermissionError('No owned imported list')
        run=value['run']
        candidates={x['isin'] for x in (row[1] or []) if not x.get('listRow',{}).get('excluded')}
        if not isinstance(run,dict) or not isinstance(run.get('isins'),list) or not run['isins'] or any(not isinstance(i,str) or i not in candidates for i in run['isins']):raise ValueError('Details outside imported list')
        # Store original observations, never turn receipt time into quote time.
        return __import__('android_observations').handle(conn,{'action':'save','run':run})
    if payload['action']=='list-status':
        batch=payload.get('value',{}).get('batchId')
        if not isinstance(batch,str) or not re.fullmatch('[a-f0-9]{32}',batch):raise ValueError('Invalid batch')
        row=conn.execute('SELECT import_receipt, parsed_items FROM bob_android_list_images WHERE batch_id=%s AND token_hash=%s',(batch,digest)).fetchone()
        plan=[]
        if row and row[0] and row[0].get('stage')=='synced':
            saved=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
            products=(saved[0] or {}).get('products',[]) if saved else []
            plan=detail_plan(row[1] or [],products,now)
        return {'ok':True,'batchId':batch,'import':row[0] if row else None,'detailIsins':[x['isin'] for x in plan],'detailPlan':plan}
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
