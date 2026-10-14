"""Prospective, observed-quote paper cases; never a broker/order connection."""
import copy
import hashlib
import json
import rule_learning
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
import paper_ko_guard

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
        'Bei automatisch ausgewählten Produkten: verifizierter KO-Puffer, beobachteter fiktiver Sicherheitsausstieg; '
        'kein garantierter Stop oder Kurs. Bei bestätigtem Produktende ohne Abrechnungskurs bleibt das Ergebnis offen. '
        '30 Tage Falldetails; Tagesstatistik fortlaufend ohne festes Enddatum.')

def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0

def stamp(value):
    if finite(value): return value
    try:
        at=datetime.fromisoformat(value.replace('Z','+00:00'))
        return at.timestamp()*1000 if at.tzinfo else None
    except (TypeError,ValueError,AttributeError): return None

def quote_block_reason(q, now, isin):
    if not isinstance(q,dict):return 'Noch keine Kursantwort vorhanden'
    if q.get('isin')!=isin:return 'ISIN der Kursantwort stimmt nicht überein'
    if q.get('priceKind') in ('calculated','issuer-chart') or q.get('isExecutableQuote') is False:
        return 'Nur Chart-, Rechen- oder Recherchekurs; kein bestätigter zweiseitiger Handelskurs'
    if q.get('found') is not True:
        code=q.get('quoteFailureCode') or q.get('sourceFailureCode')
        return 'Anbieter liefert keinen bestätigten Handelskurs'+(' ('+str(code)+')' if code else '')
    if q.get('currency')!='EUR':return 'Handelskurs nicht in EUR bestätigt'
    if q.get('marketOpen') is not True:return 'Handelbarkeit beim Kursanbieter nicht bestätigt'
    if not q.get('source'):return 'Kursquelle fehlt'
    if not finite(q.get('bid')) or not finite(q.get('ask')):return 'Geld- oder Briefkurs fehlt'
    if q['ask']<q['bid']:return 'Widersprüchlicher Geld-/Briefkurs'
    times=[stamp(q.get(k) or q.get('quoteAt')) for k in ('bidAt','askAt')]
    if any(at is None for at in times):return 'Quellzeit für Geld-/Briefkurs fehlt'
    if any(at>now for at in times):return 'Kurszeit liegt in der Zukunft'
    if any(now-at>90000 for at in times):return 'Geld-/Briefkurs älter als 90 Sekunden'
    return None


def fresh_quote(q, now, isin):
    if quote_block_reason(q,now,isin):return None
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
    import paper_portfolios
    paper_portfolios.init(conn)

