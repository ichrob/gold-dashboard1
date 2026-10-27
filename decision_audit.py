"""Immutable decision evidence and forward-only outcome review. No orders or self-modifying code."""
import hashlib
import bisect
import json
import math
import os
import time
import threading
import copy
import intraday_comparison
import signal_review
import adaptive_learning as rule_learning
import audit_history
import decision_evidence
import stop_target_audit
import paper_simulation
import optimization_review
import entry_experiment
import market_optimization
import metric_quality
import product_precision
import precision_learning
import ranking_learning
from datetime import datetime, timezone

VERSION = 'decision-audit-v1'
RULE_VERSION = 'intraday-trend-follow-v7'
REPORT_LIMIT = 2500
REPORT_BUSY_LIMIT = 500
REPORT_ROW_BATCH = 500
REPORT_CACHE_SECONDS = 300
HARVEST_HORIZONS = (1, 5, 15, 30, 60, 240)
HARVEST_HORIZON_BATCH = 64
PROSPECTIVE_INDEX = 'bob_audit_prospective_cursor'
PROSPECTIVE_INDEX_PREDICATE = """payload->'reviewVariants'->>'version'='signal-review-v1'
    AND payload->>'origin'='background'
    AND payload->>'direction' IN ('LONG','SHORT')"""

# Last *attempted* research query on this process only. No database read,
# account/SQL contents, credentials, result caching or synthetic market data.
_PROSPECTIVE_QUERY_LOCK = threading.Lock()
_PROSPECTIVE_QUERY_LAST = None
_PROSPECTIVE_QUERY_STATES = frozenset(('completed', 'query-timeout'))
_PROSPECTIVE_FALLBACK_STATES = frozenset(('not-needed', 'completed-partial', 'query-timeout'))


def prospective_query_probe():
    """Safe aggregate-only diagnostic for the last completed query attempt."""
    with _PROSPECTIVE_QUERY_LOCK:
        item = dict(_PROSPECTIVE_QUERY_LAST) if _PROSPECTIVE_QUERY_LAST else None
    return item if item else {
        'status': 'not-observed', 'readOnly': True, 'realOrders': False,
        'causeVerified': False, 'scope': 'process-local-last-research-query-attempt',
        'note': 'No prospective research query attempt observed in this process.',
    }


def _remember_prospective_query(full_state, full_ms, fallback_state, fallback_ms):
    """Store fixed enums/finite timings, never an exception or SQL text."""
    global _PROSPECTIVE_QUERY_LAST
    if (full_state not in _PROSPECTIVE_QUERY_STATES
            or fallback_state not in _PROSPECTIVE_FALLBACK_STATES
            or type(full_ms) is not int or not 0 <= full_ms <= 86400000
            or (fallback_ms is not None and
                (type(fallback_ms) is not int or not 0 <= fallback_ms <= 86400000))
            or (fallback_state == 'not-needed') != (fallback_ms is None)
            or (full_state == 'completed') != (fallback_state == 'not-needed')):
        raise ValueError('Invalid bounded prospective query telemetry')
    payload = {
        'status': 'observed', 'readOnly': True, 'realOrders': False,
        'observedAt': datetime.now(timezone.utc).isoformat(),
        'fullWindow': '30-days', 'fullState': full_state,
        'fullDurationMs': full_ms,
        'fallbackWindow': '24-hours', 'fallbackState': fallback_state,
        'fallbackDurationMs': fallback_ms,
        'fullWindowQueryCompleted': full_state == 'completed',
        'causeVerified': False,
        'scope': 'process-local-last-research-query-attempt',
        'note': 'QueryCanceled can include statement timeout or cancellation. '
                'A successful fallback is not full-window research validation; '
                'the sampled state alone does not prove database root cause.',
    }
    with _PROSPECTIVE_QUERY_LOCK:
        _PROSPECTIVE_QUERY_LAST = payload



