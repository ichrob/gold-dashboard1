"""Source-separated candle checkpoints and observed reliability, never trading rules."""
import copy
import json
import math
import os
import threading
import time
from urllib.request import Request, build_opener
from bob_auth import NoRedirect

FRAMES = {'1m':1,'5m':5,'15m':15,'30m':30,'1h':60,'4h':240}
SOURCES = {'biquote':'biquote · XAU/USD Broker/MT5','xaus':'XAUS · datierte XAU/USD-Historie'}
KEYS = {f'{source}/{tf}' for source in SOURCES for tf in FRAMES}
_LOCK = threading.RLock()
_THREAD = None
_ROWS = {}
_CHECKS = {}
_STATS = {}
_SAVED = {}
_STORAGE = {'state':'starting','lastSavedAt':None,'restoredSeries':0}
_STARTED = time.time()


def validated(key, rows, now=None):
    now = time.time() if now is None else now
    if key not in KEYS or not isinstance(rows,list) or len(rows)>2000:
        raise ValueError('Invalid candle checkpoint')
    source,tf = key.split('/')
    step = FRAMES[tf]*60000
    out=[]
    previous=0
    for b in rows:
        ts=b.get('openTime') if isinstance(b,dict) else None
        if (type(ts) not in (int,float) or not math.isfinite(ts) or ts<=previous or ts%step
            or ts+step>now*1000 or b.get('isOpen') or b.get('providerIsOpen')
            or b.get('estimated') or b.get('instrument')!='XAU/USD'
            or b.get('source')!=SOURCES[source]):
            raise ValueError('Invalid candle provenance')
        prices=[b.get(k) for k in ('open','high','low','close')]
        if any(type(p) not in (int,float) or not math.isfinite(p) or p<=0 for p in prices):
            raise ValueError('Invalid OHLC')
        o,h,l,c=prices
        if l>min(o,c) or h<max(o,c):raise ValueError('Invalid OHLC bounds')
        out.append(dict(openTime=ts,open=o,high=h,low=l,close=c,isOpen=False,
                        providerIsOpen=False,instrument='XAU/USD',source=SOURCES[source]))
        previous=ts
    return out


def observe(source, tf, rows=None, error=None):
    """Memory only in the price path. Database/network work is asynchronous."""
    key=f'{source}/{tf}'
    if key not in KEYS:return
    now=time.time()
    with _LOCK:
        _CHECKS[key]={'checkedAt':now,'error':error}
        if rows is not None:
            try:
                closed=[b for b in rows if not b.get('isOpen') and not b.get('providerIsOpen')
                        and b.get('openTime',now*1000)+FRAMES[tf]*60000<=now*1000]
                clean=validated(key,closed[-2000:],now)
            except (ValueError,TypeError,KeyError):
                _CHECKS[key]['error']='incomplete'
                return
            if clean:
                old=_ROWS.get(key,[])
                if not old or clean[-1]['openTime']>=old[-1]['openTime']:
                    older=[b for b in old if b['openTime']<clean[0]['openTime']]
                    _ROWS[key]=(older+clean)[-2000:]
            else:_CHECKS[key]['error']='incomplete'


def classify(rows, tf, now):
    # Reuse the actual analysis integrity rules, including instrument/OHLC checks.
    from market_review import frame_health
    confirmed=[b for b in rows if not b.get('providerIsOpen')]
    state=frame_health(confirmed,tf,now*1000)['state']
    return {'ok':'current','missing':'unavailable','stale':'stale'}.get(state,'incomplete')


