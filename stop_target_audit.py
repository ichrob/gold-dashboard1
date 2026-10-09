"""Frozen four-hour Gold-reference plan tests on observed source quotes only."""
import hashlib
import json
import math
import time
from datetime import datetime, timedelta, timezone

VERSION = 'stop-target-observed-v1'
WINDOW_SECONDS = 4 * 3600
MAX_GAP_SECONDS = 90

def valid_plan(plan):
    if not isinstance(plan, dict) or plan.get('unit') != 'USD/oz':
        return False
    if plan.get('kind') not in ('candidate', 'active-monitor'):
        return False
    values = [plan.get(k) for k in ('entry', 'stop', 'target')]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and v > 0 for v in values):
        return False
    entry, stop, target = values
    return (stop < entry < target if plan.get('direction') == 'LONG' else
            target < entry < stop if plan.get('direction') == 'SHORT' else False)

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_stop_target_tests (
        id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES bob_decision_audit(id) ON DELETE CASCADE,
        started_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
        plan JSONB NOT NULL, result JSONB NOT NULL,
        checked_at TIMESTAMPTZ, complete BOOLEAN NOT NULL DEFAULT FALSE)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_stop_target_started ON bob_stop_target_tests(started_at)')
    conn.execute('''CREATE INDEX IF NOT EXISTS bob_stop_target_pending
        ON bob_stop_target_tests(checked_at NULLS FIRST) WHERE complete=FALSE''')

def register(conn, decision_id, record):
    plan = record.get('plan')
    # Already-existing historical decisions are not retroactively registered.
    # Active-monitor snapshots with a profit stop beyond entry require a separate
    # lifecycle evaluation; they must not be mislabeled as a new initial plan.
    if not valid_plan(plan) or not record.get('marketEvaluable'):
        return
    now = record['recordedAt']
    source_at = record.get('priceAt')
    try:
        if isinstance(source_at,str):
            source_at = datetime.fromisoformat(source_at.replace('Z','+00:00')).timestamp()*1000
        if isinstance(source_at,bool) or not isinstance(source_at,(int,float)) or not 0 <= now-source_at <= 60000:
            return
    except (ValueError,TypeError):
        return
    identity = dict(version=VERSION, rule=record.get('ruleVersion'), bar=record.get('barAt'),
                    plan={k: plan.get(k) for k in ('kind','direction','entry','stop','target','unit','isin')})
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    start = datetime.fromtimestamp(now / 1000, timezone.utc)
    result = dict(version=VERSION, lifecycleEnabled=plan.get('kind')=='candidate', status='pending', note=NOTE, samples=0,
                  modelOnly=True, productReturnKnown=False)
    conn.execute('''INSERT INTO bob_stop_target_tests(id,decision_id,started_at,ends_at,plan,result)
        VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT(id) DO NOTHING''',
        (key, decision_id, start, start + timedelta(seconds=WINDOW_SECONDS),
         json.dumps(plan), json.dumps(result)))

NOTE = ('Fester ursprünglicher Gold-Referenzplan, maximal vier Stunden ab Speicherung. '
        'Nur beobachtete Spotkurse; Bewegungen zwischen Messungen sind unbekannt. '
        'Keine Order, keine Stop-Ausführung, keine Produktnettorendite. '
        'Nachgezogene Stops und verlängerte Ziele werden damit nicht als Trade-Lebenszyklus bewertet.')

def evaluate(plan, start, end, points, now):
    result = dict(version=VERSION, status='pending', note=NOTE, samples=0,
                  modelOnly=True, productReturnKnown=False, maxGapSeconds=0,
                  firstObserved=None, observedAt=None, observedPrice=None)
    if not valid_plan(plan):
        return {**result, 'status': 'invalid-plan', 'complete': True}
    previous = start
    elapsed_end = min(now, end)
    # Prices at one identical source timestamp must agree; never choose a
    # favorable interpretation of conflicting records.
    seen = {}
    for at, price in sorted(points):
        if not start <= at <= elapsed_end:
            continue
        if (not isinstance(price, (int,float)) or isinstance(price,bool)
                or not math.isfinite(price) or price <= 0):
            continue
        if at in seen and seen[at] != price:
            return {**result, 'status': 'inconclusive', 'complete': True,
                    'reason': 'Widersprüchliche Kurse zur gleichen Quellenzeit'}
        seen[at] = price
    for at, price in sorted(seen.items()):
        result['samples'] += 1
        result['maxGapSeconds'] = max(result['maxGapSeconds'], (at-previous).total_seconds())
        previous = at
        long = plan['direction'] == 'LONG'
        hit = ('stop' if (price <= plan['stop'] if long else price >= plan['stop']) else
               'target' if (price >= plan['target'] if long else price <= plan['target']) else None)
        if hit:
            result.update(firstObserved=hit, observedAt=at.isoformat(), observedPrice=price,
                          status='inconclusive' if result['maxGapSeconds'] > MAX_GAP_SECONDS else 'observed-'+hit,
                          complete=True)
            if result['status'] == 'inconclusive':
                result['reason'] = 'Kurslücke vor dem ersten beobachteten Treffer; Reihenfolge nicht belegt'
            return result
    result['maxGapSeconds'] = max(result['maxGapSeconds'], max(0,(elapsed_end-previous).total_seconds()))
    complete = now >= end
    result['complete'] = complete
    if complete:
        result['status'] = 'inconclusive' if result['maxGapSeconds'] > MAX_GAP_SECONDS or not seen else 'no-observed-hit'
        if result['status'] == 'inconclusive':
            result['reason'] = 'Fehlende Kursabdeckung im Testzeitraum'
    return result

