"""Prospective, bounded rank selection and full-list counterfactual quote returns.

Only already eligible spot products can be reordered. Never orders or a
retrospective claim that the subsequently best product was knowable at entry.
"""
import copy
import json
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import adaptive_learning as timing
import product_precision as precision
import rule_learning as statistics
import ranking_lifecycle
import ranking_regimes

ID='product-ranking-v1'
DAY=86400000
HOUR=3600000
VARIANTS=('second','third')
PROTOCOL=dict(id=ID,candidates=list(VARIANTS),maxScoreGap=5,horizonMinutes=60,
    selectionDays=21,validationDays=42,minSelection=60,minValidation=100,
    minSelectionDays=10,minValidationDays=20,minEachDirection=10,minCoverage=.95,
    minChangedFraction=.1,minImprovementPct=.05,monitorDays=7,monitorMinSamples=20,
    costsPct={'standard':.1,'stress':.3},scope='eligible-native-spot-same-currency-only',learningAdmission='live-gates-only')


def finite(v):return type(v) in (int,float) and math.isfinite(v)


def choose(candidates,variant):
    baseline=sorted(candidates,key=lambda c:(-c['score'],c['isin']))
    if not baseline:return None
    live=[c for c in baseline if not c.get('paperOnly')]
    index={'second':1,'third':2}.get(variant,0)
    if baseline[0].get('paperOnly') or len(live)<=index or live[0]['score']-live[index]['score']>5:return baseline[0]
    return live[index]


def initial(now,cycle=1):
    start=timing.next_slot(now)
    return dict(protocol=copy.deepcopy(PROTOCOL),cycle=cycle,phase='selection',active='baseline',
        start=start,selectionEnd=start+21*DAY,lastCheckedAt=now,history=[])