def transition(old,state,now,source_at=None):
    """Count only observed intervals; restart/monitor gaps are explicitly unknown."""
    row=copy.deepcopy(old) if old else dict(incidents=0,badSeconds=0,unknownSeconds=0,
        longestObservedSeconds=0,currentObservedSeconds=0,events=[],since=now)
    previous=row.get('state','unknown')
    delta=max(0,now-row.get('checkedAt',now))
    if delta>90:
        row['unknownSeconds']+=delta
    elif previous in ('unavailable','stale','incomplete'):
        row['badSeconds']+=delta
        row['currentObservedSeconds']+=delta
        row['longestObservedSeconds']=max(row['longestObservedSeconds'],row['currentObservedSeconds'])
    bad=state in ('unavailable','stale','incomplete')
    if bad and previous not in ('unavailable','stale','incomplete'):
        row['incidents']+=1
        row['currentObservedSeconds']=0
    if state!=previous:
        row['events']=(row['events']+[{'at':now,'state':state,'from':previous}])[-20:]
    if not bad:row['currentObservedSeconds']=0
    row.update(state=state,checkedAt=now,sourceAt=source_at)
    return row


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_candle_evidence (
        source_key TEXT NOT NULL, open_time BIGINT NOT NULL,
        fingerprint TEXT NOT NULL, payload JSONB NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(source_key,open_time,fingerprint))""")
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_candle_checkpoints (
        key TEXT PRIMARY KEY, latest DOUBLE PRECISION NOT NULL,
        payload JSONB NOT NULL, saved_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_source_reliability (
        id INTEGER PRIMARY KEY CHECK (id=1), owner_started DOUBLE PRECISION NOT NULL DEFAULT 0, payload JSONB NOT NULL,
        saved_at TIMESTAMPTZ NOT NULL DEFAULT now())''')


def handle(conn,action,payload):
    if action=='read':
        key=payload.get('key')
        if key=='statistics':
            row=conn.execute('SELECT payload FROM bob_source_reliability WHERE id=1').fetchone()
            return {'statistics':row[0] if row else {}}
        if key not in KEYS:raise ValueError('Invalid checkpoint key')
        row=conn.execute('SELECT payload FROM bob_candle_checkpoints WHERE key=%s',(key,)).fetchone()
        return {'rows':row[0] if row else []}
    if action!='write':raise ValueError('Invalid checkpoint action')
    key=payload.get('key')
    if key=='statistics':
        data=payload.get('statistics')
        if not isinstance(data,dict) or len(json.dumps(data))>60000:raise ValueError('Invalid statistics')
        owner=payload.get('ownerStartedAt')
        if type(owner) not in (int,float) or not math.isfinite(owner) or not 0<owner<=time.time()+5:
            raise ValueError('Invalid monitor identity')
        conn.execute("INSERT INTO bob_source_reliability(id,payload) VALUES(1,'{}'::jsonb) ON CONFLICT DO NOTHING")
        saved,old_owner=conn.execute('SELECT payload,owner_started FROM bob_source_reliability WHERE id=1 FOR UPDATE').fetchone()
        if owner<old_owner:return {'ok':True,'statistics':saved}
        allowed=KEYS|{'analysis/'+tf for tf in FRAMES}|{'spot/Gold-API'}
        for key,row in data.items():
            if key not in allowed or not isinstance(row,dict):raise ValueError('Invalid monitor key')
            state=row.get('state');at=row.get('checkedAt')
            if state not in ('current','stale','unavailable','incomplete','paused','unknown') or type(at) not in (int,float) or not math.isfinite(at) or not 0<=time.time()-at<=180:
                raise ValueError('Invalid observation')
            if at>=saved.get(key,{}).get('checkedAt',0):
                saved[key]=transition(saved.get(key),state,at,row.get('sourceAt'))
        conn.execute('UPDATE bob_source_reliability SET payload=%s::jsonb,owner_started=%s,saved_at=now() WHERE id=1',
                     (json.dumps(saved,allow_nan=False),owner))
        return {'ok':True,'statistics':saved}
    else:
        rows=validated(key,payload.get('rows'))
        if not rows:raise ValueError('Empty checkpoint')
        # Preserve all accepted candle revisions before replacing the rolling checkpoint.
        conn.execute("""INSERT INTO bob_candle_evidence(source_key,open_time,fingerprint,payload)
            SELECT %s,(value->>'openTime')::numeric::bigint,
                encode(sha256(convert_to(value::text,'UTF8')),'hex'),value
            FROM jsonb_array_elements(%s::jsonb)
            ON CONFLICT DO NOTHING""",(key,json.dumps(rows,allow_nan=False)))
        conn.execute('''INSERT INTO bob_candle_checkpoints(key,latest,payload) VALUES(%s,%s,%s::jsonb)
            ON CONFLICT(key) DO UPDATE SET latest=excluded.latest,payload=excluded.payload,saved_at=now()
            WHERE (excluded.latest>bob_candle_checkpoints.latest OR
                (excluded.latest=bob_candle_checkpoints.latest AND jsonb_array_length(excluded.payload)>=jsonb_array_length(bob_candle_checkpoints.payload)))
                AND bob_candle_checkpoints.payload IS DISTINCT FROM excluded.payload''',
            (key,rows[-1]['openTime'],json.dumps(rows,allow_nan=False)))
    return {'ok':True}


def request(action,payload):
    base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/')
    token=os.environ.get('PUSH_SERVICE_TOKEN','')
    if not base or not token:raise OSError('Checkpoint storage unavailable')
    if not base.startswith(('http://','https://')):base='http://'+base
    req=Request(base+'/market-candles/'+action,data=json.dumps(payload).encode(),
        headers={'Content-Type':'application/json','X-Bob-Push-Token':token},method='POST')
    with build_opener(NoRedirect()).open(req,timeout=5) as response:raw=response.read(1048577)
    if len(raw)>1048576:raise ValueError('Checkpoint response too large')
    result=json.loads(raw)
    if not isinstance(result,dict):raise ValueError('Invalid checkpoint response')
    return result


def restore(server):
    restored=0
    # Restore counts first, then source-separated series. No source timestamps change.
    statistics=request('read',{'key':'statistics'}).get('statistics',{})
    with _LOCK:
        if isinstance(statistics,dict):_STATS.update(statistics)
    for key in sorted(KEYS):
        rows=validated(key,request('read',{'key':key}).get('rows',[]))
        if not rows:continue
        source,tf=key.split('/')
        with _LOCK:
            current=_ROWS.get(key,[])
            if not current or current[-1]['openTime']<rows[-1]['openTime']:_ROWS[key]=rows
        # Active-memory selection still enforces original clocks and source isolation.
        server.retain_technical_history(tf,rows)
        if source=='biquote':
            import technical_candles
            with technical_candles._locks[tf]:
                saved=technical_candles._cache.get(tf)
                current=saved[1] if saved else []
                if not current or current[-1]['openTime']<rows[-1]['openTime']:
                    technical_candles._cache[tf]=(0,rows[-1000:])
        if source=='xaus':
            with server._ema_backfill_lock:
                current=server._ema_backfill_series.get(tf,[])
                if not current or current[-1]['openTime']<rows[-1]['openTime']:
                    server._ema_backfill_series[tf]=rows
        restored+=1
    with _LOCK:_STORAGE.update(restoredSeries=restored,state='ready')


def cycle(server, now=None, paused=False):
    now=time.time() if now is None else now
    with _LOCK:
        snapshots=copy.deepcopy(_ROWS)
        for key in sorted(KEYS):
            rows=snapshots.get(key,[])
            check=_CHECKS.get(key,{})
            state=classify(rows,key.split('/')[1],now)
            if check.get('error') in ('unavailable','incomplete'):state=check['error']
            if paused:state='paused'
            if not rows and not check and now-_STARTED<90:state='unknown'
            _STATS[key]=transition(_STATS.get(key),state,now,rows[-1]['openTime'] if rows else None)
    live=getattr(server,'_live_cache',None) or {}
    active_frames=(live.get('history') or {}).get('bars_by_tf') or {}
    for tf in FRAMES:
        rows=active_frames.get(tf,[])
        state='paused' if paused else classify(rows,tf,now)
        if not rows and now-_STARTED<90:state='unknown'
        with _LOCK:
            key='analysis/'+tf
            _STATS[key]=transition(_STATS.get(key),state,now)
    from datetime import datetime
    spots=(getattr(server,'_live_cache',None) or {}).get('spots',{})
    try:
        at=datetime.fromisoformat(spots['spot_price_as_of'].replace('Z','+00:00')).timestamp()
        state='current' if 0<=now-at<=120 else 'stale'
        if not spots.get('is_genuine_xauusd_spot'):state='incomplete'
    except (KeyError,ValueError,TypeError,AttributeError):
        at=None
        state='unknown' if now-_STARTED<90 else 'unavailable'
    with _LOCK:_STATS['spot/Gold-API']=transition(_STATS.get('spot/Gold-API'),'paused' if paused else state,now,at*1000 if at else None)
    for key,rows in snapshots.items():
        digest=json.dumps(rows,separators=(',',':'))
        if _SAVED.get(key)==digest:continue
        request('write',{'key':key,'rows':rows})
        _SAVED[key]=digest
    with _LOCK:stats=copy.deepcopy(_STATS)
    result=request('write',{'key':'statistics','statistics':stats,'ownerStartedAt':_STARTED})
    with _LOCK:
        if isinstance(result.get('statistics'),dict):_STATS.update(result['statistics'])
    with _LOCK:_STORAGE.update(state='ready',lastSavedAt=now)


def snapshot():
    with _LOCK:
        if _STORAGE.get('lastSavedAt') and time.time()-_STORAGE['lastSavedAt']>120:
            _STORAGE['state']='stale'
        return {'status':'observed','storage':dict(_STORAGE),'sources':copy.deepcopy(_STATS),
        'note':'Beobachtete Ausfallzeiten seit Messbeginn; Überwachungslücken werden separat gezählt. Keine Handelsfreigabe.'}


def _loop():
    import server, background_push
    restored=False
    while True:
        try:
            if not restored:
                restore(server)
                restored=True
            cycle(server,paused=background_push.degiro_session()!='trading')
        except Exception as exc:
            with _LOCK:_STORAGE['state']='unavailable'
            print('BOB_CANDLE_ARCHIVE state=unavailable error='+type(exc).__name__,flush=True)
        time.sleep(30)


def start():
    global _THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _THREAD=threading.Thread(target=_loop,name='bob-candle-checkpoints',daemon=True)
            _THREAD.start()
