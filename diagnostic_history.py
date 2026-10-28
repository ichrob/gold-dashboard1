"""Private bounded diagnostic journal. Passive, asynchronous, never an order path."""
from collections import deque
import hashlib
import json
import math
from datetime import datetime, timezone
import os
import re
import threading
import time
import uuid
import bob_diagnostics as diag

STAGES = ('input','analysis','analysis-failed','push','push-delivery','paper-input','health','transport')
_QUEUE = deque(maxlen=256)
_LOCK = threading.Lock()
_PRUNE_LOCK = threading.Lock()
_RUNNING = False
_DATABASE = None
# A newly started Render instance must first allow startup/database work to settle.
# Retention is maintenance, not a prerequisite for diagnostic delivery.
_LAST_PRUNE = time.monotonic()
_PRUNE_INTERVAL_SECONDS = 1800
_PRUNE_TIMEOUT = '5s'
_PRUNE_ADVISORY_LOCK = 'bob-diagnostic-history-prune-v1'
# Live stage telemetry isolated repeated five-second timeouts to the 2,000-row
# cap delete, while the existing 500-row age delete continued to complete.
# Keep the same journal cap and cadence, but bound the expensive index cleanup
# to the already proven maintenance batch size.
_PRUNE_CAP_BATCH_SIZE = 500
_STATS = {'stored':0,'dropped':0,'failures':0,'lastStoredAt':None}


class _PruneStageError(Exception):
    """Sanitized retention failure with the bounded stage that failed."""

    def __init__(self, stage, cause):
        super().__init__(stage)
        self.stage = stage
        self.error_type = type(cause).__name__


SCHEMAS = {
    'transport':diag.shape('outcome','errorType'),
    'input':diag.shape('spot_price_as_of','primary','xaus','fetchedAt',counts=diag.shape('1m','5m','15m','30m','1h','4h')),
    'analysis':diag.shape('timeframe','purpose',result=diag.ANALYSIS),
    'analysis-failed':diag.shape('timeframe','errorType'),
    'push':diag.shape('outcome','eventsCount',events=[diag.shape('kind','outcome','reason','at')]),
    'push-delivery':diag.shape('outcome','httpStatus','direction','signalBarAt','dataAt',
                               'test','synthetic','receiptId','receiptState',eventKinds=[None]),
    'paper-input':diag.shape('phase','checkedAt',profiles=[diag.shape(
        'profile','outcome','ready','priceFresh','dataAt','barAt')]),
    'health':diag.shape('status','session','sourceAt','sourceAgeSeconds','cycleAt','backgroundAt','evidenceVersion',badCodes=[None],goodCodes=[None]),
}


def init(conn):
    __import__("storage_budget").init(conn)
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
    __import__("storage_budget").maybe_observe(conn)
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
    if (time.monotonic()-_LAST_PRUNE>=_PRUNE_INTERVAL_SECONDS
            and _PRUNE_LOCK.acquire(blocking=False)):
        # Retention maintenance is best-effort. Delivery keeps its short timeout,
        # while the bounded maintenance batch gets a separate finite budget.
        # A savepoint still prevents a timeout from rolling back this event.
        try:
            try:
                with conn.transaction():
                    conn.execute("SET LOCAL statement_timeout='"+_PRUNE_TIMEOUT+"'")
                    removed=prune(conn)
                print('BOB_DIAGNOSTIC_PRUNE status=completed removed='+str(removed),flush=True)
            except _PruneStageError as exc:
                print('BOB_DIAGNOSTIC_PRUNE status=deferred stage='+exc.stage+
                      ' error='+exc.error_type,flush=True)
            except Exception as exc:
                print('BOB_DIAGNOSTIC_PRUNE status=deferred stage=transaction error='+
                      type(exc).__name__,flush=True)
            finally:
                _LAST_PRUNE=time.monotonic()
        finally:
            _PRUNE_LOCK.release()


