"""Prospective, observed-quote paper cases; never a broker/order connection."""
import copy
import hashlib
import json
import math
import subprocess
import evaluator_runtime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import background_push
import stop_target_audit

VERSION = 'paper-lifecycle-v2'
START = datetime(2026, 10, 8, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000
NOTE = ('Vorwärts-Simulation ohne Orders. Eine Position, rund 50 % Teilgewinn am ersten Ziel; '
        'Rest folgt Bobs Gewinnschutz und Zielverlängerung. Stop wird niemals gelockert. '
        'Goldplan maximal vier Stunden, spätestens 21:45 Zürich. '
        'Nur beobachtete Kurse, keine Ausführung oder sichere Treffer zwischen Messungen. '
        'Produktvergleich: Einstieg Brief / Ausstieg Geld; Anbieterquotierung, kein DEGIRO-Ausführungsnachweis. '
        'Gebühren, Finanzierung, Slippage und Nettogewinn unbekannt. '
        'Fiktives Startkapital 100 EUR, über Tage weitergeführt; ganze Stückzahlen, kein Kredit. '
        'Teilgewinn rund 50 %, auf ganze Stücke abgerundet. Ein Stück wird am ersten Ziel ganz verkauft. '
        'Fehlt der Ausstiegskurs, bleibt Kapital unbewertet bis zum nächsten frischen Geldkurs; '
        'dieser spätere simulierte Verkauf wird separat protokolliert. '
        '30 Tage Falldetails; Tagesstatistik fortlaufend ohne festes Enddatum.')

def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0

def stamp(value):
    if finite(value): return value
    try:
        at=datetime.fromisoformat(value.replace('Z','+00:00'))
        return at.timestamp()*1000 if at.tzinfo else None
    except (TypeError,ValueError,AttributeError): return None

def fresh_quote(q, now, isin):
    if not isinstance(q,dict) or q.get('isin')!=isin or q.get('currency')!='EUR':return None
    if (q.get('found') is not True or q.get('marketOpen') is not True
            or q.get('priceKind') in ('calculated','issuer-chart') or q.get('isExecutableQuote') is False
            or not q.get('source') or not finite(q.get('bid')) or not finite(q.get('ask'))
            or q['ask']<q['bid']):return None
    times=[stamp(q.get(k) or q.get('quoteAt')) for k in ('bidAt','askAt')]
    if not all(at is not None and 0<=now-at<=90000 for at in times):return None
    return {k:q.get(k) for k in ('isin','bid','ask','currency','source','quoteAt','bidAt','askAt')}

def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_paper_control (
        id INTEGER PRIMARY KEY CHECK(id=1), payload JSONB NOT NULL)''')
    conn.execute('''INSERT INTO bob_paper_control VALUES(1,%s::jsonb) ON CONFLICT DO NOTHING''',
                 (json.dumps(dict(version=VERSION,startAt=START,enabled=True,status='scheduled')),))
    conn.execute('''UPDATE bob_paper_control SET payload=payload || %s::jsonb
        WHERE NOT (payload ? 'initialCapital')''',
        (json.dumps(dict(version=VERSION,initialCapital=100.,cash=100.,equity=100.,dayOpeningEquity=100.,dayProfit=0.,totalProfit=0.,realizedProfit=0.,currency='EUR',capitalPolicy='whole-units-gross-v1')),))
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_paper_products (
        id INTEGER PRIMARY KEY CHECK(id=1), payload JSONB NOT NULL, synced_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_paper_cases (
        id TEXT PRIMARY KEY, day TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL,
        closed_at TIMESTAMPTZ, payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_paper_day ON bob_paper_cases(day,started_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_paper_open ON bob_paper_cases(started_at) WHERE closed_at IS NULL')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_paper_days (
        day TEXT PRIMARY KEY, payload JSONB NOT NULL)''')

def sync(conn, payload):
    products=payload.get('products')
    if not isinstance(products,list) or not 0<len(products)<=12:raise ValueError('Produktliste ungültig')
    keys=('isin','name','productDirection','direction','isinConfirmed','price','leverage','ko','spread','spot',
          'quote','snapshot','type','currency','basisPrice','ratio','underlying','contract','maturity')
    def clean(value):
        if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()
                if not any(s in str(k).lower() for s in ('image','password','token','account','rawtext','ocrtext','dataurl'))}
        if isinstance(value,list):return [clean(v) for v in value[:30]]
        if isinstance(value,str):return value[:2000]
        return value
    safe=dict(products=[{k:clean(p[k]) for k in keys if k in p} for p in products if isinstance(p,dict)],
              references=clean(payload.get('references') or []),fixedBarriers=clean(payload.get('fixedBarriers') or {}))
    if not any(p.get('isin') for p in safe['products']):
        return dict(ok=True,products=0,preserved=True)
    text=json.dumps(safe,allow_nan=False)
    if len(text)>180000:raise ValueError('Produktnachweise zu groß')
    conn.execute('''INSERT INTO bob_paper_products(id,payload) VALUES(1,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload,synced_at=now()''',(text,))
    return dict(ok=True,products=len(safe['products']))