def sync(conn, payload):
    products=payload.get('products')
    if not isinstance(products,list) or not 0<len(products)<=12:raise ValueError('Produktliste ungültig')
    if not any(isinstance(p,dict) and p.get('isin') for p in products):
        return dict(ok=True,products=0,preserved=True)
    # The screenshot upload timestamp tracks the active list generation.
    # It must NEVER count as a quote/KO source timestamp.
    uploaded=payload.get('listUploadedAt')
    generation=None
    if uploaded is not None:
        if not isinstance(uploaded,str):
            raise ValueError('Ungültiger Screenshot-Listenstand')
        try:
            generation=datetime.fromisoformat(uploaded.replace('Z','+00:00'))
        except ValueError as exc:
            raise ValueError('Ungültiger Screenshot-Listenstand') from exc
        if generation.tzinfo is None or generation.timestamp()>time.time()+120:
            raise ValueError('Ungültiger zukünftiger Screenshot-Listenstand')
        if payload.get('origin')!='degiro-screenshot':
            raise ValueError('Screenshot-Quellenzuordnung fehlt')
    # Serialize competing tabs/devices. An old tab must not restore an earlier
    # product set after a newer screenshot replaced it.
    old=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1 FOR UPDATE').fetchone()
    previous=old[0] if isinstance(old,(tuple,list)) and old and isinstance(old[0],dict) else {}
    old_time=stamp(previous.get('listUploadedAt'))
    new_time=generation.timestamp()*1000 if generation else None
    if old_time is not None and (new_time is None or new_time<old_time):
        return dict(ok=True,products=len(previous.get('products') or []),
                    preserved=True, reason='Älterer Screenshot-Stand; neuere Produktliste bleibt aktiv')
    if old_time is not None and new_time==old_time:
        expected={p.get('isin') for p in previous.get('products') or [] if isinstance(p,dict)}
        current={p.get('isin') for p in products if isinstance(p,dict) and p.get('isin')}
        if expected!=current:
            return dict(ok=True,products=len(previous.get('products') or []),
                        preserved=True, reason='Dieselbe Upload-Version enthält widersprüchliche ISINs')
    keys=('isin','name','productDirection','direction','isinConfirmed','price','leverage','ko','spread','spot',
          'quote','snapshot','type','currency','basisPrice','ratio','underlying','contract','maturity')
    def clean(value):
        if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()
                if not any(s in str(k).lower() for s in ('image','password','token','account','rawtext','ocrtext','dataurl'))}
        if isinstance(value,list):return [clean(v) for v in value[:30]]
        if isinstance(value,str):return value[:2000]
        return value
    safe=dict(products=[{k:clean(p[k]) for k in keys if k in p} for p in products if isinstance(p,dict)],
              references=clean(payload.get('references') or []),fixedBarriers=clean(payload.get('fixedBarriers') or {}),
              listUploadedAt=uploaded if generation else None,
              listOrigin='degiro-screenshot' if generation else 'legacy')
    if not any(p.get('isin') for p in safe['products']):
        return dict(ok=True,products=0,preserved=True)
    text=json.dumps(safe,allow_nan=False)
    if len(text)>180000:raise ValueError('Produktnachweise zu groß')
    conn.execute('''INSERT INTO bob_paper_products(id,payload) VALUES(1,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload,synced_at=now()''',(text,))
    if new_time is not None and (old_time is None or new_time > old_time):
        # Previously approved product-Push candidates belong to the old list.
        # Clear just their selection evidence; leave active trade/stop monitors,
        # trade journals and independent market alerts untouched.
        conn.execute('''UPDATE subscriptions SET selection_evidence=NULL, product_selection=NULL
            WHERE selection_evidence IS NOT NULL OR product_selection IS NOT NULL''')
    return dict(ok=True,products=len(safe['products']),listUploadedAt=uploaded)

def new_case(market, choice, quote, now, cash=100.):
    p=copy.deepcopy(market['plan']);direction=p['direction'];risk=abs(p['entry']-p['stop'])
    local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'))
    end=min(now+4*3600000,local.replace(hour=21,minute=45,second=0,microsecond=0).timestamp()*1000)
    key=hashlib.sha256(json.dumps([VERSION,market.get('ruleVersion'),market.get('learningPolicy'),market.get('analysisBarAt'),direction,choice['isin']],sort_keys=True).encode()).hexdigest()
    # No currency model is guessed from a leverage number or future contract.
    q=None if choice.get('indicative') or choice.get('estimated') else fresh_quote(quote,now,choice['isin'])
    quantity=math.floor((cash+1e-9)/q['ask']) if q else None
    if quantity==0:raise ValueError('Kapital reicht nicht für ein Produktstück')
    t=dict(tradeId=key,dir=direction,entry=p['entry'],stop=p['stop'],target=p['target'],initialRisk=risk,instrument='XAU/USD',active=True,product=None)
    return dict(id=key,version=VERSION,status='open',day=local.date().isoformat(),startedAt=now,endsAt=end,
                plan=p,product=copy.deepcopy(choice),koGuardRequired=choice.get('koGuardRequired') is True,
                entryQuote=q,entryAsk=q['ask'] if q else None,
                analysis=copy.deepcopy(market),lastAt=market['dataAt'],remaining=1.,goldR=0.,productGrossPct=0. if q else None,
                productReturnKnown=bool(q),netReturnKnown=False,modelOnly=True,partialTaken=False,
                quantity=quantity,remainingUnits=quantity,pendingUnits=0,cashReleased=0.,bookedUnits=0,
                allocated=quantity*q['ask'] if quantity else None,availableAtEntry=cash,
                entrySpreadEur=round(quantity*(q['ask']-q['bid']),8) if quantity else None,
                entrySpreadPct=round((q['ask']/q['bid']-1)*100,4) if quantity else None,
                capitalMode='EUR-Ganzstück-Bruttomodell' if quantity else 'Goldplan ohne Europosition',
                engine=dict(trade=t),events=[dict(kind='entry',at=market['dataAt'],recordedAt=now,gold=market['price'],quote=q,
                    reason=market.get('decisionReason'),ruleVersion=market.get('ruleVersion'),learningPolicy=market.get('learningPolicy'))])

