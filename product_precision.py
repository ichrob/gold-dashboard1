"""Frozen product plans, ranking cohorts and native quote evidence; no orders.

Missing observations are retained as missing. Returns are bid/ask observations,
not fills; standard/stress costs are explicit assumptions, never actual profit.
"""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
import product_trade_history as history
import stop_target_audit

VERSION='product-precision-v1'
HOUR=3600000


def key(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def native(q,now):
    if not isinstance(q,dict) or q.get('productVerified') is not True:return None
    if q.get('currencyConversion'):
        n=q.get('paperNativeQuote')
        if not isinstance(n,dict):return None
        q=dict(n,productVerified=True,found=True,fresh=True)
    if (q.get('currency') not in ('EUR','CHF') or not q.get('source') or q.get('delayed')
        or q.get('sourceFailure') or q.get('sourceDisabled') or q.get('priceKind') in
        ('issuer-chart','calculated','calculated-turbo') or not q.get('found') or not q.get('fresh')
        or not history.pos(q.get('bid')) or not history.pos(q.get('ask')) or q['ask']<q['bid']):return None
    times=[history.clock(q.get(k)) for k in ('bidAt','askAt')]
    if any(t is None or not 0<=now-t.timestamp()*1000<=90000 for t in times):return None
    if abs((times[0]-times[1]).total_seconds())>30:return None
    return dict(isin=q['isin'],currency=q['currency'],bid=q['bid'],ask=q['ask'],
                at=int(times[0].timestamp()*1000),askAt=int(times[1].timestamp()*1000),source=q['source'])


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_precision_cohorts (
        id TEXT PRIMARY KEY,at BIGINT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_precision_quotes (
        isin TEXT NOT NULL, source TEXT NOT NULL,currency TEXT NOT NULL,at BIGINT NOT NULL,
        payload JSONB NOT NULL,PRIMARY KEY(isin,source,currency,at))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_precision_cases (
        id TEXT PRIMARY KEY,cohort TEXT NOT NULL,isin TEXT NOT NULL,started_at BIGINT NOT NULL,
        ends_at BIGINT NOT NULL,payload JSONB NOT NULL,result JSONB,
        checked_at BIGINT,complete BOOLEAN NOT NULL DEFAULT FALSE)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_precision_pending ON bob_precision_cases(checked_at NULLS FIRST) WHERE complete=FALSE')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_precision_started ON bob_precision_cases(started_at)')


def observe(conn,quote,spots,now):
    q=native(quote,now)
    if not q:return
    at=history.clock((spots or {}).get('spot_price_as_of'))
    fx=(spots or {}).get('usd_chf_meta' if q['currency']=='CHF' else 'usd_eur_meta') or {}
    ft=history.clock(fx.get('fetchedAt'))
    if (at and ft and spots.get('is_genuine_xauusd_spot') is True and not spots.get('spot_error')
        and history.pos(spots.get('xaus')) and history.pos(fx.get('rate')) and not fx.get('error')
        and all(0<=now-t.timestamp()*1000<=90000 and abs(q['at']-t.timestamp()*1000)<=30000 for t in (at,ft))):
        q.update(gold=spots['xaus'],goldAt=int(at.timestamp()*1000),fx=fx['rate'],fxAt=int(ft.timestamp()*1000))
    conn.execute('''INSERT INTO bob_precision_quotes VALUES(%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT DO NOTHING''',(q['isin'],q['source'],q['currency'],q['at'],json.dumps(q)))


def freeze(market,choice,quote,spots,now):
    q=native(quote,now);plan=market.get('plan')
    if not q or not market.get('ready') or not market.get('priceFresh') or not stop_target_audit.valid_plan(plan):return None
    if choice.get('indicative') or choice.get('estimated') or choice.get('direction')!=plan['direction']:return None
    import product_list_study
    model=product_list_study.anchor(quote,spots,datetime.fromtimestamp(now/1000,timezone.utc))
    if not model or model['source']!=q['source']:return None
    p=model['product'];sign=1 if p['direction']=='LONG' else -1
    def projection(gold):
        value=p['bid']+sign*p['ratio']*(gold-p['goldReference'])*p['fxReference']
        return value if value>0 else None
    if not all(projection(plan[k]) for k in ('stop','target')):return None
    identity={k:p[k] for k in ('isin','currency','direction','ratio','strike','ko')}
    return dict(version=VERSION,rule=market.get('ruleVersion'),policy=market.get('learningPolicy'),
        at=now,quote=q,model=p,identity=identity,plan=dict(plan),score=choice.get('score'),
        predictedStop=projection(plan['stop']),predictedTarget=projection(plan['target']),
        gearing=p['goldReference']*p['fxReference']*p['ratio']/q['ask'],
        koDistancePct=abs(p['goldReference']-p['ko'])/p['goldReference']*100,
        grossOnly=True,actualExecution=False)


def capture(conn,market,selection,quotes,spots,now):
    # Nonoverlapping two-hour cohorts; first observed evidence is immutable.
    slot=int(now//(2*HOUR))*2*HOUR
    if now-slot>300000:return
    cohort=key([VERSION,slot,market.get('ruleVersion'),market.get('learningPolicy'),market.get('direction')])
    if not selection.get('choices'):return
    claimed=conn.execute('INSERT INTO bob_precision_cohorts VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING id',
                         (cohort,int(now))).fetchone()
    if not claimed:return
    for rank,choice in enumerate((selection.get('choices') or [])[:12],1):
        row=freeze(market,choice,quotes.get(choice.get('isin')),spots,now)
        if not row:continue
        row['rank']=rank
        row['expectedCount']=len(selection['choices'])
        conn.execute('''INSERT INTO bob_precision_cases(id,cohort,isin,started_at,ends_at,payload)
            VALUES(%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
            (key([cohort,choice['isin']]),cohort,choice['isin'],now,now+4*HOUR,json.dumps(row)))


def evaluate(case,points,now):
    start=case['at'];end=start+4*HOUR;q=case['quote'];p=case['model'];plan=case['plan']
    rows=sorted([r for r in points if start<r['at']<=min(now,end) and
        all(r.get(k)==q.get(k) for k in ('isin','source','currency'))],key=lambda r:r['at'])
    by_time={};conflict=False
    for r in rows:
        if r['at'] in by_time and by_time[r['at']]!=r:conflict=True
        by_time[r['at']]=r
    rows=list(by_time.values())
    out=dict(samples=len(rows),complete=now>=end,status='pending',actualExecution=False,
             netProfitKnown=False,quoteReturnPct=None,standardCostPct=.1,stressCostPct=.3)
    if conflict:return dict(out,status='conflict',complete=True)
    later=next((r for r in rows if start+HOUR<=r['at']<=start+HOUR+60000),None)
    if later:
        gross=(later['bid']/q['ask']-1)*100
        out.update(quoteReturnPct=gross,standardScenarioPct=gross-.1,stressScenarioPct=gross-.3)
        # Realized finite-window elasticity is a diagnostic, not issuer gearing.
        if history.pos(later.get('gold')) and history.pos(later.get('fx')):
            move=(later['gold']/p['goldReference']-1)
            if abs(move)>=.0005:
                bid_return=(later['bid']/q['bid']-1)
                out['realizedElasticity']=bid_return/move
                out['elasticityNote']='Beobachtete Geldkursbewegung / Goldbewegung; FX und Aufgeld wirken mit, kein identischer Emittentenhebel.'
    elif now>=start+HOUR+60000:out['returnMissing']=True
    goldpoints=[(datetime.fromtimestamp(r['goldAt']/1000,timezone.utc),r['gold']) for r in rows if history.pos(r.get('gold'))]
    dt=lambda t:datetime.fromtimestamp(t/1000,timezone.utc)
    observed=stop_target_audit.evaluate(plan,dt(start),dt(end),goldpoints,dt(now))
    out['goldPlan']=observed
    prev=start;maxgap=0;hit=None
    for r in rows:
        maxgap=max(maxgap,r['at']-prev);prev=r['at']
        kind='stop' if r['bid']<=case['predictedStop'] else 'target' if r['bid']>=case['predictedTarget'] else None
        if kind:
            hit=dict(kind=kind,at=r['at'],bid=r['bid'],conclusive=maxgap<=90000);break
    out['productPlan']=dict(firstObserved=hit,maxGapMs=maxgap)
    if observed.get('observedAt'):
        at=history.clock(observed['observedAt']).timestamp()*1000
        match=next((r for r in rows if r.get('goldAt')==at),None)
        if match and observed['status'].startswith('observed-'):
            field='predictedStop' if observed['firstObserved']=='stop' else 'predictedTarget'
            out['levelError']=dict(kind=observed['firstObserved'],estimated=case[field],
                observed=match['bid'],error=case[field]-match['bid'],currency=q['currency'],
                note='Produktkurs beim ersten beobachteten Gold-Treffer; Sprünge sind Teil der Abweichung.')
    if out['complete']:
        out['status']='observed' if later and observed['status']!='inconclusive' else 'inconclusive'
    return out


def harvest(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    cases=conn.execute('''SELECT id,payload FROM bob_precision_cases WHERE complete=FALSE
        ORDER BY checked_at NULLS FIRST LIMIT 12 FOR UPDATE SKIP LOCKED''').fetchall()
    for identity,case in cases:
        q=case['quote']
        rows=conn.execute('''SELECT payload FROM bob_precision_quotes WHERE isin=%s AND source=%s
            AND currency=%s AND at>%s AND at<=%s ORDER BY at''',
            (q['isin'],q['source'],q['currency'],case['at'],min(now,case['at']+4*HOUR))).fetchall()
        result=evaluate(case,[r[0] for r in rows],now)
        conn.execute('UPDATE bob_precision_cases SET result=%s::jsonb,checked_at=%s,complete=%s WHERE id=%s',
            (json.dumps(result),now,result['complete'],identity))
    # Research evidence has no automatic age-based expiry.
    # Research evidence has no automatic age-based expiry.
    # Research evidence has no automatic age-based expiry.


def report(conn):
    rows=conn.execute('''SELECT cohort,payload,result FROM bob_precision_cases
        ORDER BY started_at DESC LIMIT 2000''').fetchall()
    cohorts={};levels={'stop':[],'target':[]};returns=[];pending=missing=0
    for cohort,case,result in rows:
        result=result or {};value=result.get('quoteReturnPct')
        if value is not None:returns.append(value)
        elif result.get('returnMissing'):missing+=1
        else:pending+=1
        e=result.get('levelError')
        if e:levels[e['kind']].append(e)
        cohorts.setdefault((cohort,case['quote']['currency']),[]).append((case,result))
    ranking=[]
    for group in cohorts.values():
        if len(group)<2 or any(r.get('quoteReturnPct') is None or c.get('expectedCount')!=len(group) for c,r in group):continue
        group.sort(key=lambda x:x[0]['rank']);top=group[0][1]['quoteReturnPct'];others=[r['quoteReturnPct'] for _,r in group[1:]]
        ranking.append(dict(topPct=top,alternativesMeanPct=sum(others)/len(others),advantagePct=top-sum(others)/len(others)))
    return dict(cases=len(rows),pending=pending,missing=missing,returns=len(returns),
        meanQuoteReturnPct=sum(returns)/len(returns) if returns else None,
        ranking=dict(cohorts=len(ranking),meanAdvantagePct=sum(r['advantagePct'] for r in ranking)/len(ranking) if ranking else None),
        levels={k:{ccy:dict(count=len(v),mae=sum(abs(e['error']) for e in v)/len(v),bias=sum(e['error'] for e in v)/len(v))
            for ccy in ('EUR','CHF') if (v:=[e for e in values if e['currency']==ccy])} for k,values in levels.items()},
        latest=[dict(isin=c['quote']['isin'],at=c['at'],gearing=c['gearing'],result=r) for _,c,r in rows[:12]],
        detailsLimit=2000,truncated=len(rows)==2000,
        note='Eingefrorene Pläne und Rangfolgen, spätere native Geldkurse gegen Einstiegs-Brief. 0,1/0,3 % Zusatzkosten sind Szenarien. Keine Ausführung, keine bestätigte Nettorendite; Rangfolge und Risikolimits werden nicht aus unvollständigen Ergebnissen geändert.')
