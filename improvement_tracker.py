"""Prospective MBO evidence dashboard. Read-only research, never modifies trading policy."""
import json
import hashlib
import improvement_assessment
import math
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import trade_risk_review
import trade_learning_review

ZONE = ZoneInfo('Europe/Zurich')
START = int(datetime(2026, 10, 19, tzinfo=ZONE).timestamp()*1000)
VERSION = 'better-v1-20261019'
PROTOCOL = dict(version=VERSION, startAt=START, timezone='Europe/Zurich',
    captureSeconds=30, hours='Montag–Freitag 08:00–22:00 Schweizer Zeit',
    candidate='Aktuelles freigegebenes Signal zusätzlich nur bei 5m-ADX ≥ 25',
    horizonMinutes=60, spacingHours=2, selectionDays=10, validationDays=20,
    minSelection=60, minValidation=100, minCoverage=.95, minRealTrades=20,
    realTradeDays=10, costPct=[.04,.12], automaticRuleChange=False,
    note='Fortschritt misst Nachweisumfang, nicht Gewinnwahrscheinlichkeit. Spot-Testkosten sind Annahmen, keine Produktkosten.')


def finite(x):
    return type(x) in (int,float) and math.isfinite(x)


def clock(now):
    return datetime.fromtimestamp(now/1000,ZONE)


def eligible(now):
    d=clock(now)
    return now>=START and d.weekday()<5 and 8<=d.hour<22


def day_index(now):
    day=clock(now).date(); first=clock(START).date(); n=0
    while first<day:
        n+=first.weekday()<5;first+=timedelta(days=1)
    return n