def advance_case(original, market, quote, now):
    """Stop checks precede trailing; resumed gaps cannot manufacture a win."""
    c=copy.deepcopy(original)
    def event(kind,**extra):c['events'].append(dict(kind=kind,at=market.get('dataAt'),recordedAt=now,**extra))
    q=fresh_quote(quote,now,c['product']['isin']) if c.get('quantity') else None
    if (c.get('pendingUnits') and q and
            c.get('koWatchStatus') not in ('knockout-confirmed','product-terminated') and
            stamp(q.get('bidAt') or q.get('quoteAt'))>=c['pendingSince']):
        units=c['pendingUnits'];c['cashReleased']+=units*q['bid'];c['bookedUnits']+=units;c['pendingUnits']=0
        event('deferred-sale',units=units,quote=q,reason='Späterer Modellverkauf zum ersten verfügbaren frischen Geldkurs; kein rückdatierter Ausstieg')
        if not c.get('remainingUnits'):
            c.update(productReturnKnown=True,productGrossPct=(c['cashReleased']/c['allocated']-1)*100,settledAt=now)
    if c['status']!='open':return c
    def defer_remaining():
        if c.get('remainingUnits'):
            c['pendingUnits']+=c['remainingUnits'];c['remainingUnits']=0;c['remaining']=0.
            c['pendingSince']=now
    terminal_status = paper_ko_guard.terminal(quote, c['product']['isin'])
    if terminal_status:
        # Provider-confirmed terminal status is not a known executable price
        # or a proven zero recovery. Keep unpriced units pending.
        c.update(status='inconclusive',closedAt=now,
                 productReturnKnown=False,productGrossPct=None,
                 koWatchStatus=terminal_status)
        defer_remaining()
        event(terminal_status,reason='Emittent meldet Produktende; Abrechnungswert unbekannt, kein erfundener Verkauf')
        return c
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
    if c.get('koGuardRequired'):
        ko_state, ko_error = (paper_ko_guard.assess(c['product'], quote, market, now)
                              if q else (None, 'Kein frischer bestätigter Euro-Produktkurs'))
        if ko_state:
            c['koWatch']=ko_state
            c['koWatchStatus']='confirmed'
            if ko_state['crossed']:
                # An issuer KO is NOT certified by a spot crossing alone.
                # Equally, a bid sampled near that crossing cannot establish
                # that an exit was available before the barrier was struck.
                c.update(status='inconclusive',closedAt=now,
                         productReturnKnown=False,productGrossPct=None,
                         koWatchStatus='crossed-observed')
                defer_remaining()
                event('ko-barrier-crossed-observed',barrierUsd=ko_state['barrierUsd'],
                      reason='Barriere im Goldkurs überschritten; Produktstatus und Abrechnungswert ungeklärt')
                return c
            if ko_state['danger']:
                # Only a pre-barrier risk warning and a fresh bid may create
                # an observed virtual exit. No fill or loss limit guaranteed.
                c['koWatchStatus']='proximity-exit'
                realize('ko-safety-exit',c['remaining'])
                return c
        else:
            c['koWatchStatus']='unverified'
            c['koWatchReason']=ko_error
            # Missing terms never become an invented issuer event or fill.
    stopped=p<=t['stop'] if long else p>=t['stop']
    if stopped:
        realize('stop',c['remaining']);return c
    if now>=c['endsAt']:
        realize('time-exit',c['remaining']);return c
    if c.get('trendFollow') is True:
        # Separate trend lifecycle: no automatic sale at first profit target;
        # original stop, source-freshness and gap protection above stay intact.
        import trend_follow
        trend_follow.step(c,market,p,t,event,realize)
        return c
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
    """Equity and drawdown use observed, fresh EUR bids; gaps stay unknown."""
    units=((case.get('remainingUnits') or 0)+(case.get('pendingUnits') or 0)) if case else 0
    q=fresh_quote(quote,now,case['product']['isin']) if units else None
    equity=(control['cash']+units*q['bid']) if q else (None if units else control['cash'])
    control.update(equity=equity,openUnits=units,capitalAt=now,
                   valuationKnown=equity is not None)
    if units:
        counter='quoteConfirmedChecks' if q else 'quoteMissingChecks'
        control[counter]=control.get(counter,0)+1
        control['quoteStatus']='confirmed' if q else 'missing-or-stale'
        if q:
            control['lastConfirmedQuoteAt']=q.get('bidAt') or q.get('quoteAt')
            control['lastConfirmedQuoteSource']=q.get('source')
    else:
        control['quoteStatus']='no-open-units'
    if equity is not None:
        peak=control.get('peakEquity')
        if not finite(peak):peak=control.get('initialCapital')
        if not finite(peak):peak=equity
        peak=max(peak,equity)
        control['peakEquity']=peak
        dd=max(0.,(peak-equity)/peak*100) if peak>0 else 0.
        control['currentDrawdownPct']=dd
        control['maxDrawdownPct']=max(control.get('maxDrawdownPct') or 0.,dd)
    else:
        control['currentDrawdownPct']=None
    control['dayProfit']=(equity-control['dayOpeningEquity']
                          if equity is not None and control.get('dayOpeningEquity') is not None
                          else None)
    control['totalProfit']=equity-control['initialCapital'] if equity is not None else None

