"""Bounded prospective adaptation of additional entry filters, never orders.

Fixed candidates, disjoint selection/validation/monitoring evidence and an
append-only audit. Costs are Gold-signal assumptions, not broker execution proof.
"""
import copy
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import rule_learning as legacy

ID='entry-filter-v2-guarded'
BASE=legacy.BASE
HOUR=legacy.HOUR
DAY=legacy.DAY
LABELS=legacy.LABELS
PROTOCOL=dict(id=ID,base=BASE,candidates=['adx25','adx30'],selectionDays=21,validationDays=42,
    cooldownDays=7,horizonMinutes=60,spacingHours=2,minSelection=60,minValidation=100,
    minSelectionDays=10,minValidationDays=20,minCoverage=.95,minRetained=.4,minFiltered=.1,
    minEachDirection=10,minImprovementPct=.01,costPct={'standard':.04,'stress':.12},
    monitorDays=7,monitorMinSamples=20,monitorMinDays=5,leaseMs=180000,
    scope='additional-entry-filter-only',productNetValidated=False)


def next_slot(now):return legacy.slot_at(now)+2*HOUR


def eligible(slot):
    d=datetime.fromtimestamp(slot/1000,ZoneInfo('Europe/Zurich'))
    return d.weekday()<5 and 8<=d.hour<21


def slots(a,b):
    return [s for s in range(legacy.slot_at(a),int(b),2*HOUR) if a<=s and eligible(s)]


def initial(now,cycle=1,history=None):
    start=next_slot(now)
    return dict(protocol=copy.deepcopy(PROTOCOL),cycle=cycle,campaign=ID+':'+str(start),
        phase='collection',active='baseline',startedAt=start,selectionEnds=start+21*DAY,
        validationEnds=start+63*DAY,lastCheckedAt=now,history=history or [])


