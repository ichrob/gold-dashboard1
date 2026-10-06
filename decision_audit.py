"""Immutable decision evidence and forward-only outcome review. No orders or self-modifying code."""
import hashlib
import bisect
import json
import math
import os
import time
import threading
import copy
from datetime import datetime, timezone

VERSION = 'decision-audit-v1'
RULE_VERSION = 'intraday-1h-15m-5m-v2'

def milliseconds(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if math.isfinite(value) else None
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp()*1000 if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None

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
    result = {k: payload.get(k) for k in ('direction','shadowDirection','intraday','barAt','price','priceAt','reason','score','indicators','products','selection','gateReasons')}
    result.update(version=VERSION, ruleVersion=payload['ruleVersion'] if payload.get('ruleVersion') in (RULE_VERSION, 'intraday-1h-15m-5m-v1') else 'signal-5m-two-closes-v1', build=os.environ.get('RENDER_GIT_COMMIT','local'), origin=payload.get('origin','browser'), recordedAt=now)
    if result['origin'] not in ('browser','background'):
        raise ValueError('Ungültige Protokollquelle')
    if result.get('shadowDirection') not in ('LONG','SHORT','NEUTRAL'):
        result['shadowDirection'] = None
    intraday=result.get('intraday')
    if not isinstance(intraday,dict) or intraday.get('version')!='intraday-v1' or intraday.get('direction') not in ('LONG','SHORT','NEUTRAL'):result['intraday']=None
    if not isinstance(result.get('products'), list): result['products'] = []
    if len(result['products']) > 12: raise ValueError('Zu viele Produkte')
    at = milliseconds(result.get('priceAt'))
    result['marketEvaluable'] = positive(result.get('price')) and at is not None and 0 <= now-at <= 180000
    # Each decision revision is frozen once. Refreshes with unchanged evidence are idempotent.
    identity={k:result[k] for k in ('version','ruleVersion','origin','direction','shadowDirection','intraday','barAt','reason','products','selection','gateReasons')}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return key,result

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_decision_audit (
        id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_audit_recorded ON bob_decision_audit(recorded_at)')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_decision_outcomes (decision_id TEXT REFERENCES bob_decision_audit(id) ON DELETE CASCADE, horizon INTEGER NOT NULL, truth JSONB NOT NULL, PRIMARY KEY(decision_id,horizon))''')

def write(conn,payload):
    key,record=normalize(payload)
    conn.execute('INSERT INTO bob_decision_audit(id,payload) VALUES(%s,%s::jsonb) ON CONFLICT(id) DO NOTHING',(key,json.dumps(record,allow_nan=False)))
    conn.execute("DELETE FROM bob_decision_audit WHERE recorded_at < now()-interval '30 days'")
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

def summarize(rows):
    legacy_count=sum(r.get('ruleVersion')!=RULE_VERSION for r,_ in rows)
    rows=[(r,t) for r,t in rows if r.get('ruleVersion')==RULE_VERSION]
    metrics={str(h):{'evaluated':0,'favorable':0,'unfavorable':0,'flat':0,'neutral':0,'missing':0,'directionalSumPct':0} for h in (15,60,240)}
    intraday_metrics={h:dict(m) for h,m in metrics.items()}
    seen=set();pairs=[];issues={};latest=[r for r,_ in rows[:30]]
    for record,truths in sorted(rows,key=lambda row:row[0].get('origin')!='background'):
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
            if not record.get('intraday') or not record['intraday'].get('available') or result is None:im['missing']+=1
            elif iv is None:im['neutral']+=1
            else:
                im['evaluated']+=1;im['directionalSumPct']+=iv;im['favorable' if iv>0 else 'unfavorable' if iv<0 else 'flat']+=1
            if result is None:m['missing']+=1;continue
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
        'learning':{'mode':'Schattenvergleich: 2 gegen 3 Bestätigungskerzen','samples':len(spaced),
                    'training':len(train),'holdout':len(holdout),'ready':ready,'candidateBetter':better,
                    'trainingDeltaPct':train_delta,'holdoutDeltaPct':test_delta,
                    'status':'Verbesserungskandidat zur Prüfung vorhanden' if better else 'Vergleich ohne belegte Verbesserung' if ready else 'Sammelt unabhängige Vergleiche; noch keine Regeländerung',
                    'automaticRuleChange':False},'version':VERSION,'retentionDays':30}

_harvest_at=0