_last_check = 0
def harvest(conn):
    global _last_check
    if time.monotonic() - _last_check < 30:
        return
    # Small batches outside report reads; skip plans another worker is handling.
    rows = conn.execute('''SELECT id,started_at,ends_at,plan,result FROM bob_stop_target_tests
        WHERE complete=FALSE ORDER BY checked_at NULLS FIRST LIMIT 20 FOR UPDATE SKIP LOCKED''').fetchall()
    now = datetime.now(timezone.utc)
    for key, start, end, plan, saved in rows:
        points = conn.execute('''SELECT quote_at,price FROM bob_spot_observations
            WHERE stream='gold-api-xau-usd-v1' AND quote_at >= %s AND quote_at <= %s
            ORDER BY quote_at''',(start,min(end,now))).fetchall()
        result = evaluate(plan,start,end,points,now)
        if saved.get('lifecycleEnabled'):
            result['lifecycleEnabled']=True
            result['lifecycle']={k:evaluate_lifecycle(plan,start,end,points,now,trailing=k=='trailing') for k in ('fixed','trailing')}
            result['complete']=all(x['complete'] for x in result['lifecycle'].values())
        conn.execute('''UPDATE bob_stop_target_tests SET result=%s::jsonb,checked_at=%s,complete=%s
            WHERE id=%s''',(json.dumps(result),now,result['complete'],key))
    _last_check = time.monotonic()

def report(conn, start, end):
    counts = conn.execute('''SELECT result->>'status',count(*) FROM bob_stop_target_tests
        WHERE started_at >= %s AND started_at < %s GROUP BY 1''',(start,end)).fetchall()
    rows = conn.execute('''SELECT id,decision_id,started_at,ends_at,plan,result,checked_at
        FROM bob_stop_target_tests WHERE started_at >= %s AND started_at < %s
        ORDER BY started_at,id LIMIT 100''',(start,end)).fetchall()
    return dict(version=VERSION, counts=dict(counts), total=sum(n for _,n in counts),
                detailsLimit=100, detailsTruncated=sum(n for _,n in counts)>100,
                maxGapSeconds=MAX_GAP_SECONDS, windowSeconds=WINDOW_SECONDS, note=NOTE,
                tests=[dict(id=k, decisionId=d, startedAt=s.isoformat(), endsAt=e.isoformat(),
                            plan=p,result=r,checkedAt=c.isoformat() if c else None)
                       for k,d,s,e,p,r,c in rows])


def evaluate_lifecycle(plan, start, end, points, now, trailing=False):
    """Frozen shadow model: stop trails by initial risk after >=1R favorable movement.
    Test old stop before updating it at the current quote. No inferred fills.
    """
    p=dict(plan);risk=abs(p.get('entry',0)-p.get('stop',0))
    result=dict(version='plan-lifecycle-v1',status='pending',complete=False,
        samples=0,maxGapSeconds=0,maxAdverseR=0.,maxFavorableR=0.,stopUpdates=0,
        finalStop=p.get('stop'),directionalR=None,modelOnly=True,
        policy='1R-Abstand ab +1R, Stop nie lockern' if trailing else 'Ursprünglicher Stop und Ziel')
    if not valid_plan(p):return {**result,'status':'invalid-plan','complete':True}
    sign=1 if p['direction']=='LONG' else -1
    elapsed=min(now,end);previous=start;seen={};peak=0;last=None
    for at,price in sorted(points):
        if not start<=at<=elapsed or not isinstance(price,(int,float)) or isinstance(price,bool) or not math.isfinite(price) or price<=0:continue
        if at in seen and seen[at]!=price:return {**result,'status':'inconclusive','complete':True,'reason':'Widersprüchliche Quellenkurse'}
        seen[at]=price
    for at,price in sorted(seen.items()):
        result['samples']+=1;result['maxGapSeconds']=max(result['maxGapSeconds'],(at-previous).total_seconds());previous=at;last=price
        move=sign*(price-p['entry'])/risk;peak=max(peak,move)
        result['maxAdverseR']=max(result['maxAdverseR'],-move)
        result['maxFavorableR']=max(result['maxFavorableR'],move)
        hit='stop' if sign*(price-p['stop'])<=0 else 'target' if sign*(price-p['target'])>=0 else None
        if hit:
            result.update(status='observed-'+hit,complete=True,observedAt=at.isoformat(),observedPrice=price,firstObserved=hit,directionalR=move)
            break
        if trailing and peak>=1:
            candidate=p['entry']+sign*(peak-1)*risk
            if sign*(candidate-p['stop'])>0:
                p['stop']=candidate;result['stopUpdates']+=1;result['finalStop']=candidate
    if not result['complete']:
        result['maxGapSeconds']=max(result['maxGapSeconds'],max(0,(elapsed-previous).total_seconds()))
        if now>=end:result.update(status='no-observed-hit',complete=True,directionalR=sign*(last-p['entry'])/risk if last is not None else None)
    if result['maxGapSeconds']>MAX_GAP_SECONDS:
        result.update(status='inconclusive',directionalR=None,reason='Kurslücke über 90 Sekunden; Verlauf nicht vollständig belegt')
    return result