def day_update(conn, day, closed=None, wait=None, now=None,capital=None,product=None):
    row=conn.execute('SELECT payload FROM bob_paper_days WHERE day=%s',(day,)).fetchone()
    d=row[0] if row else dict(cases=0,closed=0,inconclusive=0,goldPositive=0,goldNegative=0,goldFlat=0,
                             productKnown=0,productPositive=0,productNegative=0,waitChecks=0)
    d.update(lastCheckedAt=now)
    if capital:
        d.update(openingCapital=capital.get('dayOpeningEquity'),capital=capital.get('equity'),cash=capital['cash'],
                 dayProfit=capital.get('dayProfit'),totalProfit=capital.get('totalProfit'),openUnits=capital.get('openUnits',0),
                 capitalAt=now,valuationKnown=capital.get('valuationKnown',True),initialCapital=capital['initialCapital'],
                  observedMaxDrawdownPct=capital.get('maxDrawdownPct'),
                  quoteMissingChecksSinceStart=capital.get('quoteMissingChecks',0),
                  quoteConfirmedChecksSinceStart=capital.get('quoteConfirmedChecks',0))
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
    phase = background_push.degiro_session()
    closed = phase == 'weekend'
    status = dict(control)
    if phase != 'trading' and status.get('enabled') and time.time()*1000 >= status.get('startAt', START):
        status.update(status='market-closed' if closed else 'night-paused' if phase=='night' else 'preparing',
                      reason='Goldmarkt geschlossen · Simulation pausiert' if closed
                             else 'DEGIRO-Nachtmodus · Simulation pausiert, gespeichert und geschützt' if phase=='night'
                             else 'Vorbereitung ab 07:30 Uhr · Simulation startet ab 08:00 Uhr')
    return dict(ok=True,version=VERSION,note=NOTE,control=status,marketClosed=closed,sessionMode=phase,day=day,stats=stats[0] if stats else {},
                products=[dict(isin=p.get('isin'),direction=p.get('productDirection'),name=p.get('name')) for p in feed[0]['products'] if p.get('isin')] if feed else [],
                productSyncedAt=feed[1].isoformat() if feed else None,cases=[r[0] for r in cases],
                daily=[dict(day=d,**s) for d,s in totals],detailsLimit=100,detailRetentionDays=30,
                demonstrations=technical_scenarios(), demonstration=technical_demo(control.get('lastGold'),next((p for p in feed[0]['products'] if p.get('productDirection')=='LONG'),None) if feed else None))