def prune(conn):
    # Scanner and push-service share the same journal but run in separate
    # processes, so the in-process mutex above cannot serialize deploy-time
    # retention.  A transaction-scoped, non-blocking PostgreSQL lock makes
    # exactly one service prune while the other keeps delivering diagnostics.
    try:
        locked=conn.execute(
            'SELECT pg_try_advisory_xact_lock(hashtext(%s))',
            (_PRUNE_ADVISORY_LOCK,)).fetchone()
    except Exception as exc:
        raise _PruneStageError('advisory-lock', exc) from exc
    if not locked or locked[0] is not True:
        return 0
    try:
        old=conn.execute("""DELETE FROM bob_diagnostic_history WHERE id IN
            (SELECT id FROM bob_diagnostic_history
             WHERE recorded_at < now()-interval '7 days'
             ORDER BY recorded_at LIMIT 500 FOR UPDATE SKIP LOCKED)""")
    except Exception as exc:
        raise _PruneStageError('age-delete', exc) from exc
    # Journal rows are append-only. Select physical tuple IDs and delete them
    # in the SAME statement/snapshot, avoiding a second full journal ID join.
    # The advisory lock above serializes maintenance across both services.
    # Only the pre-existing 60,000-row journal cap applies; raw archives are
    # separate tables and are never touched by this maintenance.
    try:
        capped=conn.execute('''DELETE FROM bob_diagnostic_history
            WHERE ctid = ANY(ARRAY(
                SELECT ctid FROM bob_diagnostic_history
                ORDER BY recorded_at DESC OFFSET 60000 LIMIT %s))''',
            (_PRUNE_CAP_BATCH_SIZE,))
    except Exception as exc:
        raise _PruneStageError('cap-delete', exc) from exc
    counts=(getattr(old,'rowcount',0),getattr(capped,'rowcount',0))
    return sum(value for value in counts if isinstance(value,int) and value>0)


