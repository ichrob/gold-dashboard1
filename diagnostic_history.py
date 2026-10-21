"""Private bounded diagnostic journal. Passive, asynchronous, never an order path."""
from collections import deque
import hashlib
import json
import os
import re
import threading
import time
import uuid
import bob_diagnostics as diag

STAGES = ('input','analysis','analysis-failed','push','health','transport')
_QUEUE = deque(maxlen=256)
_LOCK = threading.Lock()
_RUNNING = False
_DATABASE = None
_LAST_PRUNE = 0.0
_PRUNE_INTERVAL_SECONDS = 1800
_PRUNE_TIMEOUT = '5s'
_STATS = {'stored':0,'dropped':0,'failures':0,'lastStoredAt':None}
SCHEMAS = {
    'transport':diag.shape('outcome','errorType'),
    'input':diag.shape('spot_price_as_of','primary','xaus','fetchedAt',counts=diag.shape('1m','5m','15m','30m','1h','4h')),
    'analysis':diag.shape('timeframe','purpose',result=diag.ANALYSIS),
    'analysis-failed':diag.shape('timeframe','errorType'),
    'push':diag.shape('outcome','eventsCount',events=[diag.shape('kind','outcome','reason','at')]),
    'health':diag.shape('status','session','sourceAt','sourceAgeSeconds','cycleAt','backgroundAt',badCodes=[None],goodCodes=[None]),
}


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_diagnostic_history (
        id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, decision_id TEXT,
        stage TEXT NOT NULL, observed_at DOUBLE PRECISION NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(), build TEXT, payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_diagnostic_history_time ON bob_diagnostic_history(recorded_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_diagnostic_history_stage ON bob_diagnostic_history(stage,recorded_at DESC)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_diagnostic_history_source_window ON bob_diagnostic_history(stage,observed_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_diagnostic_history_trace ON bob_diagnostic_history(trace_id,recorded_at)')


def configure(database):
    global _DATABASE
    _DATABASE = database


def trace(bundle):
    """Same source snapshot keeps the same trace across services; no settings hashed."""
    source=(bundle or {}).get('spots') or {}
    raw=json.dumps([source.get('spot_price_as_of'),source.get('xaus'),(bundle or {}).get('fetched_at')],sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def validate(event):
    if not isinstance(event,dict) or event.get('stage') not in STAGES:raise ValueError('Invalid stage')
    for key in ('id','traceId'):
        if not re.fullmatch('[a-f0-9]{32}',str(event.get(key,''))):raise ValueError('Invalid identifier')
    decision=event.get('decisionId')
    if decision is not None and not re.fullmatch('[a-f0-9]{32}',str(decision)):raise ValueError('Invalid decision')
    at=event.get('at')
    if type(at) not in (int,float) or not time.time()-86400 <= at <= time.time()+60:raise ValueError('Invalid time')
    build=event.get('build')
    if not re.fullmatch('[a-f0-9]{7,64}',str(build)):build=None
    return {**{k:event.get(k) for k in ('id','traceId','decisionId','stage','at')},'build':build,
            'payload':diag.project(event.get('payload'),SCHEMAS[event['stage']])}


def original_spot(payload, observed_at):
    """An original Gold-API input, fresh AT capture; never a reconstructed tick."""
    if not isinstance(payload,dict) or payload.get('primary')!='Gold-API.com · XAU/USD Spot':
        return None
    from bob_market_store import point
    try:
        return point(dict(symbol='XAU',currency='USD',price=payload.get('xaus'),
                          at=payload.get('spot_price_as_of')),now=observed_at)
    except (ValueError,TypeError,OverflowError):
        return None


def write(conn,event):
    global _LAST_PRUNE
    e=validate(event)
    conn.execute('''INSERT INTO bob_diagnostic_history(id,trace_id,decision_id,stage,observed_at,build,payload)
        VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(id) DO NOTHING''',
        (e['id'],e['traceId'],e['decisionId'],e['stage'],e['at'],e['build'],json.dumps(e['payload'],allow_nan=False)))
    source=original_spot(e['payload'],e['at']) if e['stage']=='input' else None
    if source:
        # The journal is an independent delivery path for the SAME original
        # source observation. A conflicting stored price is never overwritten.
        try:
            with conn.transaction():
                conn.execute('''INSERT INTO bob_spot_observations(stream,quote_at,price)
                    VALUES('gold-api-xau-usd-v1',%s,%s) ON CONFLICT DO NOTHING''',source)
        except Exception:
            print('BOB_DIAGNOSTIC_SPOT archive=unavailable',flush=True)
    if time.monotonic()-_LAST_PRUNE>=_PRUNE_INTERVAL_SECONDS:
        # Retention maintenance is best-effort. Delivery keeps its short timeout,
        # while the bounded maintenance batch gets a separate finite budget.
        # A savepoint still prevents a timeout from rolling back this event.
        try:
            with conn.transaction():
                conn.execute("SET LOCAL statement_timeout='"+_PRUNE_TIMEOUT+"'")
                removed=prune(conn)
            print('BOB_DIAGNOSTIC_PRUNE status=completed removed='+str(removed),flush=True)
        except Exception as exc:
            print('BOB_DIAGNOSTIC_PRUNE status=deferred error='+
                  type(exc).__name__,flush=True)
        finally:
            _LAST_PRUNE=time.monotonic()


def prune(conn):
    old=conn.execute("""DELETE FROM bob_diagnostic_history WHERE id IN
        (SELECT id FROM bob_diagnostic_history
         WHERE recorded_at < now()-interval '7 days'
         ORDER BY recorded_at LIMIT 500 FOR UPDATE SKIP LOCKED)""")
    capped=conn.execute('''DELETE FROM bob_diagnostic_history WHERE id IN
        (SELECT h.id FROM bob_diagnostic_history h
         JOIN (SELECT id FROM bob_diagnostic_history
               ORDER BY recorded_at DESC OFFSET 60000 LIMIT 500) victims USING (id)
         FOR UPDATE OF h SKIP LOCKED)''')
    counts=(getattr(old,'rowcount',0),getattr(capped,'rowcount',0))
    return sum(value for value in counts if isinstance(value,int) and value>0)


def emit(stage,trace_id,payload,decision_id=None):
    """Failure-isolated enqueue; no database/network work in caller."""
    global _RUNNING
    try:
        event=validate({'id':uuid.uuid4().hex,'traceId':trace_id,'decisionId':decision_id,
            'stage':stage,'at':time.time(),'build':os.environ.get('RENDER_GIT_COMMIT'),'payload':payload})
        with _LOCK:
            if len(_QUEUE)==_QUEUE.maxlen:_STATS['dropped']+=1
            _QUEUE.append(event)
            if not _RUNNING and (_DATABASE or os.environ.get('PUSH_SERVICE_TOKEN')):
                _RUNNING=True
                threading.Thread(target=_sender,daemon=True,name='bob-diagnostic-history').start()
    except Exception:
        with _LOCK:_STATS['failures']+=1


def _sender():
    global _RUNNING
    while True:
        with _LOCK:
            if not _QUEUE:_RUNNING=False;return
            event=_QUEUE[0]
        try:
            if _DATABASE:
                with _DATABASE() as conn:
                    conn.execute("SET LOCAL statement_timeout='1500ms'")
                    write(conn,event)
            else:
                from urllib.request import Request,build_opener
                from bob_auth import NoRedirect
                base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/')
                if not base.startswith(('https://','http://')):base='http://'+base
                req=Request(base+'/diagnostic-history',data=json.dumps(event).encode(),method='POST',
                    headers={'Content-Type':'application/json','X-Bob-Push-Token':os.environ.get('PUSH_SERVICE_TOKEN','')})
                with build_opener(NoRedirect()).open(req,timeout=5) as response:
                    if json.loads(response.read(1024)).get('ok') is not True:raise ValueError('No acknowledgement')
            with _LOCK:
                if _QUEUE and _QUEUE[0]['id']==event['id']:_QUEUE.popleft()
                _STATS['stored']+=1;_STATS['lastStoredAt']=time.time()
        except Exception:
            with _LOCK:_STATS['failures']+=1
            time.sleep(10)


def status():
    with _LOCK:return {**_STATS,'queued':len(_QUEUE),'running':_RUNNING,'scope':'process-local-delivery-counters'}


def health(health):
    import bob_self_healing
    import background_push
    bad=bob_self_healing.classify(health)
    good=[]
    collection=health.get('automaticCollection') or {}
    bg=health.get('fibonacciMonitor') or {}
    research=health.get('strategyResearch') or {}
    if collection.get('enabled') and collection.get('running'):
        good+=['market-worker-stopped']
        if 'market-feed-not-current' not in bad:good+=['market-feed-not-current']
    if bg.get('configured') and bg.get('status') in ('active','idle','paused') and 'background-not-current' not in bad:
        good+=['background-worker-stopped','background-not-current']
    if research.get('enabled') and research.get('running') and research.get('phase') not in ('retry','starting','unconfigured'):
        good+=['research-worker-stopped']
    for code,state in (health.get('auxiliaryWorkers') or {}).items():
        at=state.get('successfulAt')
        if code in bob_self_healing.WORKERS and state.get('running') and type(at) in (int,float) and 0<=time.time()-at<=650 and state.get('state') not in ('unavailable','error','stale','starting'):
            good.append(code)
    if (health.get('repairSupervision') or {}).get('state')=='ok':good+=['repair-watch-stalled']
    feed=collection.get('cfdFeed') or {}
    emit('health',uuid.uuid4().hex,{'status':health.get('status'),'session':background_push.degiro_session(),
        'sourceAt':feed.get('lastCheckedAt'),'sourceAgeSeconds':feed.get('sourceAgeSeconds'),
        'cycleAt':collection.get('lastCycleAt'),'backgroundAt':bg.get('lastSuccessAt'),
        'badCodes':bad,'goodCodes':[c for c in good if c not in bad]})


def report(conn):
    with conn.transaction():
        return _report(conn)


def _report(conn):
    rows=conn.execute("""SELECT h.id,h.trace_id,h.decision_id,h.stage,h.observed_at,h.build,h.payload
        FROM (VALUES ('input'),('analysis'),('analysis-failed'),('push'),('health'),('transport')) stages(stage)
        CROSS JOIN LATERAL (SELECT * FROM bob_diagnostic_history WHERE stage=stages.stage
            ORDER BY recorded_at DESC LIMIT 20) h ORDER BY h.recorded_at DESC""").fetchall()
    events=[dict(id=r[0],traceId=r[1],decisionId=r[2],stage=r[3],observedAt=r[4],build=r[5],payload=diag.project(r[6],SCHEMAS[r[3]])) for r in rows]
    repairs=conn.execute('''SELECT e.code,e.kind,e.event_at,
        count(*) FILTER (WHERE h.payload->'goodCodes' ? e.code),
        count(*) FILTER (WHERE h.payload->'badCodes' ? e.code),
        max(h.observed_at),min(h.observed_at),
        (SELECT count(*) FROM bob_self_heal_events again WHERE again.code=e.code
            AND again.kind='detected' AND again.event_at>e.event_at)
        FROM (SELECT code,kind,event_at FROM bob_self_heal_events
              WHERE kind IN ('repair-verified','recovered') AND event_at>now()-interval '7 days'
              ORDER BY event_at DESC LIMIT 20) e
        LEFT JOIN bob_diagnostic_history h ON h.stage='health' AND h.observed_at>extract(epoch FROM e.event_at)
          AND (h.payload->'goodCodes' ? e.code OR h.payload->'badCodes' ? e.code)
        GROUP BY e.code,e.kind,e.event_at ORDER BY e.event_at DESC''').fetchall()
    followups=[]
    for code,kind,at,good,bad,last,first,recorded_recurrences in repairs:
        state=('recurred' if bad or recorded_recurrences else 'observed-stable' if good>=2 and last-first>=300 and time.time()-last<=120
               else 'pending-or-stale')
        followups.append(dict(code=code,recoveryKind=kind,recoveredAt=at.isoformat(),goodChecks=good,
                              badChecks=bad,recordedRecurrences=recorded_recurrences,lastCheckAt=last,state=state))
    return {'status':'observed' if rows else 'warming','retentionDays':7,'maxEvents':60000,
            'events':events,'reportLimitPerStage':20,'repairFollowups':followups,'delivery':status(),
            'scope':'sampled-server-observations-not-proof-of-causality-or-handset-delivery',
            'note':'No historical backfill. Unflushed queue entries may be lost on process termination. No observations means unverified.'}