def technical_scenarios():
    """Isolated deterministic checks; never persist cases or dispatch alerts."""
    results=[]
    for name, direction, mode in [('LONG: Stop und Ziel','LONG','path'),('SHORT: Stop und Ziel','SHORT','path'),('Rücksetzer: Position halten','LONG','hold'),('Gegenrichtung: Ausstieg','LONG','reverse'),('Momentum schwächer: Gewinnmitnahme','LONG','weak'),('Datenlücke: keine Ergebnisfreigabe','LONG','gap')]:
        now=datetime(2026,10,8,9,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000
        sign=1 if direction=='LONG' else -1
        m=dict(plan=dict(kind='candidate',direction=direction,entry=4100.,stop=4100.-sign*10,target=4100.+sign*20,unit='USD/oz'),price=4100.,priceFresh=True,ready=True,dataAt=now,analysisBarAt=now,ruleVersion='artificial-active-trade-v1',direction=direction,mtf=direction,score=80 if sign==1 else 20,macd=2*sign,signal=sign,atr=10.,decisionReason=name)
        c=new_case(m,dict(isin='TEST',indicative=True,approval='Künstlicher Goldplan ohne Produktkauf'),None,now)
        steps=[.5,1.,2.,2.5,.9] if mode=='path' else [.5,.2] if mode=='hold' else [.5] if mode=='reverse' else [1.2] if mode=='weak' else [0.]
        stops=[c['engine']['trade']['stop']]
        for i,r in enumerate(steps,1):
            at=now+(120000 if mode=='gap' else i*30000)
            p=4100.+sign*r*10
            tick={**m,'price':p,'dataAt':at,'analysisBarAt':now+i*300000,'suggestedTarget':p+sign*20}
            if mode=='hold':tick.update(direction='NEUTRAL',mtf='NEUTRAL',trendContext=dict(available=True,intact=True,direction=direction,phase='PULLBACK'))
            if mode=='reverse':tick.update(direction='SHORT',trendContext=dict(available=True,intact=False,direction='SHORT'))
            if mode=='weak':tick.update(direction='NEUTRAL',mtf='NEUTRAL',score=50,trendContext=dict(available=True,intact=False,phase='WEAKENING'))
            c=advance_case(c,tick,None,at)
            stops.append(c['engine']['trade']['stop'])
        kinds=[e['kind'] for e in c['events']]
        monotonic=all(sign*(b-a)>=0 for a,b in zip(stops,stops[1:]))
        expected={'path':'stop','reverse':'reversal-exit','weak':'profit-taking','gap':'data-gap'}.get(mode)
        passed=monotonic and (c['status']=='open' if mode=='hold' else expected in kinds)
        if mode=='path':passed=passed and all(k in kinds for k in ('partial-profit','target-extended','stop-raised')) and c['remaining']==0
        if mode=='gap':passed=passed and c['status']=='inconclusive'
        c.update(demonstration=True,scenarioName=name,checkPassed=passed,note='Künstlicher Funktionstest. Keine Orders, keine Push-Zustellung, keine Euro-Produktstop-Prüfung; nicht in der Handelsstatistik.')
        results.append(c)
    return results


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

def run_once(conn,bundle,market,selection,quotes,now,profile_policy=None):
    row=conn.execute('SELECT payload FROM bob_paper_control WHERE id=1 FOR UPDATE').fetchone()
    control=row[0]
    control.setdefault('initialCapital',100.);control.setdefault('cash',100.);control.setdefault('equity',100.);control.setdefault('realizedProfit',0.)
    local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'));day=local.date().isoformat()
    if control.get('ledgerDay')!=day:
        control.update(ledgerDay=day,dayOpeningEquity=control.get('equity'),dayOpeningRealized=control['realizedProfit'])
    control.update(checkedAt=now,ruleVersion=market.get('ruleVersion'),lastDirection=market.get('direction','NEUTRAL'),lastGold=market.get('price'),goldAt=market.get('dataAt'))
    phase = background_push.degiro_session(now)
    if now >= control['startAt'] and control.get('enabled') and phase != 'trading':
        control.update(status='market-closed' if phase=='weekend' else 'night-paused' if phase=='night' else 'preparing',
                       reason='Goldmarkt geschlossen · fiktive Simulation pausiert' if phase=='weekend' else
                              'DEGIRO-Produkte nachts nicht handelbar · Simulation pausiert, Kapitalstand erhalten')
        conn.execute('UPDATE bob_paper_control SET payload=%s::jsonb WHERE id=1',(json.dumps(control),))
        return
    if now<control['startAt']:
        control.update(status='scheduled',reason='Start am 8.10.2026, danach fortlaufend')
    elif not control.get('enabled'):
        control.update(status='paused',reason='Simulation pausiert')
    else:
        active=conn.execute('SELECT id,payload FROM bob_paper_cases WHERE closed_at IS NULL ORDER BY started_at LIMIT 1 FOR UPDATE').fetchone()
        if active:
            key,c=active;released=c.get('cashReleased',0);booked=c.get('bookedUnits',0);q=quotes.get(c['product']['isin'])
            c=advance_case(c,market,q,now)
            if c.get('exitReason')=='ko-safety-exit' or c.get('koWatchStatus') in ('knockout-confirmed','product-terminated','crossed-observed'):
                excluded=control.get('koExcluded') or {}
                if excluded.get('day')!=day:excluded={'day':day,'isins':[]}
                if c['product']['isin'] not in excluded['isins']:
                    excluded['isins'].append(c['product']['isin'])
                control['koExcluded']=excluded
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
            plan=market.get('plan')
            excluded=control.get('koExcluded') or {}
            blocked=set(excluded.get('isins') or []) if excluded.get('day')==day else set()
            candidates=[x for x in (selection.get('choices') or []) if x.get('isin') not in blocked]
            # Keep ranking, but do not let the top ranked unsafe KO product
            # hide the next genuinely eligible candidate.
            safe_candidates=[x for x in candidates
                 if not x.get('koGuardRequired') or (
                     fresh_quote(quotes.get(x['isin']),now,x['isin'])
                     and paper_ko_guard.entry_reason(x,quotes.get(x['isin']),market,now)[0] is None)]
            choice=next(iter(safe_candidates or candidates),None)
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
            elif profile_policy and profile_policy.get('early_impulse') and market.get('paperEntrySource')!='early-impulse-paper-v1':
                reason='Frühimpuls-Strategie: '+str(market.get('earlyPaperBlockReason') or 'kein bestätigter 5m/15m-Frühimpuls')
            elif not stop_target_audit.valid_plan(plan):reason='ABWARTEN: kein bestätigter gültiger Goldplan'
            elif not choice:
                reason=('KO-Schutz: heute ausgeschlossene ISIN; ' if blocked else 'Kein passendes belegtes Produkt: ')+ '; '.join(selection.get('reasons') or ['kein geeigneter neuer Kandidat'])
            elif profile_policy and profile_policy.get('early_impulse') and choice.get('koGuardRequired') is not True:
                reason='Frühimpuls-KO-Schutz: Nur ausdrücklich vollständig geprüfte Produkte zulässig'
            elif choice.get('indicative') or choice.get('estimated'):reason='Unverbindlicher Kandidat: kein virtueller Eurokauf ohne Produktfreigabe'
            elif not q:reason='Produkteinstieg gesperrt · '+choice['isin']+': '+str(quote_block_reason(quotes.get(choice['isin']),now,choice['isin']))
            elif choice.get('koGuardRequired') and paper_ko_guard.entry_reason(choice,quotes.get(choice['isin']),market,now)[0]:
                reason='KO-Schutz: '+paper_ko_guard.entry_reason(choice,quotes.get(choice['isin']),market,now)[0]
            elif profile_policy and __import__('paper_portfolios').entry_block_reason(profile_policy,market):
                reason=__import__('paper_portfolios').entry_block_reason(profile_policy,market)
            elif q['ask']>min(control['cash'], (control.get('equity') or control['cash'])*
                   (profile_policy['exposure_fraction'] if profile_policy else 1.)):
                reason='Risikobudget reicht nicht für ein ganzes Produktstück'
            elif (control.get('dayProfit') is not None and control.get('dayOpeningEquity') is not None
                  and control['dayOpeningEquity']>0 and control['dayProfit']<=-
                  (profile_policy['daily_loss_fraction'] if profile_policy else .03)*control['dayOpeningEquity']):
                reason='Tagesverlustgrenze für neue virtuelle Einstiege erreicht ('+str(round(100*(profile_policy['daily_loss_fraction'] if profile_policy else .03)))+' %)'
            elif control.get('lastEntryKey')==entry_key:reason='Diese Signal-Kerze wurde bereits simuliert'
            else:
                budget=min(control['cash'], (control.get('equity') or control['cash'])*
                           (profile_policy['exposure_fraction'] if profile_policy else 1.))
                c=new_case(market,choice,quotes.get(choice['isin']),now,cash=budget)
                if c.get('koGuardRequired'):
                    _,c['koWatch']=paper_ko_guard.entry_reason(choice,quotes.get(choice['isin']),market,now)
                    c['koWatchStatus']='confirmed'
                if profile_policy:
                    c['profile']=profile_policy['id']
                    if profile_policy.get('early_impulse'):
                        c['entryHypothesis']='early-impulse-paper-v1'
                        c['entrySignalAt']=(market.get('earlyImpulse') or {}).get('barAt')
                        c['entryConfirmedMainTrend']=False
                    c['availableAtEntry']=control['cash']
                    if profile_policy.get('hold_trend'):
                        # Lengthened intraday strategy, never carries past Bob's
                        # recorded 21:45 Europe/Zurich product monitoring limit.
                        local_at=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'))
                        close_ms=local_at.replace(hour=21,minute=45,second=0,microsecond=0).timestamp()*1000
                        c['endsAt']=min(now+8*3600000,close_ms)
                        c['trendFollow']=True
                        c['exitPolicy']='trend-follow-v1'
                        c['trendHighWater']=market['price'] if market['direction']=='LONG' else None
                        c['trendLowWater']=market['price'] if market['direction']=='SHORT' else None
                        c['trendReversalBars']=0
                        c['trendExtensions']=0
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
_bundle_ready=threading.Event()
_pool=None;_pending={};_quotes={};_requested={}
def quote_cache(products, active, now):
    global _pool
    if _pool is None:_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='bob-paper-quotes')
    for isin,future in list(_pending.items()):
        if not future.done():continue
        try:_quotes[isin]=future.result()
        except Exception as exc:print('BOB_PAPER quote_failed='+type(exc).__name__,flush=True)
        del _pending[isin]
    active_isins=active if isinstance(active,(list,tuple,set)) else [active] if active else []
    isins=list(dict.fromkeys([i for i in active_isins if i]+[p.get('isin') for p in products if p.get('isin')]))
    from product_quotes import get_quote
    # Oldest request first: slow sources must not repeatedly monopolize the
    # four slots just because their products occur first in the uploaded list.
    # Active positions retain priority among equally due requests.
    due=sorted((isin for isin in isins if isin not in _pending),
               key=lambda isin: (_requested.get(isin,0), isin not in active_isins))
    for isin in due:
        if len(_pending)>=4:break
        if now-_requested.get(isin,0)>=30000:
            _requested[isin]=now;_pending[isin]=_pool.submit(get_quote,isin)
    by_isin={p['isin']:p.get('quote') for p in products if p.get('isin')}
    return {isin:_quotes.get(isin,by_isin.get(isin)) for isin in isins}