def milliseconds(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if math.isfinite(value) else None
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp()*1000 if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None

def rejection_code(exc):
    """Safe fixed-category diagnostics: never return payload text or secrets."""
    if isinstance(exc, json.JSONDecodeError):
        return 'invalid-json'
    known = {
        'Prüfprotokoll zu groß oder ungültig': 'payload-invalid-or-large',
        'Ungültige Richtung': 'direction-invalid',
        'Entscheidungs-Kerzenzeit fehlt oder liegt in der Zukunft': 'bar-time-invalid',
        'Zu viele Produkte': 'product-count-invalid',
        'Ungültige Protokollquelle': 'origin-invalid',
        'Ungültige Produktdaten im Prüfprotokoll': 'product-shape-invalid',
        'Ungültige Prüfhinweise': 'reasons-invalid',
        'Screenshot-Quellenzuordnung fehlt': 'screenshot-origin-missing',
        'Ungültiger Screenshot-Listenstand': 'screenshot-generation-invalid',
        'Ungültiger zukünftiger Screenshot-Listenstand': 'screenshot-generation-time-invalid',
        'Produktliste ungültig': 'simulation-products-invalid',
        'Produktnachweise zu groß': 'simulation-evidence-large',
        'Prüfprotokoll muss ein Objekt sein': 'payload-shape-invalid',
        'Ungültige Payload-Größe': 'payload-size-invalid',
    }
    return known.get(str(exc), 'other-validation-error')


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0

def normalize(payload, now=None):
    now = time.time()*1000 if now is None else now
    if not isinstance(payload, dict) or len(json.dumps(payload, allow_nan=False)) > 60000:
        raise ValueError('Prüfprotokoll zu groß oder ungültig')
    direction = payload.get('direction')
    if direction not in ('LONG', 'SHORT', 'NEUTRAL'):
        raise ValueError('Ungültige Richtung')
    bar = milliseconds(payload.get('barAt'))
    if bar is None or bar > now:
        raise ValueError('Entscheidungs-Kerzenzeit fehlt oder liegt in der Zukunft')
    # Only explicitly whitelisted evidence; never account credentials or raw images.
    result = {k: payload.get(k) for k in ('learningPolicy','baseDirection','direction','shadowDirection','trendContext','intraday','entryQuality','minuteEntry','earlyImpulse','barAt','price','priceAt','reason','score','indicators','products','selection','gateReasons','plan')}
    warning=payload.get('earlyWarning')
    if (isinstance(warning,dict) and warning.get('version')=='early-warning-v2'
        and warning.get('comparisonOnly') is True and warning.get('affectsApproval') is False
        and warning.get('state') in ('active','watch','waiting','unavailable','withdrawn','expired','paused')
        and warning.get('direction') in ('LONG','SHORT','NEUTRAL')):
        from bob_diagnostics import project, EARLY_WARNING
        result['earlyWarning']=project(warning,EARLY_WARNING)
    else:result['earlyWarning']=None
    result['decisionContext']=decision_evidence.freeze(payload.get('decisionContext'))
    plan = result.get('plan')
    if (isinstance(plan,dict) and plan.get('kind') in ('candidate','active-monitor')
        and plan.get('direction') in ('LONG','SHORT') and plan.get('unit')=='USD/oz'
        and all(positive(plan.get(k)) for k in ('entry','stop','target'))):
        result['plan'] = {k:plan.get(k) for k in ('kind','direction','entry','stop','target','unit','at','isin')}
        result['plan']['note'] = 'Gold-Referenzplan; keine Order und kein bestätigter Euro-Produktkurs'
    else:result['plan']=None
    result.update(version=VERSION, ruleVersion=payload['ruleVersion'] if payload.get('ruleVersion') in (RULE_VERSION, 'intraday-responsive-v6', 'intraday-responsive-v5', 'intraday-consistent-v4', 'intraday-fast-v3', 'intraday-1h-15m-5m-v2', 'intraday-1h-15m-5m-v1') else 'signal-5m-two-closes-v1', build=os.environ.get('RENDER_GIT_COMMIT','local'), origin=payload.get('origin','browser'), recordedAt=now)
    if result['origin'] not in ('browser','background'):
        raise ValueError('Ungültige Protokollquelle')
    if result.get('shadowDirection') not in ('LONG','SHORT','NEUTRAL'):
        result['shadowDirection'] = None
    intraday=result.get('intraday')
    if not isinstance(intraday,dict) or intraday.get('version')!='intraday-v1' or intraday.get('direction') not in ('LONG','SHORT','NEUTRAL'):result['intraday']=None
    if not isinstance(result.get('products'), list): result['products'] = []
    if len(result['products']) > 12: raise ValueError('Zu viele Produkte')
    # Reject malformed nested evidence before persistence: a single null or
    # list here otherwise breaks every report that reads the stored record.
    if any(not isinstance(p, dict) or
           (p.get('isin') is not None and not isinstance(p['isin'], str)) or
           isinstance(p.get('researchAt'), (list, dict)) or
           (p.get('reasons') is not None and not isinstance(p['reasons'], list))
           for p in result['products']):
        raise ValueError('Ungültige Produktdaten im Prüfprotokoll')
    if result.get('gateReasons') is not None and not isinstance(result['gateReasons'], list):
        raise ValueError('Ungültige Prüfhinweise')
    at = milliseconds(result.get('priceAt'))
    minute=result.get('minuteEntry')
    if not isinstance(minute,dict) or minute.get('version')!='minute-entry-v1' or minute.get('direction') not in ('LONG','SHORT','NEUTRAL'):result['minuteEntry']=None
    early=result.get('earlyImpulse')
    if (not isinstance(early,dict) or early.get('version')!='early-impulse-v1'
        or early.get('direction') not in ('LONG','SHORT','NEUTRAL')
        or type(early.get('available')) is not bool
        or early.get('comparisonOnly') is not True
        or early.get('affectsApproval') is not False):
        result['earlyImpulse']=None
    else:
        result['earlyImpulse']={k:early.get(k) for k in ('version','direction','available','comparisonOnly','affectsApproval','extensionRisk','barAt')}
        result['earlyImpulse']['reason']=str(early.get('reason') or '')[:350]
    entry=result.get('entryQuality')
    if not isinstance(entry,dict) or entry.get('version')!='entry-quality-v1' or entry.get('direction') not in ('LONG','SHORT','NEUTRAL'):result['entryQuality']=None
    result['startEvidenceStatus'] = ('missing-price' if not positive(result.get('price')) else
        'missing-time' if at is None else 'future-time' if at>now else
        'stale-time' if now-at>180000 else 'valid')
    result['marketEvaluable'] = result['startEvidenceStatus']=='valid'
    result['learningPolicy']=result.get('learningPolicy') if isinstance(result.get('learningPolicy'),str) and len(result['learningPolicy'])<150 else None
    if result.get('baseDirection') not in ('LONG','SHORT','NEUTRAL'):result['baseDirection']=None
    result['reviewVariants'] = signal_review.capture(result)
    result['optimization'] = optimization_review.capture(result)
    result['marketOptimization'] = market_optimization.capture(result)
    result['entryExperiment'] = entry_experiment.capture(result)
    # Each decision revision is frozen once. Refreshes with unchanged evidence are idempotent.
    identity={k:result[k] for k in ('learningPolicy','version','ruleVersion','origin','direction','shadowDirection','intraday','barAt','reason','products','selection','gateReasons','plan')}
    if identity.get('plan'):identity['plan']={k:v for k,v in identity['plan'].items() if k!='at'}
    # A failed first capture must not occupy the key of a later valid capture.
    # Both immutable observations remain available, with their own capture time.
    identity['captureEvidenceVersion']='start-evidence-v2'
    identity['marketEvaluable']=result['marketEvaluable']
    identity['reviewVersion']=signal_review.VERSION
    identity['optimizationVersion']=optimization_review.VERSION
    identity['marketOptimizationVersion']=market_optimization.VERSION
    identity['entryExperimentVersion']=entry_experiment.VERSION
    identity['earlyWarningEvidence']=(lambda q:{k:q.get(k) for k in ('version','state','direction','signalBarAt')} if q else None)(result.get('earlyWarning'))
    identity['earlyImpulseEvidence']=(lambda q:{'version':q['version'],'direction':q['direction'],'barAt':q['barAt']} if q else None)(result.get('earlyImpulse'))
    identity['minuteEntryVersion']=(result.get('minuteEntry') or {}).get('version')
    identity['entryQualityVersion']=(result.get('entryQuality') or {}).get('version')
    if result['decisionContext'] is not None:identity['decisionContext']=result['decisionContext']
    key=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return key,result

def init(conn):
    import evidence_repair
    evidence_repair.init(conn)
    metric_quality.init(conn)
    product_precision.init(conn)
    precision_learning.init(conn)
    ranking_learning.init(conn)
    rule_learning.init(conn)
    intraday_comparison.init(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_decision_audit (
        id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_audit_recorded ON bob_decision_audit(recorded_at)')
    conn.execute("CREATE INDEX IF NOT EXISTS bob_audit_evaluable_cursor ON bob_decision_audit(recorded_at,id) WHERE payload->>'marketEvaluable'='true' AND jsonb_typeof(payload->'recordedAt')='number'")
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_decision_outcomes (decision_id TEXT REFERENCES bob_decision_audit(id) ON DELETE CASCADE, horizon INTEGER NOT NULL, truth JSONB NOT NULL, PRIMARY KEY(decision_id,horizon))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_decision_harvest_cursor (
        horizon INTEGER PRIMARY KEY, recorded_at TIMESTAMPTZ, decision_id TEXT)''')
    conn.execute('ALTER TABLE bob_decision_harvest_cursor ADD COLUMN IF NOT EXISTS attempted_at TIMESTAMPTZ')
    conn.execute('''INSERT INTO bob_decision_harvest_cursor(horizon)
        SELECT unnest(%s::integer[]) ON CONFLICT(horizon) DO NOTHING''',(list(HARVEST_HORIZONS),))
    stop_target_audit.init(conn)
    paper_simulation.init(conn)
    import zukunft_capture
    zukunft_capture.init(conn)
    import manual_paper_watch
    manual_paper_watch.init(conn)

def write(conn,payload):
    key,record=normalize(payload)
    inserted=conn.execute('INSERT INTO bob_decision_audit(id,payload) VALUES(%s,%s::jsonb) ON CONFLICT(id) DO NOTHING RETURNING id',(key,json.dumps(record,allow_nan=False))).fetchone()
    if inserted:stop_target_audit.register(conn,key,record)
    # Research evidence has no automatic age-based expiry.
    return {'ok':True,'id':key,'version':VERSION}

def outcome(record, truth, horizon):
    """Forward quote only, with a bounded timing tolerance; no fabricated outcome."""
    if not record.get('marketEvaluable') or not truth or not positive(truth.get('price')): return None
    target=record['recordedAt']+horizon*60000
    at=milliseconds(truth.get('at'))
    if at is None or not target <= at <= target+60000:return None
    change=(truth['price']/record['price']-1)*100
    def score(direction):
        return change if direction=='LONG' else -change if direction=='SHORT' else None
    return {'horizon':horizon,'changePct':change,'directionalPct':score(record['direction']),
            'intradayPct':score((record.get('intraday') or {}).get('direction')) if (record.get('intraday') or {}).get('available') else None,'shadowPct':score(record.get('shadowDirection')),'at':truth['at']}

def missing_reason(record, horizon, now, unavailable=False):
    if unavailable:return 'signalUnavailable'
    if not record.get('marketEvaluable'):return 'invalidStart'
    if now < record['recordedAt']+horizon*60000:return 'pending'
    return 'missingFollowup'


def summarize(rows, now=None):
    now = time.time()*1000 if now is None else now
    legacy_count=sum(r.get('ruleVersion')!=RULE_VERSION for r,_ in rows)
    rows=[(r,t) for r,t in rows if r.get('ruleVersion')==RULE_VERSION]
    metrics={str(h):{'evaluated':0,'favorable':0,'unfavorable':0,'flat':0,'neutral':0,'missing':0,'directionalSumPct':0} for h in (15,60,240)}
    intraday_metrics={h:dict(m) for h,m in metrics.items()}
    for m in [*metrics.values(),*intraday_metrics.values()]:
        m['missingReasons']={k:0 for k in ('signalUnavailable','invalidStart','pending','missingFollowup')}
    seen=set();pairs=[];issues={};latest=[r for r,_ in rows[:30]]
    for record,truths in sorted(rows,key=lambda row:(not row[0].get('marketEvaluable',False),row[0].get('origin')!='background')):
        for reason in record.get('gateReasons') or []:
            text=str(reason)[:250];issues[text]=issues.get(text,0)+1
        # A changed product list or multiple devices must not multiply market observations.
        observation=record.get('barAt')
        if observation in seen:continue
        seen.add(observation)
        for h,truth in zip((15,60,240),truths):
            m=metrics[str(h)];result=outcome(record,truth,h)
            im=intraday_metrics[str(h)]
            iv=result.get('intradayPct') if result else None
            unavailable=not record.get('intraday') or not record['intraday'].get('available')
            if unavailable or result is None:
                im['missing']+=1
                im['missingReasons'][missing_reason(record,h,now,unavailable)]+=1
            elif iv is None:im['neutral']+=1
            else:
                im['evaluated']+=1;im['directionalSumPct']+=iv;im['favorable' if iv>0 else 'unfavorable' if iv<0 else 'flat']+=1
            if result is None:
                m['missing']+=1
                m['missingReasons'][missing_reason(record,h,now)]+=1
                continue
            value=result['directionalPct']
            # Compare both policies on the same timeline; ABWARTEN contributes zero exposure.
            if h==60 and record.get('origin')=='background' and record.get('shadowDirection') in ('LONG','SHORT','NEUTRAL'):
                pairs.append((record['recordedAt'],value if value is not None else 0,result['shadowPct'] if result['shadowPct'] is not None else 0))
            if value is None:m['neutral']+=1;continue
            m['evaluated']+=1;m['directionalSumPct']+=value
            m['favorable' if value>0 else 'unfavorable' if value<0 else 'flat']+=1
    pairs.sort();spaced=[]
    for pair in pairs:
        if not spaced or pair[0]-spaced[-1][0]>=3600000:spaced.append(pair)
    split=len(spaced)//2;train=spaced[:split];holdout=spaced[split:]
    improvement=lambda values:sum(x[2]-x[1] for x in values)/len(values) if values else None
    train_delta=improvement(train);test_delta=improvement(holdout)
    ready=len(train)>=100 and len(holdout)>=100
    better=ready and train_delta>0 and test_delta>0
    return {'ruleVersion':RULE_VERSION,'legacyCount':legacy_count,'intraday':intraday_metrics,'metrics':metrics,'latest':latest,'issues':sorted(issues.items(),key=lambda x:-x[1])[:8],
        'learning':{'mode':'Schattenvergleich: aktive Bestätigung gegen 3 Schlusskerzen','samples':len(spaced),
                    'training':len(train),'holdout':len(holdout),'ready':ready,'candidateBetter':better,
                    'trainingDeltaPct':train_delta,'holdoutDeltaPct':test_delta,
                    'status':'Verbesserungskandidat zur Prüfung vorhanden' if better else 'Vergleich ohne belegte Verbesserung' if ready else 'Sammelt unabhängige Vergleiche; noch keine Regeländerung',
                    'automaticRuleChange':False},'version':VERSION,'retentionDays':30}

def early_impulse_review(rows):
    """Frozen out-of-sample LONG/SHORT study. All returns are *spot direction only*."""
    from zoneinfo import ZoneInfo
    validation_start=datetime(2026,10,19,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000
    def empty_side():
        return {'evaluated':0,'favorable':0,'unfavorable':0,'flat':0,'beforeApproval':0,
                'sumPct':0.0,'baselineSumPct':0.0,'meanDirectionalPct':None}
    def empty_phase():
        return {'evaluated':0,'long':empty_side(),'short':empty_side(),'days':0}
    sides={d:empty_side() for d in ('LONG','SHORT')}
    phases={name:empty_phase() for name in ('collection','validation')}
    series={str(h):{'evaluated':0,'favorable':0,'unfavorable':0,'flat':0,'missing':0,
                    'earlySumPct':0.0,'baselineSumPct':0.0} for h in (15,60,240)}
    result={'version':'early-impulse-v1','evaluated':0,'favorable':0,'unfavorable':0,'flat':0,
            'beforeApproval':0,'missing':0,'long':sides['LONG'],'short':sides['SHORT'],
            'phases':phases,'horizons':series,'validationFrom':'2026-10-19',
            'baselineSumPct':0.0,'earlySumPct':0.0,'incrementalPct':None,
            'unconfirmedFavorable':0,'unconfirmedUnfavorable':0,'matchedActive':0,
            'uniqueDays':0,'status':'Daten sammeln','promising':False,
            'automaticRuleChange':False}
    occupied=set();seen_days=set();phase_days={name:set() for name in phases}
    # Descriptive lead-time audit only: never retrospectively change a trade.
    timeline=sorted((r for r,_ in rows if r.get('ruleVersion')==RULE_VERSION
                     and r.get('origin')=='background'
                     and type(r.get('recordedAt')) in (int,float)),
                    key=lambda r:r['recordedAt'])
    latest_observed=timeline[-1]['recordedAt'] if timeline else 0
    early_first=[]
    for record,truths in sorted(rows,key=lambda row:row[0].get('recordedAt',0)):
        early=record.get('earlyImpulse') or {}
        if (record.get('ruleVersion')!=RULE_VERSION or record.get('origin')!='background'
            or early.get('version')!=result['version'] or early.get('available') is not True
            or early.get('direction') not in sides or not isinstance(record.get('recordedAt'),(int,float))):
            continue
        # An hourly first-observation snapshot prevents repeatedly counting a 5m signal.
        hour=int(record['recordedAt']//3600000)
        if hour in occupied: continue
        occupied.add(hour)
        d=early['direction']
        early_first.append((record['recordedAt'],d,record.get('direction')))
        phase='validation' if record['recordedAt']>=validation_start else 'collection'
        day=datetime.fromtimestamp(record['recordedAt']/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
        valid60=None
        for h,truth in zip((15,60,240),truths):
            score=outcome(record,truth,h);stats=series[str(h)]
            if score is None:
                stats['missing']+=1
                continue
            value=score['changePct'] if d=='LONG' else -score['changePct']
            baseline=score['directionalPct'] or 0.0
            category='favorable' if value>0 else 'unfavorable' if value<0 else 'flat'
            stats['evaluated']+=1;stats[category]+=1
            stats['earlySumPct']+=value;stats['baselineSumPct']+=baseline
            if h==60:valid60=(value,baseline,category)
        if valid60 is None:
            result['missing']+=1
            continue
        value,baseline,category=valid60
        result['evaluated']+=1;result[category]+=1
        for stats in (sides[d],phases[phase][d.lower()]):
            stats['evaluated']+=1;stats[category]+=1
            stats['sumPct']+=value;stats['baselineSumPct']+=baseline
        phases[phase]['evaluated']+=1
        result['baselineSumPct']+=baseline;result['earlySumPct']+=value
        seen_days.add(day);phase_days[phase].add(day)
        if record.get('direction')==d:
            result['matchedActive']+=1
        else:
            result['beforeApproval']+=1
            sides[d]['beforeApproval']+=1
            phases[phase][d.lower()]['beforeApproval']+=1
            result['unconfirmedFavorable']+=value>0
            result['unconfirmedUnfavorable']+=value<0
    result['uniqueDays']=len(seen_days)
    lead=dict(version='early-lead-v1',alreadyConfirmed=0,laterConfirmed=0,
              noConfirmationWithinHour=0,pending=0,meanLeadMinutes=None,
              medianLeadMinutes=None,matchedLeadMinutes=[],
              note='Abstand zwischen erster Frühwarnung je UTC-Stunde und einer später protokollierten '
                   'gleichgerichteten aktiven Bestätigung innerhalb 60 Minuten. Kein Echt-Entry '
                   'und kein Gewinn-/Trefferbeleg; laufende Stunden bleiben offen.')
    leads=[]
    for start,side,active in early_first:
        if active==side:
            lead['alreadyConfirmed']+=1
            continue
        subsequent=next((r for r in timeline if start<r['recordedAt']<=start+3600000
                         and r.get('direction')==side),None)
        if subsequent:
            delta=(subsequent['recordedAt']-start)/60000
            leads.append(delta);lead['laterConfirmed']+=1
        elif latest_observed<start+3600000:
            lead['pending']+=1
        else:
            lead['noConfirmationWithinHour']+=1
    if leads:
        lead['meanLeadMinutes']=round(sum(leads)/len(leads),2)
        sorted_leads=sorted(leads);i=len(leads)//2
        lead['medianLeadMinutes']=round(sorted_leads[i] if len(leads)%2
                                        else (sorted_leads[i-1]+sorted_leads[i])/2,2)
        # Aggregate metrics suffice; never expose personal input records.
        lead['matchedLeadMinutes']=[]
    result['leadTime']=lead
    for name,stats in phases.items():
        stats['days']=len(phase_days[name])
        for side in (stats['long'],stats['short']):
            if side['evaluated']:
                side['meanDirectionalPct']=side['sumPct']/side['evaluated']
    for side in sides.values():
        if side['evaluated']:
            side['meanDirectionalPct']=side['sumPct']/side['evaluated']
    if result['evaluated']:
        result['incrementalPct']=(result['earlySumPct']-result['baselineSumPct'])/result['evaluated']
    training=phases['collection'];validation=phases['validation']
    # A signal is a research candidate only after chronological unseen validation,
    # never after selecting thresholds on the same early observations.
    sufficient=(training['long']['evaluated']>=8 and training['short']['evaluated']>=8
                and validation['long']['evaluated']>=10 and validation['short']['evaluated']>=10
                and validation['days']>=5)
    if not sufficient:
        result['status']='Datensammlung / unabhängige Validierung noch nicht ausreichend'
    else:
        v=validation
        positive=(all(v[d]['favorable']>v[d]['unfavorable'] and v[d]['sumPct']>0 for d in ('long','short'))
                  and sum(v[d]['sumPct']-v[d]['baselineSumPct'] for d in ('long','short'))>0)
        result['promising']=positive
        result['status']=('ERSTE POSITIVE HINWEISE – kein Netto-Gewinnnachweis' if positive
                          else 'KEIN VORTEIL GEGENÜBER DER BESTEHENDEN REGEL BELEGT')
    result['note']=(
        'Nur erstmals je UTC-Stunde beobachtete, künftig archivierte XAU/USD-Frühimpulse; '
        'gleicher Startzeitpunkt, 15/60/240-Minuten-Folgekurse und bestehende Marktrichtung als Kontrollfall '
        '(NEUTRAL = keine Position). LONG/SHORT sowie Datensammlung vor 19.10. und spätere Validierung getrennt. '
        'Vor Freigabe = noch nicht dieselbe aktive Richtung. Die Vergleichsstrategie '
        'enthält keine KO-Schwellen, Euro-Spreads, Produktkosten, Stop-Ausführung oder Slippage. '
        'Überlappende Stunden und Kursschwankungen können Ergebnisse verzerren. '
        'Fehlende Folgekurse werden nicht ersetzt. Weder Profitabilität noch eine automatische Regeländerung '
        'wird behauptet.')
    return result


_harvest_at=0

def _store_horizon_outcomes(conn, horizon, ids):
    """Only source-timed archive observations; never replace frozen outcomes."""
    conn.execute("""INSERT INTO bob_decision_outcomes(decision_id,horizon,truth)
      SELECT a.id,%s,json_build_object(
        'at',s.quote_at,'price',s.price,'minPrice',ext.lo,'maxPrice',ext.hi)::jsonb
      FROM bob_decision_audit a
      CROSS JOIN LATERAL (SELECT to_timestamp((a.payload->>'recordedAt')::double precision/1000.0) AS at) capture
      CROSS JOIN LATERAL (SELECT quote_at,price FROM bob_spot_observations
        WHERE stream='gold-api-xau-usd-v1'
        AND quote_at>=capture.at+%s*interval '1 minute'
        AND quote_at<=capture.at+(%s+1)*interval '1 minute'
        ORDER BY quote_at LIMIT 1) s
      LEFT JOIN LATERAL (SELECT min(price) lo,max(price) hi FROM bob_spot_observations
        WHERE stream='gold-api-xau-usd-v1' AND quote_at>=capture.at AND quote_at<=s.quote_at
        AND %s IN (15,60,240)
        AND a.payload->'entryQuality'->>'version'='entry-quality-v1') ext ON TRUE
      WHERE a.id=ANY(%s::text[])
      ON CONFLICT DO NOTHING""",(horizon,horizon,horizon,horizon,ids))


def _harvest_recent(conn, horizon):
    """A separate bounded lane prevents old missing quotes delaying new outcomes."""
    rows=conn.execute("""SELECT a.id FROM bob_decision_audit a
      WHERE a.recorded_at>=now()-(%s+15)*interval '1 minute'
      AND a.payload->>'marketEvaluable'='true'
      AND jsonb_typeof(a.payload->'recordedAt')='number'
      AND to_timestamp((a.payload->>'recordedAt')::double precision/1000.0)
          + %s*interval '1 minute'<=now()
      AND (%s IN (15,60,240) OR a.payload->'marketOptimization'->>'version'='market-review-v1')
      AND NOT EXISTS(SELECT 1 FROM bob_decision_outcomes o WHERE o.decision_id=a.id AND o.horizon=%s)
      ORDER BY a.recorded_at DESC,a.id LIMIT 128""",(horizon,horizon,horizon,horizon)).fetchall()
    if rows:_store_horizon_outcomes(conn,horizon,[r[0] for r in rows])
    return len(rows)


def _harvest_horizon(conn, horizon, batch_size=None):
    """Advance one durable, bounded evidence cursor without synthesizing gaps."""
    cursor=conn.execute('''SELECT recorded_at,decision_id
        FROM bob_decision_harvest_cursor WHERE horizon=%s FOR UPDATE''',(horizon,)).fetchone()
    recorded_at,decision_id=cursor or (None,None)
    cursor_filter=''
    params=[horizon,horizon,horizon]
    if recorded_at is not None:
        cursor_filter='AND (a.recorded_at,a.id)>(%s,%s)'
        params.extend((recorded_at,decision_id))
    params.append(HARVEST_HORIZON_BATCH if batch_size is None else batch_size)
    batch=conn.execute("""SELECT a.id,a.recorded_at
      FROM bob_decision_audit a
      WHERE a.recorded_at>=now()-interval '7 days'
      AND a.payload->>'marketEvaluable'='true'
      AND jsonb_typeof(a.payload->'recordedAt')='number'
      AND to_timestamp((a.payload->>'recordedAt')::double precision/1000.0)
          + %s*interval '1 minute'<=now()
      AND (%s IN (15,60,240) OR a.payload->'marketOptimization'->>'version'='market-review-v1')
      AND NOT EXISTS (SELECT 1 FROM bob_decision_outcomes o
          WHERE o.decision_id=a.id AND o.horizon=%s)
      """+cursor_filter+"""
      ORDER BY a.recorded_at,a.id LIMIT %s""",tuple(params)).fetchall()
    if not batch:
        conn.execute('''UPDATE bob_decision_harvest_cursor
            SET recorded_at=NULL,decision_id=NULL WHERE horizon=%s''',(horizon,))
        return 0
    ids=[row[0] for row in batch]
    _store_horizon_outcomes(conn,horizon,ids)
    conn.execute('''UPDATE bob_decision_harvest_cursor
        SET recorded_at=%s,decision_id=%s WHERE horizon=%s''',
        (batch[-1][1],batch[-1][0],horizon))
    return len(batch)


def _next_harvest_horizon(conn):
    row=conn.execute('SELECT horizon FROM bob_decision_harvest_cursor ORDER BY attempted_at NULLS FIRST,horizon LIMIT 1 FOR UPDATE SKIP LOCKED').fetchone()
    if not row:return None
    conn.execute('UPDATE bob_decision_harvest_cursor SET attempted_at=clock_timestamp() WHERE horizon=%s',(row[0],))
    return row[0]


def harvest(conn):
    global _harvest_at
    now=time.time()
    if now-_harvest_at<60:return
    # One horizon per invocation: commit forward progress before another archive
    # or a slow missing-evidence scan can occupy the connection. Rotation is
    # persisted across restarts, so deployments cannot starve later horizons.
    horizon=_next_harvest_horizon(conn)
    if horizon is None:return
    import psycopg
    for stage in ('recent','archive'):
        try:
            with conn.transaction():
                if stage=='recent':_harvest_recent(conn,horizon)
                else:_harvest_horizon(conn,horizon)
        except psycopg.errors.QueryCanceled:
            # Preserve cursor and frozen evidence on timeout. Retry the archive
            # with fewer cases, in a clean savepoint; later workers still run.
            if stage=='archive':
                try:
                    with conn.transaction():_harvest_horizon(conn,horizon,batch_size=8)
                except psycopg.errors.QueryCanceled:
                    print('BOB_AUDIT_HARVEST deferred=archive horizon='+str(horizon),flush=True)
            else:print('BOB_AUDIT_HARVEST deferred=recent horizon='+str(horizon),flush=True)
    _harvest_at=now

_report_lock = threading.Lock()
_report_cache = None
_report_at = 0

def report(conn):
    # Browser startup, visibility changes and periodic refresh can overlap.
    # Coalesce identical reports; failures never refresh the cached timestamp.
    global _report_cache, _report_at
    with _report_lock:
        if _report_cache is not None and time.monotonic()-_report_at < REPORT_CACHE_SECONDS:
            return copy.deepcopy(_report_cache)
        result = _build_report(conn)
        result['generatedAt'] = int(time.time()*1000)
        _report_cache = copy.deepcopy(result)
        _report_at = time.monotonic()
        return result


def _load_report_rows(conn, limit=None):
    """Read the same newest decision IDs, then fetch large JSONB in bounded batches.

    A single 2,500-row payload + outcome query can exhaust the fixed 10s SQL
    statement budget on small Render Postgres. The recorded_at index identifies
    the exact report window; primary keys fetch immutable payloads in batches.
    No archive rows, clock, horizon, threshold or trading rule is changed.
    """
    count = REPORT_LIMIT if limit is None else limit
    ids = [row[0] for row in conn.execute(
        "SELECT id FROM bob_decision_audit ORDER BY recorded_at DESC LIMIT %s",
        (count,)).fetchall()]
    if not ids:
        return []
    payloads, by_id = {}, {}
    for offset in range(0, len(ids), REPORT_ROW_BATCH):
        batch = ids[offset:offset + REPORT_ROW_BATCH]
        for key, payload in conn.execute(
                "SELECT id,payload FROM bob_decision_audit WHERE id = ANY(%s::text[])",
                (batch,)).fetchall():
            payloads[key] = payload
        for decision_id, horizon, truth in conn.execute(
                """SELECT decision_id,horizon,truth FROM bob_decision_outcomes
                   WHERE decision_id = ANY(%s::text[]) AND horizon IN (1,5,15,30,60,240)""",
                (batch,)).fetchall():
            by_id.setdefault(decision_id, {})[horizon] = truth
    return [({**payloads[key], '_marketReviewTruths':by_id.get(key,{})}
             if payloads[key].get('marketOptimization') else payloads[key],
             *(by_id.get(key, {}).get(h) for h in (15,60,240)))
            for key in ids if key in payloads]

def _build_report(conn):
    # Reading must not run the seven-day outcome backfill.
    import psycopg
    reduced_window = False
    try:
        # Roll back a canceled statement before retrying; preserve an enclosing
        # transaction through psycopg's nested savepoint handling.
        with conn.transaction():
            rows = _load_report_rows(conn)
    except psycopg.errors.QueryCanceled:
        print('BOB_AUDIT report_window_reduced reason=query-timeout limit='+str(REPORT_BUSY_LIMIT), flush=True)
        with conn.transaction():
            rows = _load_report_rows(conn, REPORT_BUSY_LIMIT)
        reduced_window = True
    learning=rule_learning.report(conn)
    active=(learning.get('policy') or {}).get('variant','baseline')
    matches=lambda r:r.get('learningPolicy')==rule_learning.ID+':'+active or active=='baseline' and r.get('learningPolicy') is None
    scoped=[row for row in rows if matches(row[0])]
    result=summarize([(row[0],row[1:]) for row in scoped])
    current=[(r,t) for r,t in [(row[0],row[1:]) for row in scoped] if r.get('ruleVersion')==RULE_VERSION]
    chart_times=[r['recordedAt'] for r,_ in current if type(r.get('recordedAt')) in (int,float)]
    import diagram_evidence
    result['signalChartEvidence']=diagram_evidence.signal_evidence(current,outcome)
    result['signalChartScope']=dict(firstAt=min(chart_times) if chart_times else None,lastAt=max(chart_times) if chart_times else None)
    result['ruleLearning']=learning
    result['metricQuality']=metric_quality.report(conn)
    result['productPrecision']=product_precision.report(conn)
    result['precisionLearning']=precision_learning.report(conn,int(time.time()*1000))
    result['rankingLearning']=ranking_learning.report(conn)
    result['otherPolicyRecords']=len(rows)-len(scoped)
    result['signalDiagnostics']=signal_review.diagnostics(current,outcome)
    result['optimizationReview']=optimization_review.report(current,outcome)
    result['optimizationReview']['marketReview']=market_optimization.report(current,outcome)
    result['optimizationReview']['entryExperiment']=entry_experiment.report(current,outcome)
    prospective_partial = False
    # Measure actual wall-clock query duration, not the amount of historical
    # market data. Never log a row, SQL parameter, connection or exception text.
    full_started = time.monotonic()
    full_state, full_ms = "completed", None
    fallback_state, fallback_ms = "not-needed", None
    try:
        with conn.transaction():
            prospective_rows = _load_prospective_rows(conn)
    except psycopg.errors.QueryCanceled:
        full_state = "query-timeout"
        full_ms = max(0, int((time.monotonic() - full_started) * 1000))
        # Retry only the already indexed recent time slice in its own
        # transaction/savepoint. Never interpret that subset as the 30-day
        # validation archive, and never increase the global SQL timeout.
        print('BOB_AUDIT prospective_retry scope=last-day',flush=True)
        fallback_started = time.monotonic()
        try:
            with conn.transaction():
                prospective_rows = _load_prospective_rows(conn, recent=True)
            prospective_partial = True
            fallback_state = "completed-partial"
        except psycopg.errors.QueryCanceled:
            prospective_rows = None
            fallback_state = "query-timeout"
        finally:
            fallback_ms = max(0, int((time.monotonic() - fallback_started) * 1000))
    if full_ms is None:
        full_ms = max(0, int((time.monotonic() - full_started) * 1000))
    # Only categorical results and bounded durations; a completed 24h retry is
    # not proof that the 30-day research query succeeded or a market error healed.
    print('BOB_AUDIT prospective_timing scope=research'
          ' full_state=' + full_state + ' full_ms=' + str(full_ms)
          + ' fallback_state=' + fallback_state
          + ' fallback_ms=' + (str(fallback_ms) if fallback_ms is not None else 'n/a'),
          flush=True)
    if prospective_rows is None:
        result['prospectiveReview']={'available':False,'retryable':True,
            'partialHistory':True,'automaticRuleChange':False,
            'reason':'Historische Strategieauswertung auch für das begrenzte Tagesfenster wegen Datenbank-Zeitüberschreitung vorübergehend nicht verfügbar'}
        print('BOB_AUDIT prospective_unavailable reason=query-timeout',flush=True)
    else:
        review=signal_review.prospective([(r,(None,t,None)) for r,t in prospective_rows],outcome)
        review['available']=True
        review['partialHistory']=prospective_partial
        if prospective_partial:
            review['validationCoverage']='last-24-hours-only'
            review['note']='Eingeschränktes Tagesfenster nach SQL-Zeitüberschreitung: keine 30-Tage-Validierung und keine Regeländerung. '+review['note']
        result['prospectiveReview']=review
    # Existing private read-only audit result receives the same coarse,
    # monotonic timings already emitted to Render logs. No extra SQL, schema,
    # connection or timeout. A completed 24h fallback remains explicitly
    # INCOMPLETE evidence for the documented 30-day research horizon.
    result['prospectiveReview']['queryTiming']={
        'scope':'query-and-transaction-wall-time',
        'fullWindow':'30-days',
        'fullState':full_state,
        'fullDurationMs':full_ms,
        'fallbackWindow':'24-hours',
        'fallbackState':fallback_state,
        'fallbackDurationMs':fallback_ms,
        'fullWindowQueryCompleted':full_state=='completed' and not prospective_partial,
    }
    _remember_prospective_query(full_state, full_ms, fallback_state, fallback_ms)
    result['fourDayComparison']=intraday_comparison.report(conn)
    result['total']=conn.execute('SELECT count(*) FROM bob_decision_audit').fetchone()[0]
    result['reportRecords']=len(rows)
    result['reportWindowReduced']=reduced_window
    result['scope']='Aktuelle Einstiegsregel '+active+' ('+str(len(scoped))+' passende, '+str(len(rows)-len(scoped))+' andere Regelstände getrennt); aktuelle Intraday-Regel; Auswertung der letzten '+str(len(rows))+' von '+str(result['total'])+' gespeicherten Entscheidungen; frühere Regeln getrennt ('+str(result['legacyCount'])+' ältere Protokolle). Einzelne Tage bleiben vollständig abrufbar. Bis 30 Tage; Gold-Richtung ohne Handelskosten, kein Gewinnnachweis'
    if reduced_window:
        result['scope']+=' · Datenbank ausgelastet: vorübergehend verkleinertes Auswertungsfenster (höchstens '+str(REPORT_BUSY_LIMIT)+' Entscheidungen). Vollständige Tagesprotokolle bleiben abrufbar.'
    if not result['prospectiveReview']['available']:
        result['scope']+=' · '+result['prospectiveReview']['reason']+'.'
    elif prospective_partial:
        result['scope']+=' · Prospektive Zusatzforschung nur letzte 24 Stunden wegen SQL-Zeitüberschreitung; keine vollständige 30-Tage-Validierung.'
    result['earlyImpulseReview']=early_impulse_review([(row[0],row[1:]) for row in rows])
    result['minuteEntryReview']=entry_quality_review([(row[0],row[1:]) for row in rows],field='minuteEntry',version='minute-entry-v1')
    result['entryQualityReview']=entry_quality_review([(row[0],row[1:]) for row in rows])
    result['productReview']=product_review([row[0] for row in rows[:1500]])
    research=[];seen=set()
    for row in rows:
        for p in row[0].get('products',[]):
            key=(p.get('isin'),p.get('researchAt'))
            if key in seen:continue
            seen.add(key)
            conflicts=[str(x) for x in (p.get('reasons') or []) if 'widerspr' in str(x).lower()]
            research.append({'isin':p.get('isin'),'source':p.get('researchSource'),'at':p.get('researchAt'),'conflicts':conflicts})
    result['researchReview']={'observations':len(research),'conflicts':sum(bool(p['conflicts']) for p in research),'missingSourceOrTime':sum(not p['source'] or not p['at'] for p in research),'examples':[p for p in research if p['conflicts']][:10],'note':'Widersprüche sind Prüfhinweise, keine automatisch bewiesenen Recherchefehler. Abrufzeit beweist keine Aktualität der Produktwerte.'}
    return result

def _prospective_query(recent=False):
    """Return the bounded hourly research query and its safe parameters."""
    horizon = "24 hours" if recent is True else "30 days"
    eligible = PROSPECTIVE_INDEX_PREDICATE + " AND payload->>'ruleVersion'=%s"
    sql = """WITH RECURSIVE sampled(id,recorded_at) AS (
        (SELECT id,recorded_at FROM bob_decision_audit
         WHERE recorded_at >= now()-interval '""" + horizon + """'
           AND recorded_at <= now()
           AND """ + eligible + """
         ORDER BY recorded_at,id LIMIT 1)
        UNION ALL
        SELECT next_hour.id,next_hour.recorded_at
        FROM sampled previous
        CROSS JOIN LATERAL (
            SELECT id,recorded_at FROM bob_decision_audit
            WHERE recorded_at >= date_trunc('hour',previous.recorded_at) + interval '1 hour'
              AND recorded_at <= now()
              AND """ + eligible + """
            ORDER BY recorded_at,id LIMIT 1
        ) next_hour
    ) SELECT a.payload,o.truth FROM sampled s
      JOIN bob_decision_audit a ON a.id=s.id
      LEFT JOIN bob_decision_outcomes o ON o.decision_id=s.id AND o.horizon=60
      ORDER BY s.recorded_at"""
    return sql, (RULE_VERSION, RULE_VERSION)


def _load_prospective_rows(conn, recent=False):
    """Earliest qualifying background decision per hour, independent of outcomes.

    The former DISTINCT ON grouped and sorted the entire JSONB-filtered archive.
    Traverse qualifying hourly first records via the existing recorded_at index;
    skip empty hours without scanning/sorting the full history. Full validation
    retains its documented 30-day window; recovery is strictly last 24 hours.
    Explicitly cap both the seed and each recursive forward step at the
    database's current time so that a bad future-dated archive record cannot
    extend the historical review or trigger an unbounded forward walk.
    A separately provisioned filtered cursor index accelerates this query when
    present. It is deliberately not built by init(): creating an index in the
    request-serving startup transaction can block writers and make a second
    service time out while both revisions overlap during deployment. Without
    the index the existing bounded timeout and 24-hour fallback remain safe.
    No SQL timeout, retention, evidence horizon or live trading gate changes.
    """
    sql, params = _prospective_query(recent)
    return conn.execute(sql, params).fetchall()

def product_review(records, now=None):
    """Compare real bid/ask observations; never turn estimated prices into ground truth."""
    now=time.time()*1000 if now is None else now
    diagnostics={k:0 for k in ('noSelection','invalidStart','pending','missingFollowup')}
    ordered=sorted(records,key=lambda r:r['recordedAt']);results=[];seen=set();quotes={};comparisons=[]
    for r in ordered:
        for p in r.get('products',[]):
            at=milliseconds(p.get('quoteAt'))
            if at is not None and positive(p.get('bid')) and 0<=r['recordedAt']-at<=90000:
                quotes.setdefault(p.get('isin'),[]).append((at,p['bid']))
    for isin in quotes:quotes[isin]=sorted(set(quotes[isin]))
    for record in ordered:
        selected=[p for p in record.get('products',[]) if p.get('selected')]
        if not selected:
            diagnostics['noSelection']+=1
            continue
        direction=record.get('direction');returns=[]
        for product in record.get('products',[]):
            isin=product.get('isin');start=milliseconds(product.get('quoteAt'));ask=product.get('ask')
            if not positive(ask) or start is None or not 0<=record['recordedAt']-start<=90000:
                if product.get('selected'):diagnostics['invalidStart']+=1
                continue
            target=record['recordedAt']+3600000;history=quotes.get(isin,[]);index=bisect.bisect_left(history,(target,0))
            if index>=len(history) or history[index][0]>target+300000:
                if product.get('selected'):diagnostics['pending' if now<target else 'missingFollowup']+=1
                continue
            value=(history[index][1]/ask-1)*100
            if product.get('selected'):
                key=(isin,int(record['recordedAt']//3600000))
                if key not in seen:results.append({'isin':isin,'at':record['recordedAt'],'changePct':value});seen.add(key)
            reasons=product.get('reasons') or []
            if product.get('direction')==direction and (not reasons or all('Grundsätzlich geeignet' in str(x) for x in reasons)):
                returns.append((value,bool(product.get('selected'))))
        if len(returns)>=2 and any(selected for _,selected in returns) and any(not selected for _,selected in returns):
            comparisons.append(max(v for v,selected in returns if selected)>=max(v for v,_ in returns))
    return {'evaluated':len(results),'favorable':sum(r['changePct']>0 for r in results),'unfavorable':sum(r['changePct']<0 for r in results),'flat':sum(r['changePct']==0 for r in results),'latest':results[-20:],
            'observations':len(records),'diagnostics':diagnostics,
            'comparisons':len(comparisons),'selectedBest':sum(comparisons),
            'note':'Beobachteter Geldkurs nach 60 Minuten gegen damaligen Briefkurs; ohne Gebühren. Alternativen nur bei damaliger Eignung und passenden späteren Kursen. Fehlende Kurse werden nicht geschätzt; begrenzter Rückblick, kein Optimalitätsnachweis.'}

def handle(conn,action,payload):
    mode=payload.get('mode') if isinstance(payload,dict) else None
    if mode in ('manual-paper-watch-sync','manual-paper-watch-levels','manual-paper-watch'):
        import manual_paper_watch
        if action=='write' and mode=='manual-paper-watch-sync':
            return manual_paper_watch.sync(conn,payload)
        if action=='write' and mode=='manual-paper-watch-levels':
            return manual_paper_watch.set_levels(conn,payload)
        if action=='read' and mode=='manual-paper-watch':
            return manual_paper_watch.report(conn,payload)
        raise ValueError('Nicht unterstützte Beobachtungsaktion')
    if action=='write' and payload.get('mode')=='simulation-sync':return paper_simulation.sync(conn,payload)
    if action=='read' and payload.get('mode')=='simulation':return paper_simulation.report(conn,payload.get('day'))
    if action=='read' and mode=='test-repairs':
        import evidence_repair
        return evidence_repair.report(conn)
    if action=='read' and mode=='diagram-portfolios':
        import paper_portfolios
        return paper_portfolios.diagram_report(conn)
    if action=='read' and payload.get('mode')=='simulation-profiles':
        import paper_portfolios
        return paper_portfolios.report(conn,payload.get('day'))
    if action=='read' and mode=='zukunft-research':
        import zukunft_capture
        return zukunft_capture.report(conn,payload)
    if action=='write':
        # Interactive writes must not wait for seven-day outcome backfills.
        # A separate low-priority worker harvests outcomes independently.
        return write(conn,payload)
    if action=='read':
        if payload.get('day') is not None:return audit_history.report(conn,payload)
        return report(conn)
    raise ValueError('Unbekannte Protokollaktion')


def entry_quality_review(rows, field='entryQuality', version='entry-quality-v1'):
    """Paired 60m spot outcomes. No simulated fills and no automatic rule change."""
    result=dict(version=version,evaluated=0,kept=0,filtered=0,baselineWins=0,candidateWins=0,missedFavorable=0,avoidedUnfavorable=0,baselineSumPct=0.,candidateSumPct=0.,excursions=0,adverseSumPct=0.,candidateAdverseSumPct=0.)
    seen=set()
    ordered=sorted(rows,key=lambda r:(r[0].get('recordedAt',0),r[0].get('origin')!='background')) if field=='minuteEntry' else sorted(rows,key=lambda r:r[0].get('origin')!='background')
    for record,truths in ordered:
        q=record.get(field) or {}
        if q.get('version')!=version or not q.get('available') or record.get('direction') not in ('LONG','SHORT'):continue
        key=record.get('barAt')
        if key in seen:continue
        seen.add(key)
        truth=truths[1] if len(truths)>1 else None
        scored=outcome(record,truth,60)
        if not scored:continue
        value=scored['directionalPct'];keep=q.get('direction')==record['direction']
        result['evaluated']+=1;result['kept' if keep else 'filtered']+=1
        result['baselineWins']+=value>0;result['candidateWins']+=keep and value>0
        result['missedFavorable']+=not keep and value>0;result['avoidedUnfavorable']+=not keep and value<0
        result['baselineSumPct']+=value;result['candidateSumPct']+=value if keep else 0
        bound=(truth or {}).get('minPrice' if record['direction']=='LONG' else 'maxPrice')
        if positive(bound):
            adverse=max(0,(record['price']-bound)/record['price']*100 if record['direction']=='LONG' else (bound-record['price'])/record['price']*100)
            result['excursions']+=1;result['adverseSumPct']+=adverse;result['candidateAdverseSumPct']+=adverse if keep else 0
    for name,total,count in [('baselineMeanPct','baselineSumPct','evaluated'),('candidateMeanPct','candidateSumPct','evaluated'),('meanObservedAdversePct','adverseSumPct','excursions'),('candidateMeanObservedAdversePct','candidateAdverseSumPct','excursions')]:
        result[name]=result[total]/result[count] if result[count] else None
    result['note']='Gepaarter 60-Minuten-Spotvergleich, gefilterte Fälle ohne Position (0). Beobachtete Gegenbewegung nur aus gespeicherten Kursen; Datenlücken möglich. Keine Gebühren/Produktkosten enthalten, keine Produktrendite. Überlappende Fälle sind nicht unabhängig; keine automatische Regeländerung.'
    return result