def init(conn):
    ranking_lifecycle.init(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_ranking_state (
        currency TEXT PRIMARY KEY,state JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_ranking_samples (
        currency TEXT NOT NULL,slot BIGINT NOT NULL,payload JSONB NOT NULL,outcome JSONB,
        PRIMARY KEY(currency,slot))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_ranking_events (
        seq BIGSERIAL PRIMARY KEY,currency TEXT NOT NULL,at BIGINT NOT NULL,payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_ranking_pending ON bob_ranking_samples(slot) WHERE outcome IS NULL')
    for currency in ('EUR','CHF'):
        conn.execute('INSERT INTO bob_ranking_state VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',
                     (currency,json.dumps(initial(int(time.time()*1000)))))


def policy(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    states=dict(conn.execute('SELECT currency,state FROM bob_ranking_state').fetchall())
    variants={ccy:s.get('active','baseline') if s.get('protocol')==PROTOCOL and
        s.get('phase')=='monitoring' and 0<=now-s.get('lastCheckedAt',0)<=180000 and now>=s.get('effectiveAt',0)
        else 'baseline' for ccy,s in states.items()}
    return dict(id=ID,issuedAt=now,expiresAt=now+120000,variants=variants,maxScoreGap=5)


def capture(conn,market,selection,quotes,spots,now,simulation_quotes=None):
    now=int(now);slot=statistics.slot_at(now)
    if not timing.eligible(slot) or not 0<=now-slot<300000:return
    choices=selection.get('researchCandidates',selection.get('choices',[]))
    active=policy(conn,now)
    for currency in ('EUR','CHF'):
        if conn.execute('SELECT 1 FROM bob_ranking_samples WHERE currency=%s AND slot=%s',(currency,slot)).fetchone():continue
        candidates=[];missing=[]
        for c in choices[:12]:
            if c.get('scope')!='XAU/USD' or c.get('indicative') or c.get('estimated'):continue
            q=quotes.get(c.get('isin')) or {};ccy=(q.get('metadata') or {}).get('currency') or q.get('currency')
            if ccy!=currency:continue
            frozen=precision.freeze(market,c,q,spots,now)
            if frozen and finite(c.get('score')):
                candidates.append(dict(isin=c['isin'],score=c['score'],quote=frozen['quote'],
                    direction=c['direction'],paperOnly=c.get('paperOnly') is True,terms=frozen['identity']))
            else:missing.append(c.get('isin'))
        candidates.sort(key=lambda c:(-c['score'],c['isin']))
        times=[c['quote'][field] for c in candidates for field in ('at','askAt')]
        if times and max(times)-min(times)>30000:missing.append('source-time-skew')
        chosen=choose(candidates,active['variants'].get(currency,'baseline'))
        row=dict(version=ID,at=now,slot=slot,currency=currency,direction=market.get('direction'),regime=ranking_regimes.classify(market),
            marketReady=market.get('ready') is True and market.get('priceFresh') is True,
            rule=market.get('ruleVersion'),signalPolicy=market.get('learningPolicy'),
            rankingVariant=active['variants'].get(currency,'baseline'),
            chosen=chosen['isin'] if chosen else None,candidates=candidates,missing=missing,
            universe='Zum Zeitpunkt freigegebene Produkte der gespeicherten Liste; kein gesamter Markt')
        conn.execute('INSERT INTO bob_ranking_samples VALUES(%s,%s,%s::jsonb,NULL) ON CONFLICT DO NOTHING',
                     (currency,slot,json.dumps(row)))
        if simulation_quotes is not None:ranking_lifecycle.capture(conn,row,market,choices,simulation_quotes,now)


def evaluate(row,observations):
    start=row['at'];end=start+HOUR;returns={};missing=list(row['missing']);exit_times=[]
    for c in row['candidates']:
        q=c['quote'];seen={};conflict=False
        for point in observations.get(c['isin'],[]):
            if not all(point.get(k)==q.get(k) for k in ('isin','currency','source')):continue
            if not start<point['at']<=end+60000 or not finite(point.get('bid')) or point['bid']<=0:continue
            if point['at'] in seen and seen[point['at']]['bid']!=point['bid']:conflict=True
            seen[point['at']]=point
        points=sorted(seen.values(),key=lambda p:p['at'])
        exit_quote=next((p for p in points if p['at']>=end),None)
        prev=start;maxgap=0;worst=0.
        for point in points:
            if exit_quote and point['at']>exit_quote['at']:break
            maxgap=max(maxgap,point['at']-prev);prev=point['at']
            worst=min(worst,(point['bid']/q['ask']-1)*100)
        if conflict or not exit_quote or maxgap>90000:
            missing.append(c['isin']);continue
        gross=(exit_quote['bid']/q['ask']-1)*100
        exit_times.append(exit_quote['at'])
        returns[c['isin']]=dict(grossPct=gross,standardPct=gross-.1,stressPct=gross-.3,
            worstObservedPct=worst,entryAsk=q['ask'],entryAt=q['askAt'],exitBid=exit_quote['bid'],exitAt=exit_quote['at'],source=q['source'])
    if exit_times and max(exit_times)-min(exit_times)>30000:missing.append('exit-time-skew')
    complete=bool(row['marketReady'] and len(row['candidates'])>=2 and not missing and len(returns)==len(row['candidates']))
    out=dict(complete=complete,returns=returns,missing=missing,actualExecution=False,
        status='complete' if complete else 'no-comparable-products' if not row['candidates'] and row['marketReady'] else 'incomplete')
    if complete:
        best=max(v['grossPct'] for v in returns.values());chosen=row['chosen']
        winners=sorted(i for i,v in returns.items() if abs(v['grossPct']-best)<1e-9)
        alternatives=[i for i in returns if i!=chosen]
        alternative=max(alternatives,key=lambda i:(returns[i]['grossPct'],i))
        out.update(bestIsins=winners,bestPct=best,chosenIsin=chosen,chosenPct=returns[chosen]['grossPct'],
            missedPct=best-returns[chosen]['grossPct'],alternativeIsin=alternative,
            alternativeAdvantagePct=returns[alternative]['grossPct']-returns[chosen]['grossPct'])
    return out


def metrics(rows,start,end,variant):
    expected=timing.slots(start,end);by_slot={r['slot']:(r,o) for r,o in rows if start<=r['slot']<end}
    valid=[];ready=0;incomplete=0;directions={'LONG':0,'SHORT':0}
    for slot in expected:
        if slot not in by_slot:continue
        r,o=by_slot[slot]
        if not r.get('marketReady'):continue
        ready+=1
        if r.get('missing') or (len(r['candidates'])>=2 and not (o or {}).get('complete')):incomplete+=1
        if not o or not o.get('complete') or r.get('direction') not in directions:continue
        live=[c for c in r['candidates'] if not c.get('paperOnly')]
        if len(live)<2:continue
        baseline=choose(live,'baseline')['isin'];candidate=choose(live,variant)['isin']
        directions[r['direction']]+=1
        valid.append((r,o,baseline,candidate))
    scenarios={};n=len(valid)
    for name,cost in PROTOCOL['costsPct'].items():
        sums={'baseline':0.,'candidate':0.};peaks=dict(sums);dd=dict(sums);worst=dict(sums);daily={}
        for r,o,b,c in valid:
            values={'baseline':o['returns'][b]['grossPct']-cost,'candidate':o['returns'][c]['grossPct']-cost}
            day=datetime.fromtimestamp(r['slot']/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
            daily.setdefault(day,[]).append(values['candidate']-values['baseline'])
            for side,i in (('baseline',b),('candidate',c)):
                # Include observed intrahour adverse moves, not just end returns.
                dd[side]=max(dd[side],peaks[side]-(sums[side]+o['returns'][i]['worstObservedPct']-cost))
                sums[side]+=values[side];peaks[side]=max(peaks[side],sums[side]);dd[side]=max(dd[side],peaks[side]-sums[side])
                worst[side]=min(worst[side],o['returns'][i]['worstObservedPct']-cost)
        scenarios[name]=dict(mean={k:v/n if n else None for k,v in sums.items()},drawdown=dd,worst=worst,
            improvementPct=(sums['candidate']-sums['baseline'])/n if n else None,
            daily=[sum(v)/len(v) for _,v in sorted(daily.items())])
    return dict(samples=n,days=len(scenarios['standard']['daily']),expected=len(expected),
        coverage=ready/len(expected) if expected else 0,incomplete=incomplete,directions=directions,
        changed=sum(b!=c for _,_,b,c in valid),scenarios=scenarios)


def sufficient(m,validation=False):
    return (m['samples']>=(100 if validation else 60) and m['days']>=(20 if validation else 10)
        and m['coverage']>=.95 and m['incomplete']==0 and min(m['directions'].values())>=10
        and m['changed']>=m['samples']*.1)


def advantage(m):
    return all(g['improvementPct'] is not None and g['improvementPct']>=.05
        and g['mean']['candidate']>0 and g['drawdown']['candidate']<=g['drawdown']['baseline']+1e-9
        and g['worst']['candidate']>=g['worst']['baseline']-1e-9 for g in m['scenarios'].values())


EARLY_PROTOCOL=dict(version='early-rank-rollback-v1',completedTradingDays=3,minSamples=12,
    minChanged=12,minSamplesPerDay=3,minCoverage=.95,minDailyDeclinePct=.1,
    minMeanDeclinePct=.2,requireWorseRisk=True)


def early_review(s,rows,now):
    # One fixed daily checkpoint, never repeated intraday significance peeking.
    local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'))
    end=int(local.replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
    if end<=s.get('earlyCheckedThrough',s['monitorStart']):return
    s['earlyCheckedThrough']=end
    slots=timing.slots(s['monitorStart'],end)
    days=sorted({datetime.fromtimestamp(t/1000,ZoneInfo('Europe/Zurich')).date().isoformat() for t in slots})
    if len(days)<3:return
    days=days[-3:]
    start=min(t for t in slots if datetime.fromtimestamp(t/1000,ZoneInfo('Europe/Zurich')).date().isoformat()==days[0])
    m=metrics(rows,start,end,s['active'])
    per_day=[]
    for day in days:
        subset=[(r,o) for r,o in rows if datetime.fromtimestamp(r['slot']/1000,ZoneInfo('Europe/Zurich')).date().isoformat()==day]
        per_day.append(metrics(subset,start,end,s['active'])['samples'])
    qualified=(m['samples']>=12 and m['changed']>=12 and m['days']==3 and min(per_day)>=3
        and m['coverage']>=.95 and m['incomplete']==0)
    decline=qualified and all(g['improvementPct']<=-.2 and all(v<=-.1 for v in g['daily'])
        and (g['drawdown']['candidate']>g['drawdown']['baseline']+1e-9 or
             g['worst']['candidate']<g['worst']['baseline']-1e-9) for g in m['scenarios'].values())
    s['earlyReview']=dict(protocol=EARLY_PROTOCOL,start=start,end=end,evidence=m,
        triggered=bool(decline),status='rollback' if decline else 'no-confirmed-decline' if qualified else 'insufficient-evidence')
    if decline:
        revert(s,now,'Frühe Rücknahme: drei abgeschlossene Vergleichstage mit Renditeverschlechterung und höherem beobachtetem Risiko')
        s['history'][-1]['earlyEvidence']=s['earlyReview']


def event(s,at,kind,**details):s['history'].append(dict(at=at,event=kind,**details))


def revert(s,now,reason,manual=False):
    s.update(active='baseline',phase='paused' if manual else 'cooldown',restartAt=timing.next_slot(now+7*DAY))
    event(s,now,'manual-pause' if manual else 'rollback',reason=reason)


def transition(state,rows,now):
    s=copy.deepcopy(state)
    if s.get('protocol')!=PROTOCOL:return s
    if s['phase']=='cooldown' and now>=s['restartAt']:
        old=s;s=initial(now,s['cycle']+1);s['history']=old['history'];event(s,now,'new-cycle')
    if s['phase']=='monitoring' and now-s['lastCheckedAt']>DAY:revert(s,now,'Überwachung unterbrochen')
    s['lastCheckedAt']=now
    if s['phase']=='selection' and now>=s['selectionEnd']:
        scored={v:metrics(rows,s['start'],s['selectionEnd']-HOUR-60000,v) for v in VARIANTS}
        choices=[v for v,m in scored.items() if sufficient(m) and advantage(m)];s['selection']=scored
        if choices:
            candidate=max(choices,key=lambda v:(scored[v]['scenarios']['stress']['improvementPct'],v))
            start=timing.next_slot(now)
            s.update(phase='validation',candidate=candidate,validationStart=start,validationEnd=start+42*DAY)
            event(s,now,'candidate-frozen',candidate=candidate)
        else:
            s.update(phase='cooldown',restartAt=timing.next_slot(now+7*DAY));event(s,now,'selection-rejected')
    if s['phase']=='validation' and now>=s['validationEnd']+HOUR+60000:
        m=metrics(rows,s['validationStart'],s['validationEnd'],s['candidate']);s['validation']=m
        bounds={k:statistics.lower_bound(g['daily']) for k,g in m['scenarios'].items()} if sufficient(m,True) else {}
        passed=bool(bounds and min(bounds.values())>0 and advantage(m));s['lowerBounds99']=bounds
        if passed:
            start=timing.next_slot(now+120000)
            s.update(phase='monitoring',active=s['candidate'],effectiveAt=now+120000,monitorStart=start,monitorEnd=start+7*DAY)
            event(s,now,'adopted',variant=s['active'],evidence=m,lowerBounds99=bounds)
        else:
            s.update(phase='cooldown',active='baseline',restartAt=timing.next_slot(now+7*DAY));event(s,now,'validation-rejected',evidence=m)
    if s['phase']=='monitoring':early_review(s,rows,now)
    if s['phase']=='monitoring' and now>=s['monitorEnd']+HOUR+60000:
        m=metrics(rows,s['monitorStart'],s['monitorEnd'],s['active']);s['monitoring']=m
        if m['samples']<20 or m['days']<5 or m['coverage']<.95 or m['incomplete'] or not advantage(m):
            revert(s,now,'Neue Rendite-, Risiko- oder Abdeckungsprüfung nicht bestanden')
        else:
            start=timing.next_slot(now);s.update(monitorStart=start,monitorEnd=start+7*DAY);event(s,now,'monitor-passed',evidence=m)
    return s


def harvest(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    pending=conn.execute('''SELECT currency,slot,payload FROM bob_ranking_samples
        WHERE outcome IS NULL AND (payload->>'at')::bigint<%s ORDER BY slot LIMIT 12 FOR UPDATE SKIP LOCKED''',(now-HOUR-60000,)).fetchall()
    for currency,slot,row in pending:
        observations={}
        for c in row['candidates']:
            q=c['quote']
            observations[c['isin']]=[r[0] for r in conn.execute('''SELECT payload FROM bob_precision_quotes
                WHERE isin=%s AND source=%s AND currency=%s AND at>%s AND at<=%s ORDER BY at''',
                (c['isin'],q['source'],currency,row['at'],row['at']+HOUR+60000)).fetchall()]
        out=evaluate(row,observations)
        conn.execute('UPDATE bob_ranking_samples SET outcome=%s::jsonb WHERE currency=%s AND slot=%s AND outcome IS NULL',
                     (json.dumps(out),currency,slot))


def tick(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    for currency,state in conn.execute('SELECT currency,state FROM bob_ranking_state ORDER BY currency FOR UPDATE').fetchall():
        rows=conn.execute('SELECT payload,outcome FROM bob_ranking_samples WHERE currency=%s AND slot>=%s ORDER BY slot',
                          (currency,state['start'])).fetchall()
        n=len(state['history']);s=transition(state,rows,now)
        for e in s['history'][n:]:conn.execute('INSERT INTO bob_ranking_events(currency,at,payload) VALUES(%s,%s,%s::jsonb)',(currency,e['at'],json.dumps(e)))
        s['history']=s['history'][-50:]
        conn.execute('UPDATE bob_ranking_state SET state=%s::jsonb WHERE currency=%s',(json.dumps(s),currency))
    # Never discard an ongoing campaign's selection/validation evidence.
    # Preserve study cases and outcomes for reproducible historical evaluation.


def control(conn,enabled,now):
    if type(enabled) is not bool:raise ValueError('enabled muss true oder false sein')
    for currency,state in conn.execute('SELECT currency,state FROM bob_ranking_state ORDER BY currency FOR UPDATE').fetchall():
        if enabled:
            s=initial(now,state['cycle']+1);event(s,now,'manual-restart')
        else:
            s=copy.deepcopy(state);revert(s,now,'Vom Nutzer pausiert',True)
        e=s['history'][-1]
        conn.execute('INSERT INTO bob_ranking_events(currency,at,payload) VALUES(%s,%s,%s::jsonb)',(currency,now,json.dumps(e)))
        conn.execute('UPDATE bob_ranking_state SET state=%s::jsonb WHERE currency=%s',(json.dumps(s),currency))
    return policy(conn,now)


def report(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    states=dict(conn.execute('SELECT currency,state FROM bob_ranking_state').fetchall())
    for ccy,s in states.items():
        start=s.get('monitorStart') if s['phase']=='monitoring' else s.get('validationStart') if s['phase']=='validation' else s['start']
        end=min(now-HOUR-60000,s.get('monitorEnd',now) if s['phase']=='monitoring' else s.get('validationEnd',now) if s['phase']=='validation' else s['selectionEnd'])
        campaign=conn.execute('SELECT payload,outcome FROM bob_ranking_samples WHERE currency=%s AND slot>=%s AND slot<%s ORDER BY slot',(ccy,start,end)).fetchall()
        variants=[s['candidate']] if s.get('candidate') else VARIANTS
        s['progress']={v:metrics(campaign,start,end,v) for v in variants}
        s['lastMeasurementAt']=max((p['at'] for p,_ in campaign),default=None)
    rows=conn.execute('SELECT payload,outcome FROM bob_ranking_samples ORDER BY slot DESC,currency LIMIT 100').fetchall()
    lifecycle=ranking_lifecycle.report(conn)
    return dict(protocol=PROTOCOL,earlyProtocol=EARLY_PROTOCOL,policy=policy(conn,now),states=states,limit=100,
        lifecycle=lifecycle,regimes=ranking_regimes.summarize(rows,lifecycle['comparisons']),
        comparisons=[dict(at=r['at'],slot=r['slot'],regime=r.get('regime'),currency=r['currency'],direction=r['direction'],chosen=r['chosen'],
            candidates=r['candidates'],outcome=o,missing=r['missing']) for r,o in rows],
        note='Beobachteter 60-Minuten-Vergleich aller damals zulässigen Produkte der gespeicherten Liste. Einstieg Brief, Ausstieg Geld; gleiche Währung und Quellenzeiten bis 30 Sekunden auseinander. Nur regulär freigegebene Produkte liefern Lernbelege; reine Simulationsfreigaben werden separat verglichen. 0,1/0,3 % zusätzliche Kosten sind Szenarien. Keine Ausführung oder belegte Nettorendite; ein späterer Gewinner war vorher nicht bekannt.')