def _worker(db):
    while True:
        _bundle_ready.wait(timeout=30)
        with _guard:
            _bundle_ready.clear()
            bundle=_latest
        if bundle and background_push.degiro_session() == 'trading':
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
                        import paper_portfolios
                        active_cases=paper_portfolios.active_cases(conn)
                        now=time.time()*1000
                        settings=dict(timeframe='15m',trailAtr=1.5,learningPolicy=rule_learning.policy(conn))
                        active_isins=[c['product']['isin'] for c in active_cases.values() if c.get('product',{}).get('isin')]
                        quotes=quote_cache(evidence['products'],active_isins,now)
                        # Evaluate ONLY the active screenshot list against the
                        # already refreshed quotes. Audit failure must never roll
                        # back paper positions, stop logic or signal delivery.
                        conn.execute('SAVEPOINT bob_degiro_audit')
                        try:
                            import degiro_product_audit
                            degiro_product_audit.store(conn,evidence,quotes,now)
                            conn.execute('RELEASE SAVEPOINT bob_degiro_audit')
                        except Exception as audit_exc:
                            conn.execute('ROLLBACK TO SAVEPOINT bob_degiro_audit')
                            conn.execute('RELEASE SAVEPOINT bob_degiro_audit')
                            print('BOB_PRODUCT_AUDIT error='+type(audit_exc).__name__,flush=True)
                        # Original four paper policies consume unchanged confirmed direction.
                        market=background_push.analyze(bundle,settings,priority=2)
                        selection=dict(choices=[],reasons=[])
                        if market.get('ready') and market.get('direction') in ('LONG','SHORT') and any(
                             p not in active_cases for p in ('conservative','balanced','offensive','trend800')):
                            request={**evidence,'quotes':quotes,'market':market,'bundle':bundle}
                            p=evaluator_runtime.run(['node',str(Path(__file__).with_name('paper_selection.js'))],input=json.dumps(request),
                                             text=True,capture_output=True,timeout=6,check=True,priority=2)
                            selection=json.loads(p.stdout)
                        # Independent extra research account receives its own direction
                        # and derived stop/target; same exact product validator and quotes.
                        early_market=paper_portfolios.early_paper_market(market,now)
                        early_selection=dict(choices=[],reasons=['Kein freigegebenes Produkt zur Frühwarnung'])
                        if ('early100' not in active_cases and
                            early_market.get('paperEntrySource')=='early-impulse-paper-v1'):
                            request={**evidence,'quotes':quotes,'market':early_market,'bundle':bundle}
                            try:
                                p=evaluator_runtime.run(['node',str(Path(__file__).with_name('paper_selection.js'))],
                                    input=json.dumps(request),text=True,capture_output=True,timeout=6,
                                    check=True,priority=2)
                                early_selection=json.loads(p.stdout)
                            except Exception as early_exc:
                                early_selection['reasons']=['Frühimpuls-Produktprüfung nicht verfügbar: '+type(early_exc).__name__]
                                print('BOB_EARLY_PAPER_SELECTION error='+type(early_exc).__name__,flush=True)
                        outcomes=paper_portfolios.run_all(conn,bundle,market,selection,quotes,
                                                          time.time()*1000,settings,active_cases,
                                                          early_market=early_market,early_selection=early_selection)
                        # Observational research MUST NOT interrupt existing paper ledgers.
                        # A PostgreSQL savepoint contains all collector failures.
                        conn.execute('SAVEPOINT bob_zukunft_capture')
                        try:
                            import zukunft_capture
                            zukunft_capture.record(conn,market,selection,quotes,time.time()*1000)
                            conn.execute('RELEASE SAVEPOINT bob_zukunft_capture')
                        except Exception as capture_error:
                            conn.execute('ROLLBACK TO SAVEPOINT bob_zukunft_capture')
                            conn.execute('RELEASE SAVEPOINT bob_zukunft_capture')
                            print('BOB_ZUKUNFT capture_error='+type(capture_error).__name__,flush=True)
                        conn.commit()
                        print('BOB_PAPER checked profiles='+str(outcomes)+
                              ' direction='+str(market.get('direction'))+
                              ' ready='+str(market.get('ready'))+
                              ' priceFresh='+str(market.get('priceFresh')),flush=True)
            except Exception as exc:print('BOB_PAPER error='+type(exc).__name__,flush=True)

def enqueue(bundle, db):
    # Avoid starting the quote/analysis worker because someone calls the API
    # during a scheduled weekend closure.
    if background_push.degiro_session() != 'trading':
        return
    global _latest,_thread
    with _guard:
        _latest=bundle
        _bundle_ready.set()
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_worker,args=(db,),daemon=True,name='bob-paper-simulation');_thread.start()

