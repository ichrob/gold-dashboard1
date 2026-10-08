"""Frozen four-day, prospective paired hourly signal study. No orders or fitted rules."""
import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ID='gold-fast-cautious-20261006-v1'
POLICY='intraday-responsive-v6'
START=int(datetime(2026,10,6,5,tzinfo=timezone.utc).timestamp()*1000)
END=START+4*86400000
HOUR=3600000

def active(now=None):
    now=time.time()*1000 if now is None else now
    return START<=now<END+HOUR

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_intraday_comparison (
      campaign TEXT NOT NULL, slot BIGINT NOT NULL, payload JSONB NOT NULL,
      truth JSONB, PRIMARY KEY(campaign,slot))''')

def slot_at(now):
    return START+int((now-START)//HOUR)*HOUR

def eligible(slot):
    return START<=slot<END and datetime.fromtimestamp(slot/1000,ZoneInfo('Europe/Zurich')).weekday()<5

def observation(market,now):
    baseline=market.get('comparisonBaseline')
    if market.get('ruleVersion')=='intraday-trend-follow-v7' and isinstance(baseline,dict):
        market={**market,**{k:baseline.get(k) for k in ('ruleVersion','direction','shadowDirection','decisionReason')}}
    slot=slot_at(now)
    if not eligible(slot) or not 0<=now-slot<300000:return None
    directions=[market.get('direction'),market.get('shadowDirection')]
    price=market.get('price');at=market.get('dataAt');bar=market.get('analysisBarAt')
    number=lambda v:isinstance(v,(int,float)) and not isinstance(v,bool) and __import__('math').isfinite(v)
    valid=bool(market.get('ready') and market.get('priceFresh') and market.get('ruleVersion')==POLICY
       and number(price) and price>0 and number(at) and 0<=now-at<=60000
       and number(bar) and 300000<=now-bar<=600000
       and all(d in ('LONG','SHORT','NEUTRAL') for d in directions))
    failures=[]
    if not market.get('ready'):failures.append('Analyse nicht bereit')
    if not market.get('priceFresh') or not number(at) or not 0<=now-at<=60000:failures.append('Spot-Quellenzeit fehlt oder nicht innerhalb 60 Sekunden')
    if not number(bar) or not 300000<=now-bar<=600000:failures.append('Geschlossene 5m-Kerze fehlt oder veraltet')
    if market.get('ruleVersion')!=POLICY:failures.append('Vergleichsregel stimmt nicht überein')
    if not number(price) or price<=0:failures.append('Spotpreis fehlt')
    if not all(d in ('LONG','SHORT','NEUTRAL') for d in directions):failures.append('Gepaarte Richtungen fehlen')
    return dict(campaign=ID,slot=slot,recordedAt=now,valid=valid,validationFailures=failures,price=price if number(price) else None,
       priceAt=at if number(at) else None,barAt=bar if number(bar) else None,
       fast=directions[0] if valid else None,cautious=directions[1] if valid else None,
       entryQuality=market.get('entryQuality'),reason=market.get('decisionReason') or 'Aktuelle gemeinsame Datenbasis fehlt',policy=market.get('ruleVersion'))

def needs_capture(conn, now):
    slot = slot_at(now)
    if not eligible(slot) or not 0 <= now-slot < 300000:return False
    row = conn.execute('SELECT payload FROM bob_intraday_comparison WHERE campaign=%s AND slot=%s',(ID,slot)).fetchone()
    return not row or not row[0].get('valid')

def capture(conn,market,now=None):
    now=int(time.time()*1000) if now is None else now
    record=observation(market,now)
    if record:
        conn.execute('''INSERT INTO bob_intraday_comparison(campaign,slot,payload) VALUES(%s,%s,%s::jsonb)
          ON CONFLICT(campaign,slot) DO UPDATE SET payload=EXCLUDED.payload || jsonb_build_object(
            'firstAttempt',bob_intraday_comparison.payload,'recoveredWithinWindow',TRUE)
          WHERE (bob_intraday_comparison.payload->>'valid')::boolean=FALSE
            AND (EXCLUDED.payload->>'valid')::boolean=TRUE
            AND bob_intraday_comparison.truth IS NULL''',(ID,record['slot'],json.dumps(record,allow_nan=False)))
    harvest(conn,now)
    return record

def harvest(conn,now=None):
    # Save outcomes permanently with the campaign, independent of the rolling quote archive.
    conn.execute('''UPDATE bob_intraday_comparison a SET truth=x.truth FROM (
      SELECT c.campaign,c.slot,json_build_object('price',s.price,'at',extract(epoch from s.quote_at)*1000,
        'low',ext.lo,'high',ext.hi,'minutes',ext.minutes)::jsonb truth
      FROM bob_intraday_comparison c
      CROSS JOIN LATERAL (SELECT quote_at,price FROM bob_spot_observations
        WHERE stream='gold-api-xau-usd-v1'
        AND quote_at>=to_timestamp(((c.payload->>'recordedAt')::double precision+3600000)/1000)
        AND quote_at<=to_timestamp(((c.payload->>'recordedAt')::double precision+3660000)/1000)
        ORDER BY quote_at LIMIT 1) s
      LEFT JOIN LATERAL (SELECT min(price) lo,max(price) hi,count(DISTINCT date_trunc('minute',quote_at)) minutes
        FROM bob_spot_observations WHERE stream='gold-api-xau-usd-v1'
        AND quote_at>=to_timestamp((c.payload->>'recordedAt')::double precision/1000)
        AND quote_at<=s.quote_at) ext ON TRUE
      WHERE c.campaign=%s AND c.truth IS NULL AND (c.payload->>'valid')::boolean=TRUE
      ) x WHERE a.campaign=x.campaign AND a.slot=x.slot''',(ID,))

def summarize(rows,now=None):
    now=int(time.time()*1000) if now is None else now
    expected=[s for s in range(START,min(END,now),HOUR) if eligible(s)]
    records={r['slot']:(r,t) for r,t in rows if r.get('campaign')==ID and r.get('slot') in expected}
    stats={k:dict(signals=0,wins=0,losses=0,flat=0,wait=0,sumPct=0.,worstPct=None,adverseSumPct=0.,adverseCases=0) for k in ('fast','cautious')}
    pairs=0;missing=0;pending=0;avoided=0;missed=0;deltas=[]
    for slot in expected:
        item=records.get(slot)
        if not item:
            if now<slot+300000:pending+=1
            else:missing+=1
            continue
        r,t=item
        if not r.get('valid'):missing+=1;continue
        if now<r['recordedAt']+HOUR:pending+=1;continue
        if not t or not r['recordedAt']+HOUR<=t.get('at',0)<=r['recordedAt']+HOUR+60000:
            missing+=1;continue
        change=100*(t['price']/r['price']-1);pairs+=1;values={}
        for key,m in stats.items():
            d=r[key];value=change if d=='LONG' else -change if d=='SHORT' else 0;values[key]=value
            m['sumPct']+=value
            if d=='NEUTRAL':m['wait']+=1
            else:
                m['signals']+=1;m['wins' if value>0 else 'losses' if value<0 else 'flat']+=1
                m['worstPct']=min(value,m['worstPct']) if m['worstPct'] is not None else value
                if t.get('minutes',0)>=54 and t.get('low') and t.get('high'):
                    m['adverseCases']+=1;m['adverseSumPct']+=max(0,100*(r['price']-t['low'])/r['price'] if d=='LONG' else 100*(t['high']-r['price'])/r['price'])
        if r['fast']!='NEUTRAL' and r['cautious']=='NEUTRAL':
            avoided+=values['fast']<0;missed+=values['fast']>0
        deltas.append(values['fast']-values['cautious'])
    for m in stats.values():
        m['meanPct']=m['sumPct']/pairs if pairs else None
        m['hitRate']=100*m['wins']/m['signals'] if m['signals'] else None
        m['meanAdversePct']=m['adverseSumPct']/m['adverseCases'] if m['adverseCases'] else None
    complete=now>=END+60000;coverage=pairs/(len(expected)-pending) if len(expected)>pending else 0
    delta=sum(deltas)/pairs if pairs else None
    leader='nicht auswertbar' if delta is None else 'gleichauf' if abs(delta)<1e-10 else 'schnell' if delta>0 else 'vorsichtig'
    return dict(id=ID,start=START,end=END,status='abgeschlossen' if complete else 'geplant' if now<START else 'läuft',
       expected=len(expected),recorded=len(records),evaluated=pairs,missing=missing,pending=pending,coveragePct=coverage*100,
       variants=stats,leader=leader,meanDifferencePct=delta,avoidedUnfavorable=avoided,missedFavorable=missed,
       sufficient=complete and pairs>=20 and coverage>=.8,
       conclusion=('Deskriptiver Vorsprung im Test: '+leader) if complete and pairs>=20 and coverage>=.8 else 'Noch kein belastbarer Sieger; Test läuft oder Datenbasis zu klein/lückenhaft',
       note='Stündliche gemeinsame Beobachtungen, 60-Minuten-Goldbewegung; ABWARTEN zählt als 0. Keine echten Trades, keine Gebühren oder Produktrendite. Treffer = positive Richtungsbewegung nach 60 Minuten, kein Stop/Ziel-Test. Gegenbewegung nur aus gespeicherten Kursen mit mindestens 54 beobachteten Minuten. Vier Tage belegen keine dauerhafte Überlegenheit; keine automatische Regeländerung.')

def report(conn,now=None):
    # capture/background processing saves outcomes; a report only reads them.
    rows=conn.execute('SELECT payload,truth FROM bob_intraday_comparison WHERE campaign=%s ORDER BY slot',(ID,)).fetchall()
    return summarize(rows,now)