def new_case(market, choice, quote, now, cash=100.):
    p=copy.deepcopy(market['plan']);direction=p['direction'];risk=abs(p['entry']-p['stop'])
    local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'))
    end=min(now+4*3600000,local.replace(hour=21,minute=45,second=0,microsecond=0).timestamp()*1000)
    key=hashlib.sha256(json.dumps([VERSION,market.get('ruleVersion'),market.get('analysisBarAt'),direction,choice['isin']],sort_keys=True).encode()).hexdigest()
    # No currency model is guessed from a leverage number or future contract.
    q=None if choice.get('indicative') or choice.get('estimated') else fresh_quote(quote,now,choice['isin'])
    quantity=math.floor((cash+1e-9)/q['ask']) if q else None
    if quantity==0:raise ValueError('Kapital reicht nicht für ein Produktstück')
    t=dict(tradeId=key,dir=direction,entry=p['entry'],stop=p['stop'],target=p['target'],initialRisk=risk,instrument='XAU/USD',active=True,product=None)
    return dict(id=key,version=VERSION,status='open',day=local.date().isoformat(),startedAt=now,endsAt=end,
                plan=p,product=copy.deepcopy(choice),entryQuote=q,entryAsk=q['ask'] if q else None,
                analysis=copy.deepcopy(market),lastAt=market['dataAt'],remaining=1.,goldR=0.,productGrossPct=0. if q else None,
                productReturnKnown=bool(q),netReturnKnown=False,modelOnly=True,partialTaken=False,
                quantity=quantity,remainingUnits=quantity,pendingUnits=0,cashReleased=0.,bookedUnits=0,
                allocated=quantity*q['ask'] if quantity else None,availableAtEntry=cash,
                capitalMode='EUR-Ganzstück-Bruttomodell' if quantity else 'Goldplan ohne Europosition',
                engine=dict(trade=t),events=[dict(kind='entry',at=market['dataAt'],recordedAt=now,gold=market['price'],quote=q,
                    reason=market.get('decisionReason'),ruleVersion=market.get('ruleVersion'))])

