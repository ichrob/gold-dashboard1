"""Three frozen paper stop variants; independent forward quotes, no ledger writes."""
import copy
import json
import math
import paper_costs

VERSION='paper-three-stops-v1'
LABELS={'fixed':'Fester Bob-Anfangsstopp','atr':'1,5 × ATR bei Einstieg','structure':'20 geschlossene 5m-Kerzen · Strukturstopp'}
NOTE=('Prospektiver Vergleich im ausgewogenen 100-EUR-Konto: gleicher Einstieg, gleiche Stückzahl, gleiches Ziel und Zeitende; vollständiger Modellverkauf je Variante. '
      'ATR und Struktur werden beim Einstieg eingefroren. Beispielkosten einschließlich Spread über Brief/Geld, keine bestätigten Brokergebühren. '
      'Kurslücken bleiben nicht auswertbar. Keine Änderung des Kontostands, des echten Bob-Stopps oder der Handelsfreigabe. '
      'Varianten haben unterschiedliche Anfangsrisiken; keine automatische Übernahme einer Gewinnerregel.')

def positive(v):return type(v) in (int,float) and math.isfinite(v) and v>0

def setup(market,bundle,now):
    p=market.get('plan') or {};direction=p.get('direction');entry=p.get('entry')
    atr=market.get('atr');atr=atr if positive(atr) else (market.get('analysisSnapshot') or {}).get('at')
    sign=1 if direction=='LONG' else -1
    levels={'fixed':p.get('stop'),'atr':entry-sign*1.5*atr if positive(entry) and positive(atr) else None,'structure':None}
    bars=(((bundle or {}).get('history') or {}).get('bars_by_tf') or {}).get('5m') or []
    usable=[b for b in bars if isinstance(b,dict) and b.get('instrument')=='XAU/USD' and b.get('isOpen') is False
            and positive(b.get('openTime')) and b['openTime']+300000<=now
            and all(positive(b.get(k)) for k in ('low','high','close')) and b['low']<=b['close']<=b['high']]
    usable=sorted(usable,key=lambda b:b['openTime'])[-20:]
    times=[b['openTime'] for b in usable]
    structure_at=None
    if len(usable)==20 and all(b-a==300000 for a,b in zip(times,times[1:])) and 0<=now-(times[-1]+300000)<=300000:
        levels['structure']=min(b['low'] for b in usable) if direction=='LONG' else max(b['high'] for b in usable)
        structure_at=times[-1]+300000
    return dict(version=VERSION,capturedAt=now,atrBarAt=market.get('analysisBarAt'),atr=atr if positive(atr) else None,structureAt=structure_at,
        stops={k:v if positive(v) and positive(entry) and sign*(entry-v)>0 else None for k,v in levels.items()})

def create(case):
    frozen=case.get('stopStudySetup') or {};plan=case.get('plan') or {}
    if case.get('demonstration') or frozen.get('version')!=VERSION or case.get('profile')!='balanced' or not positive(case.get('quantity')):return None
    return dict(version=VERSION,id=case['id'],day=case['day'],isin=case['product']['isin'],
        startedAt=case['startedAt'],endsAt=case['endsAt'],unit=plan.get('unit'),entry=plan['entry'],direction=plan['direction'],target=plan['target'],
        product=copy.deepcopy(case['product']),koGuardRequired=case.get('koGuardRequired') is True,quantity=case['quantity'],entryAsk=case['entryAsk'],costModel=copy.deepcopy(case.get('ledgerCostModel') or paper_costs.SCENARIOS[0]),
        setup=copy.deepcopy(frozen),lastGoldAt=case['analysis']['dataAt'],lastQuoteAt=case['entryQuote']['bidAt'],
        gap=False,complete=False,variants={k:dict(label=label,stop=frozen['stops'].get(k),status='open' if frozen['stops'].get(k) else 'unavailable',modelNetEur=None)
                                         for k,label in LABELS.items()})