def emit(stage,trace_id,payload,decision_id=None,event_id=None):
    """Failure-isolated enqueue; no database/network work in caller."""
    global _RUNNING
    try:
        event=validate({'id':event_id or uuid.uuid4().hex,'traceId':trace_id,'decisionId':decision_id,
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


def _recent_original_success(value, now=None, freshness_seconds=650):
    """Validate original post-work clock, never a mere poll/heartbeat time.

    Accept UTC-aware ISO 8601, Unix seconds or Unix milliseconds, not booleans,
    local/naive strings, futures, wall-time estimates or stale observations.
    """
    now = time.time() if now is None else now
    if type(now) not in (int, float) or not math.isfinite(now):
        return False
    if type(value) in (int, float) and math.isfinite(value):
        observed = float(value)
        if observed > 1e11:
            observed /= 1000
    elif isinstance(value, str) and len(value) <= 48:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return False
            observed = parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            return False
    else:
        return False
    return 0 <= now - observed <= freshness_seconds


def health(health):
    """Archive only explicit successful source cycles, not 'running' or pause.

    Legacy health event goodCodes lacked cycle proof. evidenceVersion=2
    distinguishes reliable followups and prevents old weekend status samples
    from being back-labelled as independently verified repair outcomes.
    """
    import bob_self_healing
    import background_push
    bad = bob_self_healing.classify(health)
    good = []
    collection = health.get('automaticCollection') or {}
    bg = health.get('fibonacciMonitor') or {}
    research = health.get('strategyResearch') or {}
    session = background_push.degiro_session()
    feed = collection.get('cfdFeed') or {}
    now = time.time()
    # An active collection thread is no proof that a cycle completed.
    if (session != 'weekend' and collection.get('enabled')
            and collection.get('running')
            and collection.get('state') in ('ready', 'estimating', 'collecting')
            and _recent_original_success(collection.get('lastCycleAt'), now)):
        good.append('market-worker-stopped')
        # A source quote is different from a completed worker evaluation.
        # Never mark missing market data recovered from thread liveness alone.
        if ('market-feed-not-current' not in bad
                and feed.get('state') == 'current'
                and _recent_original_success(feed.get('sourceAt'), now, 120)
                and _recent_original_success(feed.get('successfulAt'), now, 120)):
            good.append('market-feed-not-current')
    if (bg.get('configured') and bg.get('status') in ('active', 'idle')
            and 'background-not-current' not in bad
            and _recent_original_success(bg.get('lastSuccessAt'), now)):
        good += ['background-worker-stopped', 'background-not-current']
    if (research.get('enabled') and research.get('running')
            and research.get('phase') not in ('retry', 'starting', 'unconfigured', 'paused')
            and _recent_original_success(research.get('lastSuccessAt'), now)):
        good.append('research-worker-stopped')
    for code,state in (health.get('auxiliaryWorkers') or {}).items():
        if not isinstance(state, dict):
            continue
        if (code in bob_self_healing.WORKERS and state.get('running')
                and state.get('state') not in
                ('unavailable', 'error', 'stale', 'starting', 'paused', 'closed')
                and _recent_original_success(state.get('successfulAt'), now)
                and (code != 'comparison-worker-stopped'
                     or state.get('archiveStatus') == 'loaded')):
            good.append(code)
    supervision = health.get('repairSupervision') or {}
    if (supervision.get('state') == 'ok' and supervision.get('running')
            and type(supervision.get('lastCompletedAgeSeconds')) in (int, float)
            and math.isfinite(supervision['lastCompletedAgeSeconds'])
            and 0 <= supervision['lastCompletedAgeSeconds'] <= 150):
        good.append('repair-watch-stalled')
    emit('health', uuid.uuid4().hex, {
        'status': health.get('status'),
        'session': session,
        'sourceAt': feed.get('lastCheckedAt'),
        'sourceAgeSeconds': feed.get('sourceAgeSeconds'),
        'cycleAt': collection.get('lastCycleAt'),
        'backgroundAt': bg.get('lastSuccessAt'),
        'evidenceVersion': 2,
        'badCodes': bad,
        'goodCodes': [code for code in good if code not in bad],
    })

def report(conn):
    with conn.transaction():
        return _report(conn)


def _report(conn):
    # Every SCHEMAS stage must be read, not only stored. Especially a
    # provider-accepted push is not handset-delivered, and a paper worker's
    # captured input is not a real product fill. Bounded 20 rows per stage,
    # explicitly within seven days even when best-effort pruning is delayed.
    rows=conn.execute("""SELECT h.id,h.trace_id,h.decision_id,h.stage,h.observed_at,h.build,h.payload
        FROM (VALUES ('input'),('analysis'),('analysis-failed'),('push'),
                     ('push-delivery'),('paper-input'),('health'),('transport')) stages(stage)
        CROSS JOIN LATERAL (SELECT * FROM bob_diagnostic_history WHERE stage=stages.stage
            AND recorded_at >= now()-interval '7 days'
            ORDER BY recorded_at DESC LIMIT 20) h ORDER BY h.recorded_at DESC""").fetchall()
    events=[dict(id=r[0],traceId=r[1],decisionId=r[2],stage=r[3],observedAt=r[4],build=r[5],payload=diag.project(r[6],SCHEMAS[r[3]])) for r in rows]
    repairs=conn.execute('''SELECT e.code,e.kind,e.event_at,
        count(*) FILTER (WHERE h.payload->>'evidenceVersion'='2' AND h.payload->'goodCodes' ? e.code),
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
    from diagnostic_state_compare import compare as compare_health_snapshots
    from diagnostic_health_cadence import assess as assess_health_cadence
    comparison = compare_health_snapshots(events)
    cadence = assess_health_cadence(events)
    # The full journal is often response-size truncated. Preserve a tiny
    # aggregate with no identities, trace IDs, dates or raw payload data.
    # Counts are 0..20 per stage: a zero is NOT evidence of no sends/fills.
    sample_counts = {stage: sum(item['stage'] == stage for item in events)
                     for stage in STAGES}
    stage_coverage = {
        'status': 'observed' if rows else 'warming',
        'readOnly': True, 'realOrders': False,
        'totalSampled': len(events), 'limitPerStage': 20,
        'counts': sample_counts,
        'handsetDeliveryVerified': False,
        'paperExecutionVerified': False,
        'scope': 'last-twenty-per-stage-seven-day-best-effort-journal',
        'note': 'Missing captures, older events and asynchronous drops are not '
                'proof that no push was sent or that no simulation ran.',
    }
    return {'status':'observed' if rows else 'warming','retentionDays':7,'maxEvents':60000,
            'events':events,'reportLimitPerStage':20,'repairFollowups':followups,'delivery':status(),
            'stateComparison':comparison['stateComparison'],
            'deploymentComparison':comparison['deploymentComparison'],
            'healthCadence':cadence,
            'stageCoverage':stage_coverage,
            'comparisonScope':comparison['limitations'],
            'scope':'sampled-server-observations-not-proof-of-causality-or-handset-delivery',
            'note':'No historical backfill. Unflushed queue entries may be lost on process termination. No observations means unverified.'}
