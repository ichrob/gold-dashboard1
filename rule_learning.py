"""One-shot, prospective entry-filter trial. Never fits on holdout or places orders."""
import json
import math
import random
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ID = 'entry-filter-v1-20261009'
BASE = 'intraday-trend-follow-v7'
HOUR = 3600000
DAY = 24 * HOUR
# Protocol is fixed in code before any new evidence is observed.
START = int(datetime(2026, 10, 9, 19, tzinfo=timezone.utc).timestamp()*1000)
SPLIT = START + 21*DAY
END = SPLIT + 42*DAY
LABELS = {'adx25': '5m-ADX mindestens 25', 'adx30': '5m-ADX mindestens 30'}
PROTOCOL = dict(id=ID, base=BASE, start=START, selectionEnds=SPLIT, validationEnds=END,
               horizonMinutes=60, spacingHours=2, thresholds=[25,30], minSelection=60,
               minValidation=100, minSelectionDays=10, minValidationDays=20,
               minCoverage=.95, minRetained=.4, minFiltered=.1,
               minImprovementPct=.01, bootstrapBlocksDays=2, bootstrapQuantile=.01,
               bootstrapReplicates=5000, outcome='Gold-Richtungsbewegung nach 60 Minuten, ohne Kosten')

def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_rule_learning (
      id TEXT PRIMARY KEY, state JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_rule_learning_samples (
      campaign TEXT NOT NULL, slot BIGINT NOT NULL, payload JSONB NOT NULL,
      truth JSONB, PRIMARY KEY(campaign,slot))''')
    conn.execute('INSERT INTO bob_rule_learning(id,state) VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',
                 (ID,json.dumps(dict(protocol=PROTOCOL,phase='collection',active='baseline',history=[]))))

def get(conn, lock=False):
    row=conn.execute('SELECT state FROM bob_rule_learning WHERE id=%s'+(' FOR UPDATE' if lock else ''),(ID,)).fetchone()
    return row[0] if row else dict(protocol=PROTOCOL,phase='unavailable',active='baseline',history=[])

def policy(conn, now=None):
    now=int(time.time()*1000) if now is None else now
    s=get(conn)
    compatible=s.get('protocol')==PROTOCOL and s.get('phase')!='unavailable'
    variant=s.get('active','baseline') if compatible else 'unavailable'
    effective=s.get('effectiveAt',0)
    expiry=now+120000
    if now<effective and variant!='baseline':
        variant='baseline';expiry=min(expiry,effective)
    return dict(campaign=ID,base=BASE,variant=variant,
                version=ID+':'+variant,issuedAt=now,expiresAt=expiry,phase=s['phase'])

def slot_at(now): return int(now//(2*HOUR))*(2*HOUR)

def eligible(slot):
    d=datetime.fromtimestamp(slot/1000,ZoneInfo('Europe/Zurich'))
    # Fixed scheduled observations; neutral and missing slots are retained too.
    return START<=slot<END and d.weekday()<5 and 8<=d.hour<21

def slots(a,b):
    return [s for s in range(slot_at(a),b,2*HOUR) if s>=a and eligible(s)]

def observation(market,now):
    d=market.get('baseDirection',market.get('direction'))
    adx=(market.get('context') or {}).get('adx')
    p=market.get('price');at=market.get('dataAt');bar=market.get('analysisBarAt')
    valid=bool(market.get('ruleVersion')==BASE and market.get('ready') and market.get('priceFresh')
               and finite(p) and p>0 and finite(at) and 0<=now-at<=60000
               and finite(bar) and 300000<=now-bar<=600000
               and d in ('LONG','SHORT','NEUTRAL') and (d=='NEUTRAL' or finite(adx)))
    return dict(at=now,slot=slot_at(now),valid=valid,base=BASE,direction=d,
                price=p if finite(p) else None,priceAt=at if finite(at) else None,
                adx=adx if finite(adx) else None,
                reason=market.get('decisionReason') if valid else 'Analyse, ADX oder Quellenzeit nicht vollständig bestätigt')

def sample_value(r,t):
    if not r.get('valid'):return None
    if r['direction']=='NEUTRAL':return 0.
    if not t or not finite(t.get('price')) or t['price']<=0 or not finite(t.get('at')) or not r['at']+HOUR<=t['at']<=r['at']+HOUR+60000:return None
    return (t['price']/r['price']-1)*100*(1 if r['direction']=='LONG' else -1)

def metrics(rows,a,b,variant):
    records={r['slot']:(r,t) for r,t in rows if a<=r['slot']<b}
    expected=slots(a,b); valid=0; n=kept=filtered=0;daily={};base_sum=candidate_sum=0.;worst_base=worst_candidate=0.
    threshold={'adx25':25,'adx30':30}[variant]
    for slot in expected:
        item=records.get(slot)
        if not item:continue
        r,t=item;v=sample_value(r,t)
        if v is None:continue
        valid+=1
        if r['direction']=='NEUTRAL':continue
        n+=1;keep=r['adx']>=threshold;kept+=keep;filtered+=not keep
        c=v if keep else 0.
        day=datetime.fromtimestamp(slot/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
        daily.setdefault(day,[]).append(c-v)
        base_sum+=v;candidate_sum+=c;worst_base=min(worst_base,v);worst_candidate=min(worst_candidate,c)
    ds=[sum(v)/len(v) for _,v in sorted(daily.items())]
    return dict(expected=len(expected),valid=valid,coverage=valid/len(expected) if expected else 0,
                samples=n,days=len(ds),kept=kept,filtered=filtered,
                improvementPct=(candidate_sum-base_sum)/n if n else None,
                baselineMeanPct=base_sum/n if n else None,candidateMeanPct=candidate_sum/n if n else None,
                worstBaselinePct=worst_base,worstCandidatePct=worst_candidate,daily=ds)

def sufficient(m,validation=False):
    return (m['samples']>=(100 if validation else 60) and m['days']>=(20 if validation else 10)
            and m['coverage']>=.95 and m['kept']>=.4*m['samples'] and m['filtered']>=.1*m['samples'])

def lower_bound(days):
    # Paired, circular moving blocks of two observed trading days. Fixed RNG.
    # An uncertainty estimate, not proof of independence or guaranteed future results.
    if len(days)<20:return None
    rng=random.Random(20261009);means=[];n=len(days)
    for _ in range(5000):
        sample=[]
        while len(sample)<n:
            k=rng.randrange(n);sample.extend((days[k],days[(k+1)%n]))
        means.append(sum(sample[:n])/n)
    return sorted(means)[49]

def transition(state,rows,now):
    # At most one selection and one final validation; no repeated holdout peeking.
    state=json.loads(json.dumps(state))
    if state.get('protocol')!=PROTOCOL:return state
    if state['phase']=='collection' and now>=SPLIT:
        train={k:metrics(rows,START,SPLIT-HOUR,k) for k in LABELS}
        choices=[k for k,m in train.items() if sufficient(m) and m['improvementPct']>=.01]
        candidate=max(choices,key=lambda k:(train[k]['improvementPct'],k)) if choices else None
        state.update(candidate=candidate,selection=train,selectedAt=now,
                     phase='validation' if candidate else 'rejected')
        # If the service missed the boundary, future observations start only now.
        state['validationStart']=max(SPLIT,slot_at(now)+2*HOUR)
        state['history'].append(dict(at=now,event='candidate-frozen' if candidate else 'no-qualified-candidate',candidate=candidate))
    if state['phase']=='validation' and now>=END+HOUR+60000:
        m=metrics(rows,state['validationStart'],END,state['candidate'])
        bound=lower_bound(m['daily']) if sufficient(m,True) else None
        passed=bool(bound is not None and bound>0 and m['improvementPct']>=.01
                    and m['candidateMeanPct']>0 and m['worstCandidatePct']>=m['worstBaselinePct'])
        state.update(validation=m,lowerBound99Pct=bound,phase='adopted' if passed else 'rejected',
                     active=state['candidate'] if passed else 'baseline',decidedAt=now,effectiveAt=now+120000 if passed else now)
        state['history'].append(dict(at=now,event='adopted' if passed else 'validation-failed',
                                    variant=state['active'],previous='baseline'))
    return state

def tick(conn,bundle,analyze,now=None):
    now=int(time.time()*1000) if now is None else now
    s=get(conn,True)
    if s.get('protocol')!=PROTOCOL:return
    # Lock serializes capture and the immutable phase boundary across processes.
    slot=slot_at(now)
    if s['phase'] in ('collection','validation'):
        conn.execute('''UPDATE bob_rule_learning_samples a SET truth=x.truth FROM (
          SELECT c.slot,json_build_object('price',q.price,'at',extract(epoch from q.quote_at)*1000)::jsonb truth
          FROM bob_rule_learning_samples c CROSS JOIN LATERAL (
            SELECT quote_at,price FROM bob_spot_observations WHERE stream='gold-api-xau-usd-v1'
            AND quote_at>=to_timestamp(((c.payload->>'at')::double precision+3600000)/1000)
            AND quote_at<=to_timestamp(((c.payload->>'at')::double precision+3660000)/1000)
            ORDER BY quote_at LIMIT 1) q
          WHERE c.campaign=%s AND c.truth IS NULL AND (c.payload->>'valid')::boolean=TRUE
          ) x WHERE a.campaign=%s AND a.slot=x.slot AND a.truth IS NULL''',(ID,ID))
        rows=conn.execute('SELECT payload,truth FROM bob_rule_learning_samples WHERE campaign=%s ORDER BY slot',(ID,)).fetchall()
        s=transition(s,rows,now)
        conn.execute('UPDATE bob_rule_learning SET state=%s::jsonb WHERE id=%s',(json.dumps(s),ID))
        allowed=s['phase']=='collection' and slot<SPLIT-HOUR or s['phase']=='validation' and slot>=s['validationStart']
        if allowed and eligible(slot) and 0<=now-slot<300000 and not any(r['slot']==slot for r,_ in rows):
            try:market=analyze(bundle,{'timeframe':'15m','learningPolicy':policy(conn,now)},priority=2)
            except Exception:market={}
            # First scheduled attempt is immutable, even when data is missing.
            conn.execute('INSERT INTO bob_rule_learning_samples(campaign,slot,payload) VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                         (ID,slot,json.dumps(observation(market,now))))

def report(conn):
    s=get(conn);rows=conn.execute('SELECT payload,truth FROM bob_rule_learning_samples WHERE campaign=%s ORDER BY slot',(ID,)).fetchall()
    s=dict(s,policy=policy(conn),captured=len(rows))
    s['note']='Einmaliger prospektiver Vergleich: ADX 25 oder 30. Auswahl und spätere Prüfung zeitlich getrennt; keine Anpassung an Prüfdaten. Mindestens 60/100 Richtungssignale, 10/20 Handelstage, 95 % Datenabdeckung. Gepaarter Vergleich nach 60 Minuten, 2 Stunden Abstand; 99 %-Block-Bootstrap auf Handelstagen. Mindestverbesserung 0,01 Prozentpunkte pro Signal. Nur zusätzliche Einstiegsfilter; keine automatische Order. Goldbewegung ohne Spread, Gebühren oder Produktausführung: kein Gewinnnachweis und keine Garantie. Bei Nichtbestehen bleibt die Grundregel; kein automatischer neuer Versuch mit denselben Prüfdaten.'
    return s

def rollback(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    s=get(conn,True)
    if s['phase']=='adopted':
        previous=s['active'];s.update(active='baseline',phase='rolled-back')
        s['history'].append(dict(at=now,event='manual-rollback',previous=previous,variant='baseline'))
        conn.execute('UPDATE bob_rule_learning SET state=%s::jsonb WHERE id=%s',(json.dumps(s),ID))
    return policy(conn,now)