def expected_slots(now):
    """Completed scheduled slots, including outages; never infer perfect coverage."""
    day=clock(START).date(); end=clock(now).date(); result=0
    while day<=end:
        if day.weekday()<5:
            a=int(datetime(day.year,day.month,day.day,8,tzinfo=ZONE).timestamp()*1000)
            b=int(datetime(day.year,day.month,day.day,22,tzinfo=ZONE).timestamp()*1000)
            result+=max(0,(min(now//30000*30000,b)-a)//30000)
        day+=timedelta(days=1)
    return result


def init(conn):
    import improvement_operations
    improvement_operations.init(conn)
    import exit_quality
    exit_quality.init(conn)
    conn.execute('CREATE TABLE IF NOT EXISTS bob_improvement_protocol (id TEXT PRIMARY KEY, payload JSONB NOT NULL)')
    conn.execute('INSERT INTO bob_improvement_protocol VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',(VERSION,json.dumps(PROTOCOL)))
    import entry_path_study
    conn.execute('INSERT INTO bob_improvement_protocol VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',(entry_path_study.VERSION,json.dumps(entry_path_study.PROTOCOL)))
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_improvement_reviews (id TEXT PRIMARY KEY, campaign TEXT NOT NULL, at BIGINT NOT NULL, payload JSONB NOT NULL)''')
    conn.execute('CREATE TABLE IF NOT EXISTS bob_improvement_state (campaign TEXT PRIMARY KEY, validation_at BIGINT)')
    conn.execute('INSERT INTO bob_improvement_state VALUES(%s,NULL) ON CONFLICT DO NOTHING',(VERSION,))
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_improvement_observations (
      campaign TEXT NOT NULL, slot BIGINT NOT NULL, day TEXT NOT NULL, valid BOOLEAN NOT NULL,
      payload JSONB NOT NULL, PRIMARY KEY(campaign,slot))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_improvement_trials (
      campaign TEXT NOT NULL, slot BIGINT NOT NULL, day TEXT NOT NULL, phase TEXT NOT NULL,
      payload JSONB NOT NULL, outcome JSONB, PRIMARY KEY(campaign,slot))''')


def safe_evidence(value,depth=0):
    """Preserve the allowlisted analysis, replacing non-finite values with unknown."""
    if depth>6:return None
    if value is None or isinstance(value,bool):return value
    if isinstance(value,str):return value[:800]
    if finite(value):return value
    if isinstance(value,dict):return {str(k):safe_evidence(v,depth+1) for k,v in list(value.items())[:80]}
    if isinstance(value,(list,tuple)):return [safe_evidence(v,depth+1) for v in value[:30]]
    return None


def observation(market,now):
    at=market.get('dataAt');price=market.get('price')
    fresh=finite(at) and -2000<=now-at<=90000 and market.get('priceFresh') is True
    valid=bool(fresh and finite(price) and price>0 and finite(market.get('analysisBarAt')))
    adx=(market.get('context') or {}).get('adx')
    direction=market.get('direction','NEUTRAL')
    allowed=valid and market.get('ready') is True and direction in ('LONG','SHORT') and (market.get('entryTimingGate') or {}).get('allowed') is True and (market.get('session') or {}).get('entryAllowed') is True
    return dict(build=os.environ.get('RENDER_GIT_COMMIT','local'),evidence=safe_evidence({k:market.get(k) for k in ('context','entryTimingGate','entryQuality','minuteEntry','analysisSnapshot','plan','trendContext','session')}),at=now,price=price if finite(price) else None,priceAt=at if finite(at) else None,
        valid=valid,ready=bool(allowed),direction=direction if direction in ('LONG','SHORT') else 'NEUTRAL',
        adx=adx if finite(adx) else None,keep=bool(allowed and finite(adx) and adx>=25),
        reason=str(market.get('decisionReason') or 'Kein freigegebenes Signal')[:400],
        cohort=str(market.get('ruleVersion') or 'unknown')+'|'+str(market.get('learningPolicy') or 'baseline'))


def capture(conn,market,now=None):
    now=int(time.time()*1000) if now is None else now
    if not eligible(now):return False
    protocol=conn.execute('SELECT payload FROM bob_improvement_protocol WHERE id=%s',(VERSION,)).fetchone()
    if not protocol or protocol[0]!=PROTOCOL:raise ValueError('Improvement protocol mismatch')
    row=observation(market,now); slot=now//30000*30000; day=clock(now).date().isoformat()
    conn.execute('INSERT INTO bob_improvement_observations VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                 (VERSION,slot,day,row['valid'],json.dumps(row,allow_nan=False)))
    # Same fixed two-hour slots, even neutral/invalid observations stay in the denominator.
    local=clock(now)
    if local.hour%2==0 and local.minute*60+local.second<90 and local.hour<=20:
        transition=conn.execute('SELECT validation_at FROM bob_improvement_state WHERE campaign=%s',(VERSION,)).fetchone()
        phase='validation' if transition and transition[0] is not None and now>=transition[0] else 'development'
        conn.execute('INSERT INTO bob_improvement_trials VALUES(%s,%s,%s,%s,%s::jsonb,NULL) ON CONFLICT DO NOTHING',
                     (VERSION,slot-(local.minute*60+local.second)//30*30000,day,phase,json.dumps(row,allow_nan=False)))
    if row['valid']:
        pending=conn.execute('''SELECT slot,payload FROM bob_improvement_trials
          WHERE campaign=%s AND outcome IS NULL AND slot<=%s AND slot>=%s ORDER BY slot LIMIT 8''',
          (VERSION,now-3600000,now-3780000)).fetchall()
        for trial_slot,base in pending:
            if not base.get('valid') or not base.get('ready') or not finite(base.get('adx')):continue
            due=base['at']+3600000
            if not due<=row['priceAt']<=due+90000:continue
            change=(row['price']/base['price']-1)*100*(1 if base['direction']=='LONG' else -1)
            out=dict(at=row['priceAt'],directionalPct=change,keep=base['keep'],
                     scenarios=[dict(costPct=c,baseline=change-c,candidate=change-c if base['keep'] else 0) for c in PROTOCOL['costPct']])
            conn.execute('UPDATE bob_improvement_trials SET outcome=%s::jsonb WHERE campaign=%s AND slot=%s AND outcome IS NULL',
                         (json.dumps(out,allow_nan=False),VERSION,trial_slot))
    # Freeze the boundary only after sufficient completed development observations.
    conn.execute('''UPDATE bob_improvement_state SET validation_at=%s WHERE campaign=%s AND validation_at IS NULL
        AND (SELECT count(*) FROM bob_improvement_trials WHERE campaign=%s AND phase='development' AND outcome IS NOT NULL)>=60
        AND (SELECT count(DISTINCT day) FROM bob_improvement_trials WHERE campaign=%s AND phase='development' AND outcome IS NOT NULL)>=10''',
        (now+1,VERSION,VERSION,VERSION))
    return True


def ratio(n,target):return min(1,max(0,n/target))


def pairs(rows):
    complete=[(day,p,o) for day,phase,p,o in rows if o]
    out=dict(count=len(complete),days=len({d for d,p,o in complete}),falseSignals=0,
             avoidedLosses=0,missedGains=0,retained=0,scenarios=[])
    for day,p,o in complete:
        out['falseSignals']+=o['directionalPct']<=0
        out['avoidedLosses']+=not o['keep'] and o['scenarios'][0]['baseline']<0
        out['missedGains']+=not o['keep'] and o['scenarios'][0]['baseline']>0
        out['retained']+=o['keep']
    for i,cost in enumerate(PROTOCOL['costPct']):
        base=[o['scenarios'][i]['baseline'] for d,p,o in complete]
        cand=[o['scenarios'][i]['candidate'] for d,p,o in complete]
        out['scenarios'].append(dict(costPct=cost,baselineMean=sum(base)/len(base) if base else None,
            candidateMean=sum(cand)/len(cand) if cand else None,
            difference=sum(c-b for b,c in zip(base,cand))/len(base) if base else None))
    out['falseSignalPct']=100*out['falseSignals']/out['count'] if out['count'] else None
    return out


def real_results(rows,evidence=None,validation_at=None):
    complete=[]; paired=[]; missing=0
    evidence=evidence or {}
    for snapshot in rows:
        if snapshot.get('active') or snapshot.get('test') or snapshot.get('recordOnly'):continue
        bounds=trade_learning_review.window(snapshot)
        if not bounds:
            missing+=1;continue
        if bounds[0].timestamp()*1000<START:continue
        review=trade_risk_review.evaluation(snapshot)
        # Only comparable CHF settlement totals; no mixing currencies or model P/L.
        value=review['realizedNetCHF']
        if value is None:missing+=1;continue
        complete.append((bounds[1].astimezone(ZONE).date().isoformat(),bounds[1].timestamp(),value))
        before=evidence.get(snapshot.get('tradeId'))
        if before and before.get('valid') and finite(before.get('priceAt')) and 0<=bounds[0].timestamp()*1000-before['priceAt']<=90000 and finite(before.get('at')) and 0<=bounds[0].timestamp()*1000-before['at']<=90000 and not bounds[2] and validation_at is not None and bounds[0].timestamp()*1000>=validation_at and before.get('ready') and before.get('direction')==snapshot.get('dir') and finite(before.get('adx')):
            paired.append((bounds[1].astimezone(ZONE).date().isoformat(),value,value if before['keep'] else 0))
    complete.sort(key=lambda x:x[1]);running=peak=drawdown=0
    for day,at,value in complete:
        running+=value;peak=max(peak,running);drawdown=max(drawdown,peak-running)
    return dict(pairedCount=len(paired),pairedDays=len({r[0] for r in paired}),pairedBaselineCHF=round(sum(r[1] for r in paired),2) if paired else None,pairedCandidateCHF=round(sum(r[2] for r in paired),2) if paired else None,count=len(complete),days=len({x[0] for x in complete}),netCHF=round(running,2) if complete else None,
        drawdownCHF=round(drawdown,2) if complete else None,missing=missing,
        note='Rückgang der kumulierten abgeschlossenen CHF-Ergebnisse; keine Intraday-Depotbewertung. Keine Aufforderung zu zusätzlichen Trades.')


def summarize(observed,valid,days,last,rows,real,now,validation_at=None):
    expected=expected_slots(now);coverage=min(1,valid/expected) if expected else 0
    latest=next((p['cohort'] for day,phase,p,o in reversed(rows)),None)
    current=[r for r in rows if r[2]['cohort']==latest]
    dev=pairs([r for r in current if r[1]=='development'])
    val=pairs([r for r in current if r[1]=='validation'])
    # Coverage of scheduled trial slots, not only available/selected trades.
    scheduled=expected_trial_slots(now,validation_at)
    captured=len([r for r in current if r[1]=='validation'])
    paired_ready=len([r for r in current if r[1]=='validation' and r[2]['ready'] and finite(r[2].get('adx')) and r[2]['at']+3690000<=now])
    trial_coverage=min(1,captured/scheduled) if scheduled else 0
    outcome_coverage=min(1,val['count']/paired_ready) if paired_ready else 0
    dev_fraction=min(ratio(dev['count'],60),ratio(dev['days'],10))
    val_fraction=min(ratio(val['count'],100),ratio(val['days'],20),ratio(trial_coverage,.95),ratio(outcome_coverage,.95))
    progress=[math.floor(100*min(ratio(days,20),ratio(coverage,.95))),
              math.floor(100*min(ratio(real['count'],20),ratio(real['days'],10))),
              math.floor(50*dev_fraction+50*val_fraction),
              math.floor(25*dev_fraction+25*val_fraction+50*min(ratio(real['pairedCount'],20),ratio(real['pairedDays'],10)))]
    if now<START:progress=[0]*4
    result=dict(ok=True,protocol=PROTOCOL,generatedAt=now,started=now>=START,
        progress=progress,validationAt=validation_at,reliability=dict(observed=observed,valid=valid,expected=expected,
        coveragePct=round(coverage*100,2) if expected else None,days=days,lastAt=last,
        missingSlots=max(0,expected-observed)),real=real,
        comparison=dict(development=dev,validation=val,cohort=latest,excludedOtherVersions=len(rows)-len(current),
        coveragePct=round(trial_coverage*100,2) if scheduled else None,
        outcomeCoveragePct=round(outcome_coverage*100,2) if paired_ready else None),
        adoption=dict(status=('Vergleich vollständig; Vorteil prüfen, keine automatische Übernahme' if progress[3]==100 else 'Unabhängiger Vergleich und zugeordnete Nettoabrechnungen werden gesammelt'),
        automaticRuleChange=False,productNetValidated=False,
        note='50 %: vollständiger unabhängiger Spotvergleich. 50 %: mindestens 20 zeitlich zugeordnete Nettoabrechnungen an 10 späteren Tagen. Verglichen werden tatsächlich gehandelte Positionen gegen Auslassen durch den Filter. Auswahlverzerrung bleibt möglich; 100 % bedeutet Prüfziel erreicht, keine bewiesene allgemeine Überlegenheit oder Handelsfreigabe.'))

    result['assessment']=improvement_assessment.assess(rows,result['comparison'],real,progress,now>=START,result['reliability'])
    return result


def expected_trial_slots(now,validation_at):
    if validation_at is None:return 0
    day=clock(validation_at).date(); end=clock(now).date(); n=0
    while day<=end:
        if day.weekday()<5:
            for h in range(8,21,2):
                at=int(datetime(day.year,day.month,day.day,h,tzinfo=ZONE).timestamp()*1000)
                if validation_at<=at and at+90000<=now:n+=1
        day+=timedelta(days=1)
    return n


def report(conn,now=None,include_history=True):
    now=int(time.time()*1000) if now is None else now
    protocol=conn.execute('SELECT payload FROM bob_improvement_protocol WHERE id=%s',(VERSION,)).fetchone()
    if not protocol or protocol[0]!=PROTOCOL:raise ValueError('Improvement protocol mismatch')
    stats=conn.execute('''SELECT count(*),count(*) FILTER (WHERE valid),
        count(DISTINCT day) FILTER (WHERE valid),max(slot) FROM bob_improvement_observations
        WHERE campaign=%s AND slot<%s''',(VERSION,now//30000*30000)).fetchone()
    rows=conn.execute('SELECT day,phase,payload,outcome FROM bob_improvement_trials WHERE campaign=%s ORDER BY slot',(VERSION,)).fetchall()
    snapshots=conn.execute('''SELECT snapshot FROM bob_real_trades WHERE active=FALSE
        AND updated_at>=to_timestamp(%s/1000.0) ORDER BY updated_at''',(START,)).fetchall()
    state=conn.execute('SELECT validation_at FROM bob_improvement_state WHERE campaign=%s',(VERSION,)).fetchone()
    validation_at=state[0] if state else None
    evidence={}
    for (snapshot,) in snapshots:
        bounds=trade_learning_review.window(snapshot)
        if not bounds or bounds[2] or bounds[0].timestamp()*1000<START:continue
        bought=int(bounds[0].timestamp()*1000)
        before=conn.execute('''SELECT payload FROM bob_improvement_observations WHERE campaign=%s
          AND slot BETWEEN %s AND %s AND (payload->>'at')::bigint<=%s ORDER BY slot DESC LIMIT 1''',
          (VERSION,bought-90000,bought,bought)).fetchone()
        if before:evidence[snapshot.get('tradeId')]=__import__('cold_observations').resolve(conn,before[0])
    result=summarize(*stats,rows,real_results([s[0] for s in snapshots],evidence,validation_at),now,validation_at)
    import improvement_operations
    improvement_operations.attach(conn,result,rows,[s[0] for s in snapshots],now,START)
    if include_history:
        import decision_journal
        result['decisionJournal']=decision_journal.read(conn,VERSION,now)
        import entry_path_study
        result['entryPath']=entry_path_study.read(conn,VERSION,now)
        import exit_quality
        result['exitQuality']=exit_quality.read(conn,now)
        history=conn.execute('SELECT at,payload FROM bob_improvement_reviews WHERE campaign=%s ORDER BY at DESC,id LIMIT 50',(VERSION,)).fetchall()
        result['history']=[dict(at=at,**payload) for at,payload in history]
    return result


def archive_review(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    if now<START:return
    result=report(conn,now,include_history=False);a=result['assessment'];c=result['comparison']
    review=dict(version=a['version'],baseline='Aktuelle freigegebene Regel',candidate=PROTOCOL['candidate'],
        cohort=c['cohort'],label=a['label'],decision=a['decision'],code=a['code'],
        cases=a['independentCases'],days=a['days'],developmentCases=c['development']['count'],
        realPairs=result['real']['pairedCount'],netDifferenceCHF=a['netDifferenceCHF'],
        standardDifference=c['validation']['scenarios'][0]['difference'],
        stressDifference=c['validation']['scenarios'][1]['difference'],
        coveragePct=c['coveragePct'],outcomeCoveragePct=c['outcomeCoveragePct'],
        actualRuleChange=False)
    identity={k:v for k,v in review.items() if k not in ('coveragePct','outcomeCoveragePct')}
    key=hashlib.sha256(json.dumps([VERSION,clock(now).date().isoformat(),identity],sort_keys=True).encode()).hexdigest()
    conn.execute('INSERT INTO bob_improvement_reviews VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                 (key,VERSION,now,json.dumps(review,allow_nan=False)))
    import improvement_operations
    return improvement_operations.archive(conn,result,now)