def harvest(conn):
    global _harvest_at
    if time.time()-_harvest_at<60:return
    conn.execute("""INSERT INTO bob_decision_outcomes(decision_id,horizon,truth)
      SELECT a.id,h.minutes,json_build_object('at',s.quote_at,'price',s.price)::jsonb
      FROM bob_decision_audit a CROSS JOIN (VALUES (15),(60),(240)) h(minutes)
      CROSS JOIN LATERAL (SELECT quote_at,price FROM bob_spot_observations
        WHERE stream='gold-api-xau-usd-v1'
        AND quote_at>=a.recorded_at+h.minutes*interval '1 minute'
        AND quote_at<=a.recorded_at+(h.minutes+1)*interval '1 minute'
        ORDER BY quote_at LIMIT 1) s
      WHERE a.recorded_at>=now()-interval '7 days'
      AND NOT EXISTS (SELECT 1 FROM bob_decision_outcomes o WHERE o.decision_id=a.id AND o.horizon=h.minutes)
      ON CONFLICT DO NOTHING""")
    _harvest_at=time.time()

_report_lock = threading.Lock()
_report_cache = None
_report_at = 0

def report(conn):
    # Browser startup, visibility changes and periodic refresh can overlap.
    # Coalesce identical reports; failures never refresh the cached timestamp.
    global _report_cache, _report_at
    with _report_lock:
        if _report_cache is not None and time.monotonic()-_report_at < 30:
            return copy.deepcopy(_report_cache)
        result = _build_report(conn)
        result['generatedAt'] = int(time.time()*1000)
        _report_cache = copy.deepcopy(result)
        _report_at = time.monotonic()
        return result


def _build_report(conn):
    harvest(conn)
    rows=conn.execute("""SELECT a.payload,
      (SELECT truth FROM bob_decision_outcomes WHERE decision_id=a.id AND horizon=15),
      (SELECT truth FROM bob_decision_outcomes WHERE decision_id=a.id AND horizon=60),
      (SELECT truth FROM bob_decision_outcomes WHERE decision_id=a.id AND horizon=240)
      FROM bob_decision_audit a ORDER BY a.recorded_at DESC LIMIT 10000""").fetchall()
    result=summarize([(row[0],row[1:]) for row in rows])
    result['total']=conn.execute('SELECT count(*) FROM bob_decision_audit').fetchone()[0]
    result['scope']='Aktuelle Intraday-Regel; frühere Regeln getrennt ('+str(result['legacyCount'])+' ältere Protokolle). Bis 30 Tage; Gold-Richtung ohne Handelskosten, kein Gewinnnachweis'
    result['productReview']=product_review([row[0] for row in rows[:1500]])
    research=[];seen=set()
    for row in rows:
        for p in row[0].get('products',[]):
            key=(p.get('isin'),p.get('researchAt'))
            if key in seen:continue
            seen.add(key)
            conflicts=[str(x) for x in p.get('reasons',[]) if 'widerspr' in str(x).lower()]
            research.append({'isin':p.get('isin'),'source':p.get('researchSource'),'at':p.get('researchAt'),'conflicts':conflicts})
    result['researchReview']={'observations':len(research),'conflicts':sum(bool(p['conflicts']) for p in research),'missingSourceOrTime':sum(not p['source'] or not p['at'] for p in research),'examples':[p for p in research if p['conflicts']][:10],'note':'Widersprüche sind Prüfhinweise, keine automatisch bewiesenen Recherchefehler. Abrufzeit beweist keine Aktualität der Produktwerte.'}
    return result

def product_review(records):
    """Compare real bid/ask observations; never turn estimated prices into ground truth."""
    ordered=sorted(records,key=lambda r:r['recordedAt']);results=[];seen=set();quotes={};comparisons=[]
    for r in ordered:
        for p in r.get('products',[]):
            at=milliseconds(p.get('quoteAt'))
            if at is not None and positive(p.get('bid')) and 0<=r['recordedAt']-at<=90000:
                quotes.setdefault(p.get('isin'),[]).append((at,p['bid']))
    for isin in quotes:quotes[isin]=sorted(set(quotes[isin]))
    for record in ordered:
        selected=[p for p in record.get('products',[]) if p.get('selected')]
        if not selected:continue
        direction=record.get('direction');returns=[]
        for product in record.get('products',[]):
            isin=product.get('isin');start=milliseconds(product.get('quoteAt'));ask=product.get('ask')
            if not positive(ask) or start is None or not 0<=record['recordedAt']-start<=90000:continue
            target=record['recordedAt']+3600000;history=quotes.get(isin,[]);index=bisect.bisect_left(history,(target,0))
            if index>=len(history) or history[index][0]>target+300000:continue
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
            'comparisons':len(comparisons),'selectedBest':sum(comparisons),
            'note':'Beobachteter Geldkurs nach 60 Minuten gegen damaligen Briefkurs; ohne Gebühren. Alternativen nur bei damaliger Eignung und passenden späteren Kursen. Fehlende Kurse werden nicht geschätzt; begrenzter Rückblick, kein Optimalitätsnachweis.'}

def handle(conn,action,payload):
    if action=='write':
        result=write(conn,payload)
        harvest(conn)
        return result
    if action=='read':return report(conn)
    raise ValueError('Unbekannte Protokollaktion')
