"""Prospective original-bid exit study; never changes trading state or places orders."""
import json
import math
from datetime import datetime,timezone
from zoneinfo import ZoneInfo

VERSION='exit-quality-v1-20261019'
START=int(datetime(2026,10,19,8,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
PROTOCOL=dict(version=VERSION,startAt=START,horizonMinutes=60,captureSeconds=30,maxGapSeconds=90,
              minCoveragePct=95,costPct=[.10,.30],trailingActivationR=1,trailingDistanceR=1,
              automaticRuleChange=False)
NOTE='Ein prospektiver 60-Minuten-Fall je Trade. Start am ersten gültigen Originalkurs nach Freischaltung; kein nachträglicher Einstieg zum Kaufkurs. Stopp/Ziel werden aus dem damaligen Goldplan mit damaligem FX berechnet und eingefroren. Variante: nach +1R den Stopp mit Abstand 1R zum bisherigen Höchstkurs nachziehen, nie lockern. Einstieg am beobachteten Briefkurs, Referenzausstieg am ersten beobachteten Geldkurs nach Berührung; keine bestätigten Ausführungen. Zusatzkosten 0,10/0,30 % sind Annahmen. Gleiche ISIN, Währung, Modellbasis und Quelle erforderlich. Fehlende Kurse und vorzeitig beendete Überwachung bleiben offen. Stichproben zeigen keine lückenlosen Intrabar-Verläufe. Keine Änderung aktiver Stopps oder Orders.'


def finite(v):return type(v) in (int,float) and math.isfinite(v)
def pos(v):return finite(v) and v>0


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_exit_quality_protocol
        (id TEXT PRIMARY KEY,payload JSONB NOT NULL)''')
    conn.execute('INSERT INTO bob_exit_quality_protocol VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING',(VERSION,json.dumps(PROTOCOL)))
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_exit_quality_cases (
        trade_id TEXT NOT NULL,version TEXT NOT NULL,payload JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(trade_id,version))''')


def check(conn):
    row=conn.execute('SELECT payload FROM bob_exit_quality_protocol WHERE id=%s',(VERSION,)).fetchone()
    if not row or row[0]!=PROTOCOL:raise ValueError('Exit quality protocol mismatch')


def seed(trade,row,point,ask,now):
    import background_push
    import product_comparison_worker as worker
    p=trade.get('product') or {}
    from product_trade_history import clock
    fx_at=clock(point.get('fxAt'))
    if (now<START or not pos(ask) or not pos(row.get('quoted')) or ask<row['quoted']
        or row.get('currency') not in ('EUR','CHF') or p.get('currency')!=row['currency']
        or row.get('side')!='bid' or row.get('kind')!='issuer' or not row.get('source')
        or not finite(row.get('at')) or not 0<=now-row['at']<=90000
        or not pos(point.get('fxRate')) or not fx_at or not 0<=now-fx_at.timestamp()*1000<=90000):return None
    stop=background_push.product_price(dict(p,fxScenario=point['fxRate']),trade.get('stop'))
    target=background_push.product_price(dict(p,fxScenario=point['fxRate']),trade.get('target'))
    if not pos(stop) or not pos(target) or not stop<row['quoted']<=ask<target:return None
    return dict(at=now,isin=p['isin'],currency=p['currency'],source=row['source'],
        modelKey=worker.model_key(p),entry=ask,initialBid=row['quoted'],stop=stop,target=target,
        risk=ask-stop,goldStop=trade.get('stop'),goldTarget=trade.get('target'),
        fxRate=point['fxRate'],fxAt=point.get('fxAt'),quoteAt=row['at'],askAt=row.get('askAt'),
        proposalKind='contemporaneous-model',points=[],mismatches=0)


def append(case,row,model_key,now):
    if (model_key!=case['modelKey'] or row.get('currency')!=case['currency']
        or row.get('source')!=case['source'] or row.get('side')!='bid' or row.get('kind')!='issuer'):
        case['mismatches']=min(999999,case.get('mismatches',0)+1);return
    at=row.get('at')
    if not pos(row.get('quoted')) or not finite(at) or not 0<=now-at<=90000:return
    if not case['at']<at<=case['at']+3690000:return
    if case['points'] and at<=case['points'][-1]['at']:return
    # One original point per 30-second source bucket; repeated cached clocks add nothing.
    bucket=int((at-case['at']-1)//30000)
    if any(p['bucket']==bucket for p in case['points']):return
    if len(case['points'])>=123:return
    case['points'].append(dict(at=at,bid=row['quoted'],bucket=bucket))


def observe(conn,tid,trade,row,point,ask,now):
    import product_comparison_worker as worker
    if now<START:return
    check(conn)
    stored=conn.execute('SELECT payload FROM bob_exit_quality_cases WHERE trade_id=%s AND version=%s FOR UPDATE',(tid,VERSION)).fetchone()
    case=stored[0] if stored else seed(trade,row,point,ask,now)
    if case is None:return
    if now>case['at']+3780000:return
    append(case,row,worker.model_key(trade.get('product') or {}),now)
    conn.execute('''INSERT INTO bob_exit_quality_cases(trade_id,version,payload) VALUES(%s,%s,%s::jsonb)
        ON CONFLICT(trade_id,version) DO UPDATE SET payload=excluded.payload,updated_at=now()''',
        (tid,VERSION,json.dumps(case,allow_nan=False)))


def evaluate(case,now):
    entry=case['entry'];start=case['at'];due=start+3600000
    points=[p for p in case['points'] if p['at']<=now]
    endpoint=next((p for p in points if due<=p['at']<=due+90000),None)
    path=[p for p in points if not endpoint or p['at']<=endpoint['at']]
    expected=max(0,min(120,int((now-start)//30000)))
    coverage=min(100,100*len({p['bucket'] for p in path if p['bucket']<120})/expected) if expected else None
    clocks=[start]+[p['at'] for p in path]
    gap=max([b-a for a,b in zip(clocks,clocks[1:])]+[max(0,min(now,due)-clocks[-1])])
    complete=bool(endpoint and coverage is not None and coverage>=95 and gap<=90000 and not case.get('mismatches'))
    result=dict(at=start,isin=case['isin'],currency=case['currency'],source=case['source'],
        status='complete' if complete else 'missing' if now>due+180000 else 'collecting',
        coveragePct=round(coverage,1) if coverage is not None else None,maxGapSeconds=round(gap/1000,1),
        observations=len(path),entry=entry,stop=case['stop'],target=case['target'],
        referenceExits={},scenarios=[],stopReboundPct=None,stopRecoveredEntry=None,
        targetPullbackPct=None,peakGivebackPct=None,proposalKind=case['proposalKind'])
    # Observed threshold crossings can be described even when the comparison is incomplete.
    exits={};peak=case['initialBid'];trailing=case['stop']
    for p in path:
        bid=p['bid']
        for name,stop in (('fixed',case['stop']),('trailing',trailing)):
            if name not in exits:
                reason='stop' if bid<=stop else 'target' if bid>=case['target'] else None
                if reason:exits[name]=dict(at=p['at'],bid=bid,reason=reason,level=stop if reason=='stop' else case['target'])
        peak=max(peak,bid)
        if peak>=entry+case['risk']:trailing=max(trailing,peak-case['risk'])
    if endpoint:
        for name in ('fixed','trailing'):
            exits.setdefault(name,dict(at=endpoint['at'],bid=endpoint['bid'],reason='horizon',level=None))
        result['peakGivebackPct']=round(max(0,(peak-endpoint['bid'])/entry*100),3)
    result['referenceExits']=exits
    fixed=exits.get('fixed')
    if fixed:
        later=[p['bid'] for p in path if p['at']>fixed['at']]
        if later and fixed['reason']=='stop':
            result['stopReboundPct']=round((max(later)-fixed['bid'])/entry*100,3)
            result['stopRecoveredEntry']=max(later)>=entry
        if later and fixed['reason']=='target':
            result['targetPullbackPct']=round(max(0,(fixed['bid']-min(later))/entry*100),3)
    if complete:
        for cost in PROTOCOL['costPct']:
            baseline=(exits['fixed']['bid']/entry-1)*100-cost
            candidate=(exits['trailing']['bid']/entry-1)*100-cost
            result['scenarios'].append(dict(costPct=cost,baselinePct=baseline,candidatePct=candidate,differencePct=candidate-baseline))
    return result


def read(conn,now):
    check(conn)
    rows=conn.execute('''SELECT trade_id,payload FROM bob_exit_quality_cases WHERE version=%s
        ORDER BY (payload->>'at')::bigint DESC,trade_id LIMIT 30''',(VERSION,)).fetchall()
    return dict(protocol=PROTOCOL,items=[dict(evaluate(p,now),tradeId=tid) for tid,p in rows],
        note=NOTE,ordersPlaced=False,automaticRuleChange=False)