def advance_case(original, market, quote, now):
    """Stop checks precede trailing; resumed gaps cannot manufacture a win."""
    c=copy.deepcopy(original)
    def event(kind,**extra):c['events'].append(dict(kind=kind,at=market.get('dataAt'),recordedAt=now,**extra))
    q=fresh_quote(quote,now,c['product']['isin']) if c.get('quantity') else None
    if c.get('pendingUnits') and q and stamp(q.get('bidAt') or q.get('quoteAt'))>=c['pendingSince']:
        units=c['pendingUnits'];c['cashReleased']+=units*q['bid'];c['bookedUnits']+=units;c['pendingUnits']=0
        event('deferred-sale',units=units,quote=q,reason='Späterer Modellverkauf zum ersten verfügbaren frischen Geldkurs; kein rückdatierter Ausstieg')
        if not c.get('remainingUnits'):
            c.update(productReturnKnown=True,productGrossPct=(c['cashReleased']/c['allocated']-1)*100,settledAt=now)
    if c['status']!='open':return c
    def defer_remaining():
        if c.get('remainingUnits'):
            c['pendingUnits']+=c['remainingUnits'];c['remainingUnits']=0;c['remaining']=0.
            c['pendingSince']=now
    at=market.get('dataAt');last=c['lastAt']
    if not finite(at) or not 0<=now-at<=60000 or not market.get('priceFresh') or not finite(market.get('price')):
        if now-last>90000:
            c.update(status='inconclusive',closedAt=now,productReturnKnown=False,productGrossPct=None)
            defer_remaining()
            event('data-gap',reason='Aktuelle Goldkursabdeckung fehlt; kein belegter Ausstieg')
        return c
    if at<=last:return c
    if at-last>90000:
        c.update(status='inconclusive',closedAt=now,productReturnKnown=False,productGrossPct=None)
        defer_remaining()
        event('data-gap',reason='Goldkurslücke über 90 Sekunden; Reihenfolge unbekannt')
        return c
    c['lastAt']=at;p=market['price'];t=c['engine']['trade'];long=t['dir']=='LONG'
    sign=1 if long else -1
    def realize(kind,weight):
        q=fresh_quote(quote,now,c['product']['isin']) if c['entryQuote'] else None
        units=None
        if c.get('quantity'):
            units=min(c['remainingUnits'],round(c['quantity']*weight))
            weight=units/c['quantity'];c['remainingUnits']-=units
            if q:c['cashReleased']+=units*q['bid'];c['bookedUnits']+=units
            else:c['pendingUnits']+=units;c['pendingSince']=now
        c['goldR']+=sign*(p-t['entry'])/t['initialRisk']*weight
        if q and c['productGrossPct'] is not None:c['productGrossPct']+=(q['bid']/c['entryAsk']-1)*100*weight
        else:c.update(productGrossPct=None,productReturnKnown=False)
        c['remaining']=max(0,c['remaining']-weight)
        event(kind,gold=p,weight=weight,units=units,quote=q,stop=t['stop'],target=t['target'])
        if c['remaining']<1e-9:
            c.update(status='closed',closedAt=now,exitReason=kind)
            if c.get('quantity') and not c.get('pendingUnits'):
                c.update(productReturnKnown=True,productGrossPct=(c['cashReleased']/c['allocated']-1)*100)
    stopped=p<=t['stop'] if long else p>=t['stop']
    if stopped:
        realize('stop',c['remaining']);return c
    if now>=c['endsAt']:
        realize('time-exit',c['remaining']);return c
    trend=market.get('trendContext') or {}
    trend_intact=market.get('ready') and trend.get('available') is True and trend.get('intact') is True and trend.get('direction')==t['dir']
    if not trend_intact and market.get('ready') and market.get('direction') in ('LONG','SHORT') and market['direction']!=t['dir']:
        realize('reversal-exit',c['remaining']);return c
    target_hit=p>=t['target'] if long else p<=t['target']
    if target_hit and not c['partialTaken']:
        weight=max(1,c['quantity']//2)/c['quantity'] if c.get('quantity') else .5
        realize('partial-profit',weight);c['partialTaken']=True
        if c['status']=='closed':return c
    before=copy.deepcopy(t)
    settings=dict(timeframe='15m',trailAtr=1.5,trade={**t,'stop':c['plan']['stop'],'target':c['plan']['target']})
    engine,alerts=background_push.advance(c['engine'],settings,market,False,True,now=now,log=False)
    c['engine']=engine;t=engine['trade']
    if t['stop']!=before['stop']:event('stop-raised',old=before['stop'],new=t['stop'],gold=p,reason='Bobs Gewinnschutz / technischer Stop')
    if t.get('target')!=before.get('target'):event('target-extended',old=before.get('target'),new=t['target'],gold=p,ruleVersion=market.get('ruleVersion'))
    if target_hit and not trend_intact and t.get('target')==before.get('target'):
        realize('target-exit',c['remaining'])
    elif market.get('ready') and any(e['data']['eventKind']=='profit-weak' for e in alerts):
        realize('profit-taking',c['remaining'])
    return c

def capital_snapshot(control,case,quote,now):
    units=(case.get('remainingUnits') or 0)+(case.get('pendingUnits') or 0) if case else 0
    q=fresh_quote(quote,now,case['product']['isin']) if units else None
    control.update(equity=control['cash']+units*q['bid'] if q else None if units else control['cash'],
                   openUnits=units,capitalAt=now,valuationKnown=not units or bool(q))
    control['dayProfit']=control['equity']-control['dayOpeningEquity'] if control.get('equity') is not None and control.get('dayOpeningEquity') is not None else None
    control['totalProfit']=control['equity']-control['initialCapital'] if control.get('equity') is not None else None

def day_update(conn, day, closed=None, wait=None, now=None,capital=None,product=None):
    row=conn.execute('SELECT payload FROM bob_paper_days WHERE day=%s',(day,)).fetchone()
    d=row[0] if row else dict(cases=0,closed=0,inconclusive=0,goldPositive=0,goldNegative=0,goldFlat=0,
                             productKnown=0,productPositive=0,productNegative=0,waitChecks=0)
    d.update(lastCheckedAt=now)
    if capital:
        d.update(openingCapital=capital.get('dayOpeningEquity'),capital=capital.get('equity'),cash=capital['cash'],
                 dayProfit=capital.get('dayProfit'),totalProfit=capital.get('totalProfit'),openUnits=capital.get('openUnits',0),
                 capitalAt=now,valuationKnown=capital.get('valuationKnown',True),initialCapital=capital['initialCapital'])
        d.update(realizedProfit=capital.get('realizedProfit',0),dayRealizedProfit=capital.get('realizedProfit',0)-capital.get('dayOpeningRealized',0))
    if wait:d.update(waitChecks=d['waitChecks']+1,lastWait=wait)
    if closed:
        d['cases']+=1
        if closed['status']=='closed':
            d['closed']+=1
            value=closed['goldR'];d['goldPositive' if value>0 else 'goldNegative' if value<0 else 'goldFlat']+=1
        else:d['inconclusive']+=1
    product=product or closed
    if product and product['productReturnKnown']:
        d['productKnown']+=1;d['productPositive' if product['productGrossPct']>0 else 'productNegative']+=1
    conn.execute('''INSERT INTO bob_paper_days VALUES(%s,%s::jsonb)
        ON CONFLICT(day) DO UPDATE SET payload=EXCLUDED.payload''',(day,json.dumps(d)))

def report(conn, day=None):
    control=conn.execute('SELECT payload FROM bob_paper_control WHERE id=1').fetchone()[0]
    feed=conn.execute('SELECT payload,synced_at FROM bob_paper_products WHERE id=1').fetchone()
    day=day or datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()
    datetime.strptime(day,'%Y-%m-%d')
    cases=conn.execute('SELECT payload FROM bob_paper_cases WHERE day=%s ORDER BY started_at DESC LIMIT 100',(day,)).fetchall()
    stats=conn.execute('SELECT payload FROM bob_paper_days WHERE day=%s',(day,)).fetchone()
    totals=conn.execute('SELECT day,payload FROM bob_paper_days ORDER BY day DESC LIMIT 366').fetchall()
    return dict(ok=True,version=VERSION,note=NOTE,control=control,day=day,stats=stats[0] if stats else {},
                products=[dict(isin=p.get('isin'),direction=p.get('productDirection'),name=p.get('name')) for p in feed[0]['products'] if p.get('isin')] if feed else [],
                productSyncedAt=feed[1].isoformat() if feed else None,cases=[r[0] for r in cases],
                daily=[dict(day=d,**s) for d,s in totals],detailsLimit=100,detailRetentionDays=30,
                demonstration=technical_demo(control.get('lastGold'),next((p for p in feed[0]['products'] if p.get('productDirection')=='LONG'),None) if feed else None))

def technical_demo(reference=None, product=None):
    """Artificial future path, never inserted into observed-case statistics."""
    base=reference if finite(reference) else 4100.
    now=datetime(2026,10,8,9,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000
    risk=base*.002
    market=dict(plan=dict(kind='candidate',direction='LONG',entry=base,stop=base-risk,target=base+2*risk,unit='USD/oz'),
        price=base,priceFresh=True,ready=True,dataAt=now,analysisBarAt=now,ruleVersion='artificial-mechanics-demo',
        direction='LONG',mtf='LONG',score=80,macd=2,signal=1,atr=risk,decisionReason='Künstlicher LONG-Probelauf; kein reales Bob-Signal')
    choice=dict(isin=product['isin'] if product else 'kein Produkt synchronisiert',name=product.get('name') if product else None,
                indicative=True,approval='Mechaniktest, kein Produktkurs und keine Freigabe')
    c=new_case(market,choice,None,now)
    for i,multiple in enumerate((.5,1.,2.,2.5,.9),1):
        at=now+i*30000;p=base+multiple*risk
        tick={**market,'price':p,'dataAt':at,'analysisBarAt':now+i*300000,
              'suggestedStop':p-risk*1.5,'suggestedTarget':p+risk*2}
        c=advance_case(c,tick,None,at)
    c.update(demonstration=True,referenceIsObserved=finite(reference),referenceGold=base,
             note='Künstliche Folgekursfolge zur Funktionsprüfung. Kein historischer Marktfall, keine Renditewertung, keine echte Produktauswahl.')
    return c

def run_once(conn,bundle,market,selection,quotes,now):
    row=conn.execute('SELECT payload FROM bob_paper_control WHERE id=1 FOR UPDATE').fetchone()
    control=row[0]
    control.setdefault('initialCapital',100.);control.setdefault('cash',100.);control.setdefault('equity',100.);control.setdefault('realizedProfit',0.)
    local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'));day=local.date().isoformat()
    if control.get('ledgerDay')!=day:
        control.update(ledgerDay=day,dayOpeningEquity=control.get('equity'),dayOpeningRealized=control['realizedProfit'])
    control.update(checkedAt=now,ruleVersion=market.get('ruleVersion'),lastDirection=market.get('direction','NEUTRAL'),lastGold=market.get('price'),goldAt=market.get('dataAt'))
    if now<control['startAt']:
        control.update(status='scheduled',reason='Start am 8.10.2026, danach fortlaufend')
    elif not control.get('enabled'):
        control.update(status='paused',reason='Simulation pausiert')
    else:
        active=conn.execute('SELECT id,payload FROM bob_paper_cases WHERE closed_at IS NULL ORDER BY started_at LIMIT 1 FOR UPDATE').fetchone()
        if active:
            key,c=active;released=c.get('cashReleased',0);booked=c.get('bookedUnits',0);q=quotes.get(c['product']['isin'])
            c=advance_case(c,market,q,now)
            control['cash']+=c.get('cashReleased',0)-released
            control['realizedProfit']+=c.get('cashReleased',0)-released-(c.get('bookedUnits',0)-booked)*(c.get('entryAsk') or 0)
            capital_snapshot(control,c,q,now)
            if c['status']!='open' and not c.get('counted'):
                day_update(conn,c['day'],closed=c,now=now);c['counted']=True;c['productCounted']=c['productReturnKnown']
            elif c['status']!='open' and c['productReturnKnown'] and not c.get('productCounted'):
                day_update(conn,c['day'],product=c,now=now);c['productCounted']=True
            finished=c['status']!='open' and not c.get('pendingUnits')
            conn.execute('UPDATE bob_paper_cases SET payload=%s::jsonb,closed_at=to_timestamp(%s) WHERE id=%s',
                         (json.dumps(c),(c.get('settledAt') or c.get('closedAt'))/1000 if finished else None,key))
            control.update(status='running',reason='Simulationsfall '+c['status']+(' · Euroverkauf wartet auf Kurs' if c.get('pendingUnits') else ''),activeCase=None if finished else key)
            day_update(conn,day,now=now,capital=control)
        else:
            capital_snapshot(control,None,None,now)
            plan=market.get('plan');choice=next(iter(selection.get('choices') or []),None)
            q=fresh_quote(quotes.get(choice['isin']),now,choice['isin']) if choice and not choice.get('indicative') and not choice.get('estimated') else None
            healthy=market.get('ready') is True and market.get('priceFresh') is True and finite(market.get('dataAt')) and 0<=now-market['dataAt']<=60000
            entry_key=str([market.get('ruleVersion'),market.get('analysisBarAt'),market.get('direction')])
            if not healthy:
                if not market.get('priceFresh') or not finite(market.get('dataAt')) or not 0<=now-market['dataAt']<=60000:
                    reason='Goldkurs nicht aktuell bestätigt; Quellenzeit prüfen'
                else:
                    details=market.get('analysisWarnings') or [market.get('decisionReason') or 'Analysedaten noch unvollständig']
                    reason='Marktanalyse wartet: '+'; '.join(str(v) for v in details)
            elif not (market.get('session') or {}).get('entryAllowed'):reason='Außerhalb von Bobs Einstiegszeit'
            elif not stop_target_audit.valid_plan(plan):reason='ABWARTEN: kein bestätigter gültiger Goldplan'
            elif not choice:reason='Kein passendes belegtes Produkt: '+'; '.join(selection.get('reasons') or ['Produktliste noch nicht synchronisiert'])
            elif q and q['ask']>control['cash']:reason='Fiktives Kapital reicht nicht für ein ganzes Produktstück'
            elif control.get('lastEntryKey')==entry_key:reason='Diese Signal-Kerze wurde bereits simuliert'
            else:
                c=new_case(market,choice,quotes.get(choice['isin']),now,cash=control['cash'])
                inserted=conn.execute('''INSERT INTO bob_paper_cases(id,day,started_at,payload)
                    VALUES(%s,%s,to_timestamp(%s),%s::jsonb) ON CONFLICT DO NOTHING RETURNING id''',
                    (c['id'],day,now/1000,json.dumps(c))).fetchone()
                control.update(lastEntryKey=entry_key,activeCase=c['id'] if inserted else None)
                if inserted:
                    control['cash']-=c.get('allocated') or 0
                    capital_snapshot(control,c,quotes.get(choice['isin']),now)
                reason='Neuer Simulationsfall gespeichert' if inserted else 'Signal bereits dokumentiert'
            control.update(status='running',reason=reason)
            day_update(conn,day,wait=reason,now=now,capital=control)
        conn.execute("DELETE FROM bob_paper_cases WHERE closed_at < now()-interval '30 days'")
    conn.execute('UPDATE bob_paper_control SET payload=%s::jsonb WHERE id=1',(json.dumps(control),))

# Independent bounded worker: product network calls never delay /background or Push.
_guard=threading.Lock();_latest=None;_thread=None
_pool=None;_pending={};_quotes={};_requested={}
def quote_cache(products, active, now):
    global _pool
    if _pool is None:_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='bob-paper-quotes')
    for isin,future in list(_pending.items()):
        if not future.done():continue
        try:_quotes[isin]=future.result()
        except Exception as exc:print('BOB_PAPER quote_failed='+type(exc).__name__,flush=True)
        del _pending[isin]
    isins=list(dict.fromkeys(([active] if active else [])+[p.get('isin') for p in products if p.get('isin')]))
    from product_quotes import get_quote
    for isin in isins:
        if len(_pending)>=4:break
        if isin not in _pending and now-_requested.get(isin,0)>=60000:
            _requested[isin]=now;_pending[isin]=_pool.submit(get_quote,isin)
    by_isin={p['isin']:p.get('quote') for p in products if p.get('isin')}
    return {isin:_quotes.get(isin,by_isin.get(isin)) for isin in isins}

def _worker(db):
    while True:
        began=time.monotonic()
        with _guard:bundle=_latest
        if bundle:
            try:
                with db() as conn:
                    if conn.execute('SELECT pg_try_advisory_xact_lock(72610408)').fetchone()[0]:
                        feed=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
                        if feed and not any(p.get('isin') for p in feed[0]['products']):feed=None
                        if not feed:
                            legacy=conn.execute('''SELECT selection_evidence FROM subscriptions WHERE selection_evidence IS NOT NULL
                                AND EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(selection_evidence->'products','[]'::jsonb)) AS product
                                            WHERE COALESCE(product->>'isin','') <> '')
                                ORDER BY updated_at DESC LIMIT 1''').fetchone()
                            if legacy and any(p.get('isin') for p in legacy[0].get('products',[]) if isinstance(p,dict)):
                                sync(conn,legacy[0]);feed=(legacy[0],)
                        if not feed:
                            # Identified by the user's October 7 DEGIRO/BNP screenshots;
                            # all mutable values still need the live quote/term pipeline.
                            known=dict(products=[dict(isin='DE000PJ9NCK0',name='GOLD Unlimited Long',productDirection='LONG',isinConfirmed=True)])
                            sync(conn,known);feed=(known,)
                        evidence=feed[0]
                        active=conn.execute('SELECT payload FROM bob_paper_cases WHERE closed_at IS NULL LIMIT 1').fetchone()
                        now=time.time()*1000
                        settings=dict(timeframe='15m',trailAtr=1.5)
                        if active:settings['trade']=active[0]['engine']['trade']
                        quotes=quote_cache(evidence['products'],active[0]['product']['isin'] if active else None,now)
                        # A closed browser is not needed: exact same headless rules.
                        market=background_push.analyze(bundle,settings,priority=2)
                        selection=dict(choices=[],reasons=[])
                        if not active and market.get('ready') and market.get('direction') in ('LONG','SHORT'):
                            request={**evidence,'quotes':quotes,'market':market,'bundle':bundle}
                            p=evaluator_runtime.run(['node',str(Path(__file__).with_name('paper_selection.js'))],input=json.dumps(request),
                                             text=True,capture_output=True,timeout=6,check=True,priority=2)
                            selection=json.loads(p.stdout)
                        run_once(conn,bundle,market,selection,quotes,time.time()*1000)
                        conn.commit()
                        print('BOB_PAPER checked direction='+str(market.get('direction'))+' ready='+str(market.get('ready'))+' priceFresh='+str(market.get('priceFresh'))+' reason='+str(market.get('analysisWarnings') or market.get('decisionReason')),flush=True)
            except Exception as exc:print('BOB_PAPER error='+type(exc).__name__,flush=True)
        time.sleep(max(1,30-(time.monotonic()-began)))

def enqueue(bundle, db):
    global _latest,_thread
    with _guard:
        _latest=bundle
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_worker,args=(db,),daemon=True,name='bob-paper-simulation');_thread.start()