def advance(original,market,quote,now):
    from paper_simulation import fresh_quote,stamp
    from paper_ko_guard import terminal,assess
    s=copy.deepcopy(original)
    if s['complete']:return s
    q=fresh_quote(quote,now,s['isin']);at=market.get('dataAt');gold=market.get('price')
    healthy=positive(at) and positive(gold) and market.get('priceFresh') is True and 0<=now-at<=60000
    terminal_state=terminal(quote,s['isin'])
    guard=None
    if s.get('koGuardRequired') and healthy and q:
        guard_market={**market,'plan':{'unit':s.get('unit')}}
        guard,blocker=assess(s['product'],quote,guard_market,now)
        if blocker:healthy=False
    if not healthy or not q:
        if now-max(s.get('lastGoldAt',s['startedAt']),s['startedAt'])>90000:s['gap']=True
        if now>s['endsAt']+90000 or terminal_state:
            for v in s['variants'].values():
                if v['status']=='open':v.update(status='inconclusive',reason='Kursabdeckung oder Produktstatus unvollständig')
            s['complete']=True
        return s
    if at<=s['lastGoldAt']:return s
    qa=stamp(q['bidAt']);previous_q=stamp(s['lastQuoteAt'])
    if at-s['lastGoldAt']>90000 or not qa or not previous_q or qa<previous_q or qa<s['startedAt'] or qa-previous_q>90000 or abs(qa-at)>60000:s['gap']=True
    s.update(lastGoldAt=at,lastQuoteAt=q['bidAt'])
    sign=1 if s['direction']=='LONG' else -1
    for v in s['variants'].values():
        if v['status']!='open':continue
        reason=('product-ended' if terminal_state else 'ko-safety' if guard and guard['danger'] else 'stop' if sign*(gold-v['stop'])<=0 else 'target' if sign*(gold-s['target'])>=0 else 'time' if now>=s['endsAt'] else None)
        if not reason:continue
        v.update(status='inconclusive' if s['gap'] or terminal_state or (guard and guard['crossed']) else 'observed-'+reason,exitAt=qa,exitGoldAt=at,bid=q['bid'])
        if v['status']!='inconclusive':
            c=dict(status='closed',productReturnKnown=True,pendingUnits=0,remainingUnits=0,quantity=s['quantity'],
                allocated=s['quantity']*s['entryAsk'],cashReleased=s['quantity']*q['bid'],startedAt=s['startedAt'],closedAt=now,
                events=[dict(units=s['quantity'],quote=q)])
            costs=paper_costs.evaluate(c,s['costModel']);v.update(costs=costs,modelNetEur=costs['modelNetEur'] if costs else None)
    s['complete']=all(v['status']!='open' for v in s['variants'].values())
    return s

def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS bob_paper_stop_studies (id TEXT PRIMARY KEY,day TEXT NOT NULL,complete BOOLEAN NOT NULL,payload JSONB NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_paper_stop_studies_pending ON bob_paper_stop_studies(day) WHERE complete=FALSE')

def active_isins(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT payload->>'isin' FROM bob_paper_stop_studies WHERE complete=FALSE LIMIT 32").fetchall()]

def tick(conn,market,quotes,now):
    # Registration uses the setup frozen at actual entry, even if read a cycle later.
    rows=conn.execute('''SELECT c.payload FROM bob_paper_balanced_cases c
        WHERE c.payload->'stopStudySetup'->>'version'=%s
        AND NOT EXISTS(SELECT 1 FROM bob_paper_stop_studies s WHERE s.id=c.id)
        ORDER BY c.started_at DESC LIMIT 8''',(VERSION,)).fetchall()
    for (c,) in rows:
        s=create(c)
        if s:conn.execute('INSERT INTO bob_paper_stop_studies VALUES(%s,%s,FALSE,%s::jsonb) ON CONFLICT DO NOTHING',(s['id'],s['day'],json.dumps(s)))
    for key,s in conn.execute('SELECT id,payload FROM bob_paper_stop_studies WHERE complete=FALSE ORDER BY day,id LIMIT 32 FOR UPDATE SKIP LOCKED').fetchall():
        s=advance(s,market,quotes.get(s['isin']),now)
        conn.execute('UPDATE bob_paper_stop_studies SET complete=%s,payload=%s::jsonb WHERE id=%s',(s['complete'],json.dumps(s),key))
    # Preserve study cases and outcomes for reproducible historical evaluation.

def report(conn,day):
    rows=[r[0] for r in conn.execute('SELECT payload FROM bob_paper_stop_studies WHERE day=%s ORDER BY id LIMIT 100',(day,)).fetchall()]
    paired=[s for s in rows if all(v['status'].startswith('observed-') and type(v.get('modelNetEur')) in (int,float) for v in s['variants'].values())]
    return dict(version=VERSION,total=len(rows),paired=len(paired),open=sum(not s['complete'] for s in rows),
        unavailable=sum(s['complete'] and s not in paired for s in rows),limit=100,
        variants=[dict(key=k,label=label,paired=len(paired),modelNetEur=sum(s['variants'][k]['modelNetEur'] for s in paired) if paired else None,
                       stopHits=sum(s['variants'][k]['status']=='observed-stop' for s in paired)) for k,label in LABELS.items()],
        note=NOTE,status='collecting' if len(paired)<20 else 'research-only',promoted=False)