def init(conn):
    legacy.init(conn)  # Old campaigns remain intact for historical inspection.
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_adaptive_events (
        seq BIGSERIAL PRIMARY KEY,campaign TEXT NOT NULL,at BIGINT NOT NULL,payload JSONB NOT NULL)''')
    conn.execute('INSERT INTO bob_rule_learning VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',
                 (ID,json.dumps(initial(int(time.time()*1000)))))


def get(conn,lock=False):
    row=conn.execute('SELECT state FROM bob_rule_learning WHERE id=%s'+(' FOR UPDATE' if lock else ''),(ID,)).fetchone()
    return row[0] if row else dict(protocol=None,phase='unavailable',active='baseline',history=[])


def policy(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    s=get(conn)
    compatible=s.get('protocol')==PROTOCOL
    variant=s.get('active','baseline') if compatible else 'unavailable'
    if compatible and (not legacy.finite(s.get('lastCheckedAt')) or not 0<=now-s['lastCheckedAt']<=PROTOCOL['leaseMs']):
        variant='baseline' # An unmonitored learned filter never persists indefinitely.
    if now<s.get('effectiveAt',0):variant='baseline'
    return dict(campaign=ID,base=BASE,variant=variant,version=ID+':'+variant,
                issuedAt=now,expiresAt=now+120000,phase=s['phase'])


def metrics(rows,a,b,variant):
    records={r['slot']:(r,t) for r,t in rows if a<=r['slot']<b}
    expected=slots(a,b);valid=0;values=[];directions={'LONG':0,'SHORT':0}
    for slot in expected:
        if slot not in records:continue
        r,t=records[slot];v=legacy.sample_value(r,t)
        if v is None:continue
        valid+=1
        if r['direction']=='NEUTRAL':continue
        if not legacy.finite(r.get('adx')):continue
        directions[r['direction']]+=1
        values.append((r,v,r['adx']>= {'adx25':25,'adx30':30}[variant]))
    n=len(values);kept=sum(keep for _,_,keep in values)
    scenarios={}
    for name,cost in PROTOCOL['costPct'].items():
        sums={'baseline':0.,'candidate':0.};peaks=dict(sums);dd=dict(sums);worst=dict(sums);daily={}
        for r,v,keep in values:
            base=v-cost;cand=base if keep else 0.
            day=datetime.fromtimestamp(r['slot']/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
            daily.setdefault(day,[]).append(cand-base)
            for side,value in (('baseline',base),('candidate',cand)):
                sums[side]+=value;peaks[side]=max(peaks[side],sums[side]);dd[side]=max(dd[side],peaks[side]-sums[side]);worst[side]=min(worst[side],value)
        scenarios[name]=dict(baselineMeanPct=sums['baseline']/n if n else None,
            candidateMeanPct=sums['candidate']/n if n else None,
            improvementPct=(sums['candidate']-sums['baseline'])/n if n else None,
            drawdown=dd,worst=worst,daily=[sum(v)/len(v) for _,v in sorted(daily.items())],costPct=cost)
    standard=scenarios['standard']
    return dict(samples=n,days=len(standard['daily']),expected=len(expected),valid=valid,
        coverage=valid/len(expected) if expected else 0,kept=kept,filtered=n-kept,directions=directions,
        scenarios=scenarios,**{k:standard[k] for k in ('improvementPct','baselineMeanPct','candidateMeanPct')})


def sufficient(m,validation=False):
    return (m['samples'] >= (100 if validation else 60) and m['days'] >= (20 if validation else 10)
        and m['coverage']>=.95 and m['kept']>=.4*m['samples'] and m['filtered']>=.1*m['samples']
        and min(m['directions'].values())>=10)


def advantage(m):
    return all(g['improvementPct'] is not None and g['improvementPct']>=.01 and g['candidateMeanPct']>0
        and g['drawdown']['candidate']<=g['drawdown']['baseline']+1e-9
        and g['worst']['candidate']>=g['worst']['baseline'] for g in m['scenarios'].values())


def event(s,now,kind,reason,**details):
    s.setdefault('history',[]).append(dict(at=now,event=kind,reason=reason,cycle=s['cycle'],**details))


def revert(s,now,reason,manual=False):
    previous=s['active'];s.update(active='baseline',phase='paused' if manual else 'cooldown',
        nextCycleAt=next_slot(now+7*DAY),effectiveAt=now)
    event(s,now,'manual-rollback' if manual else 'automatic-rollback',reason,previous=previous,variant='baseline',evidence=s.get('monitoring'))


def transition(state,rows,now):
    s=copy.deepcopy(state)
    if s.get('protocol')!=PROTOCOL:return s
    if s['phase']=='cooldown' and now>=s['nextCycleAt']:
        old=s;s=initial(now,old['cycle']+1,old['history'])
        event(s,now,'new-cycle','Neuer Test nur mit künftigen, ungenutzten Beobachtungen.')
    if s['phase']=='monitoring' and now-s.get('lastCheckedAt',0)>DAY:
        revert(s,now,'Überwachung länger als einen Tag unterbrochen; Grundregel wiederhergestellt.')
    s['lastCheckedAt']=now
    if s['phase']=='collection' and now>=s['selectionEnds']:
        scored={k:metrics(rows,s['startedAt'],s['selectionEnds']-HOUR,k) for k in LABELS}
        candidates=[k for k,m in scored.items() if sufficient(m) and advantage(m)]
        s['selection']=scored
        if candidates:
            candidate=max(candidates,key=lambda k:(scored[k]['scenarios']['stress']['improvementPct'],k))
            s.update(candidate=candidate,phase='validation',validationStart=max(s['selectionEnds'],next_slot(now)))
            # Missed boundaries never turn already observed outcomes into holdout.
            s['validationEnds']=s['validationStart']+42*DAY
            event(s,now,'candidate-frozen','Auswahl abgeschlossen; spätere Prüfung beginnt.',candidate=candidate,evidence=scored[candidate])
        else:
            s.update(phase='cooldown',nextCycleAt=next_slot(now+7*DAY))
            event(s,now,'selection-rejected','Stichprobe, Kosten oder Risiko erfüllen die Kriterien nicht.')
    if s['phase']=='validation' and now>=s['validationEnds']+HOUR+60000:
        m=metrics(rows,s['validationStart'],s['validationEnds'],s['candidate']);s['validation']=m
        bounds={k:legacy.lower_bound(g['daily']) for k,g in m['scenarios'].items()} if sufficient(m,True) else {}
        passed=bool(bounds and min(bounds.values())>0 and advantage(m))
        s['lowerBound99Pct']=min(bounds.values()) if bounds else None
        if passed:
            s.update(phase='monitoring',active=s['candidate'],effectiveAt=now+120000,
                     monitorStart=next_slot(now+120000),monitorEnd=next_slot(now+120000)+7*DAY)
            event(s,now,'adopted','Spätere Prüfung einschließlich Kostenstress und Rückgangsvergleich bestanden.',variant=s['active'],previous='baseline',evidence=m,lowerBounds=bounds)
        else:
            s.update(phase='cooldown',active='baseline',nextCycleAt=next_slot(now+7*DAY))
            event(s,now,'validation-rejected','Spätere Prüfung nicht bestanden; Grundregel bleibt aktiv.',evidence=m,lowerBounds=bounds)
    if s['phase']=='monitoring' and now>=s['monitorEnd']+HOUR+60000:
        m=metrics(rows,s['monitorStart'],s['monitorEnd'],s['active']);s['monitoring']=m
        enough=m['samples']>=20 and m['days']>=5 and m['coverage']>=.95
        bad=not enough or any(g['improvementPct'] is None or g['improvementPct']<0 or g['candidateMeanPct']<=0
            or g['drawdown']['candidate']>g['drawdown']['baseline']+1e-9 for g in m['scenarios'].values())
        if bad:revert(s,now,'Neue Kontrollperiode: Vorteil, Kostenrobustheit oder Datenabdeckung nicht bestätigt.')
        else:
            event(s,now,'monitor-passed','Neue unabhängige Kontrollperiode bestanden.',variant=s['active'],evidence=m)
            s.update(monitorStart=next_slot(now),monitorEnd=next_slot(now)+7*DAY)
    return s


def persist(conn,s,previous_events):
    for e in s['history'][previous_events:]:
        conn.execute('INSERT INTO bob_adaptive_events(campaign,at,payload) VALUES(%s,%s,%s::jsonb)',(s['campaign'],e['at'],json.dumps(e)))
    s['history']=s['history'][-100:]
    conn.execute('UPDATE bob_rule_learning SET state=%s::jsonb WHERE id=%s',(json.dumps(s),ID))


def tick(conn,bundle,analyze,now=None):
    now=int(time.time()*1000) if now is None else now
    s=get(conn,True)
    if s.get('protocol')!=PROTOCOL:return
    campaign=s['campaign']
    conn.execute('''UPDATE bob_rule_learning_samples a SET truth=x.truth FROM (
      SELECT c.slot,json_build_object('price',q.price,'at',extract(epoch from q.quote_at)*1000)::jsonb truth
      FROM bob_rule_learning_samples c CROSS JOIN LATERAL (
        SELECT quote_at,price FROM bob_spot_observations WHERE stream='gold-api-xau-usd-v1'
        AND quote_at>=to_timestamp(((c.payload->>'at')::double precision+3600000)/1000)
        AND quote_at<=to_timestamp(((c.payload->>'at')::double precision+3660000)/1000)
        ORDER BY quote_at LIMIT 1) q
      WHERE c.campaign=%s AND c.truth IS NULL AND (c.payload->>'valid')::boolean=TRUE
      ) x WHERE a.campaign=%s AND a.slot=x.slot AND a.truth IS NULL''',(campaign,campaign))
    rows=conn.execute('SELECT payload,truth FROM bob_rule_learning_samples WHERE campaign=%s ORDER BY slot',(campaign,)).fetchall()
    before=len(s['history']);s=transition(s,rows,now);persist(conn,s,before)
    if s['campaign']!=campaign:rows=[]
    slot=legacy.slot_at(now)
    allowed=(s['phase']=='collection' and s['startedAt']<=slot<s['selectionEnds']-HOUR or
        s['phase']=='validation' and s['validationStart']<=slot<s['validationEnds'] or
        s['phase']=='monitoring' and s['monitorStart']<=slot<s['monitorEnd'])
    if allowed and eligible(slot) and 0<=now-slot<300000 and not any(r['slot']==slot for r,_ in rows):
        # Always capture the original baseline, even after a filter is adopted.
        p=policy(conn,now);p.update(variant='baseline',version=ID+':baseline')
        try:market=analyze(bundle,{'timeframe':'15m','learningPolicy':p},priority=2)
        except Exception:market={}
        payload=legacy.observation(market,now)
        conn.execute('INSERT INTO bob_rule_learning_samples(campaign,slot,payload) VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
            (s['campaign'],slot,json.dumps(payload)))


def report(conn):
    s=get(conn);out=copy.deepcopy(s)
    row=conn.execute('SELECT count(*) FROM bob_rule_learning_samples WHERE campaign=%s',(s.get('campaign',''),)).fetchone()
    out.update(captured=row[0],policy=policy(conn))
    out['protocol']=dict(PROTOCOL,selectionEnds=s.get('selectionEnds'),validationEnds=s.get('validationEnds'))
    out['note']='Automatische Anpassung nur zusätzlicher ADX-Einstiegsfilter (25/30). Auswahl: mindestens 60 Signale / 10 Tage; spätere Prüfung: 100 / 20 Tage; beide Richtungen, 95 % Abdeckung. Gold-Signalvergleich mit angenommenen Gesamtkosten 0,04 % und 0,12 %, kein Nachweis von Produkt-Nettogewinnen. Übernahme nur bei positivem Vorteil in beiden Szenarien, positiver 99%-Block-Schätzgrenze und keinem größeren Rückgang. Danach getrennte 7-Tage-Kontrollen; bei Verschlechterung oder fehlender Evidenz Grundregel. Neue Versuche nach 7 Tagen ausschließlich mit neuen Daten. KO, Stopps, Verlustgrenzen und Orders werden nicht geändert. Manuelle Rücknahme pausiert weitere Anpassungen.'
    return out


def rollback(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    s=get(conn,True)
    if s.get('protocol')==PROTOCOL:
        before=len(s['history']);revert(s,now,'Vom Nutzer pausiert; keine automatische Wiederaufnahme.',manual=True);persist(conn,s,before)
    return policy(conn,now)
