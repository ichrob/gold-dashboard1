"""Prospective, observed-quote paper cases; never a broker/order connection."""
import copy
import hashlib
import json
import adaptive_learning as rule_learning
import paper_case_review
import paper_reflection
import paper_entry_review
import paper_stop_study
import paper_ledger_costs
import ranking_learning
import ranking_lifecycle
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
import quote_updates

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
        'Falldetails dauerhaft gespeichert; Tagesstatistik fortlaufend ohne festes Enddatum.')

def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0

def stamp(value):
    if finite(value): return value
    try:
        at=datetime.fromisoformat(value.replace('Z','+00:00'))
        return at.timestamp()*1000 if at.tzinfo else None
    except (TypeError,ValueError,AttributeError): return None

def chf_paper_quote(q, now, isin):
    """Dated native CHF observations projected into EUR for paper ledgers only."""
    from swissquote_quotes import eligible_primary, current_pair
    if not eligible_primary(q, isin) or (q.get('metadata') or {}).get('tradingHalted'):
        return None
    clock=datetime.fromtimestamp(now/1000, timezone.utc)
    native=current_pair(q, clock)
    if native is None:
        if q.get('marketOpen') is False:return None
        chart=q.get('nativeChartEvidence') or q.get('chartEvidence') or {}
        if chart.get('currency') != 'CHF' or chart.get('delayed'):
            return None
        native=dict(isin=isin, currency='CHF',bid=chart.get('bid'),ask=chart.get('ask'),
                    bidAt=chart.get('pointAt'),askAt=chart.get('pointAt'),quoteAt=chart.get('pointAt'),
                    source='SG · datierter CHF-Chartkurs',priceKind='issuer-chart')
    times=[stamp(native.get(k)) for k in ('bidAt','askAt')]
    if (not finite(native.get('bid')) or not finite(native.get('ask')) or native['ask']<native['bid']
            or any(t is None or not 0<=now-t<=90000 for t in times)):
        return None
    from sg_chf import convert_analysis
    converted=convert_analysis(dict(chartEvidence=dict(bid=native['bid'],ask=native['ask'],
        currency='CHF',pointAt=datetime.fromtimestamp(min(times)/1000,timezone.utc).isoformat())), now=clock)
    fx=converted.get('currencyConversion');chart=converted.get('chartEvidence')
    if not fx or not chart or not 0<=now-stamp(fx['at'])<=90000:
        return None
    out=copy.deepcopy(q)
    out.update(isin=isin,found=True,marketOpen=True,paperQuoteAccepted=True,
        paperNativeQuote=copy.deepcopy(native),paperFxConversion=fx,currencyConversion=fx,
        paperIssuerSource=q.get('source'),paperIssuerSourceUrl=q.get('sourceUrl'),
        source=native['source'],venue='Swiss DOTS',currency='EUR',bid=chart['bid'],ask=chart['ask'],
        price=chart['ask'],bidAt=fx['at'],askAt=fx['at'],quoteAt=fx['at'],
        priceKind=native['priceKind'],isExecutableQuote=False,degiroExecutable=False,
        paperQuoteLabel='Simulationskurs · '+native['source']+' · CHF in EUR umgerechnet · keine DEGIRO-Ausführung')
    inputs=(out.get('leverageCalculation') or {}).get('inputs')
    if isinstance(inputs,dict):
        inputs.update(usdEur=fx['evidence']['eur'],quoteCurrency='EUR',askEur=chart['ask'],
                      fxDataAt=fx['evidence']['dataAt'],fxEffectiveAt=fx['evidence']['eurAt'])
    return out


def paper_quote(q, now, isin):
    """Project a validated public LiveTrading pair into the paper ledger only.

    Never change the provider payload, source clocks or broker execution flags.
    Product approval, leverage, KO and strategy checks remain independent.
    """
    if not isinstance(q, dict) or q.get('isin') != isin:
        return q
    converted=chf_paper_quote(q,now,isin)
    if converted is not None:return converted
    if (q.get('found') is True and q.get('isExecutableQuote') is not False
            and all(stamp(q.get(k)) is not None and 0 <= now-stamp(q[k]) <= 90000 for k in ('bidAt','askAt'))):
        return q
    meta = q.get('metadata') or {}
    if (q.get('productVerified') is not True or q.get('sourceDisabled')
            or meta.get('status') != 1 or meta.get('tradingHalted') is True):
        return q
    from comdirect_quotes import matches_primary
    candidates = [q.get('analysisQuote'), q.get('secondaryQuote')]
    valid = []
    for pair in candidates:
        if not isinstance(pair, dict):
            continue
        if (pair.get('isin') != isin or pair.get('currency') != 'EUR'
                or not matches_primary(q, pair)
                or pair.get('priceKind') != 'market-observation'
                or pair.get('delayed') or pair.get('isExecutableQuote') is not False
                or pair.get('degiroExecutable') is not False
                or not finite(pair.get('bid')) or not finite(pair.get('ask'))
                or pair['ask'] < pair['bid']):
            continue
        times = [stamp(pair.get(k)) for k in ('bidAt', 'askAt', 'quoteAt')]
        if not all(t is not None and 0 <= now-t <= 90000 for t in times):
            continue
        if len(set(times)) != 1:
            continue
        valid.append(pair)
    if not valid:
        return q
    pair = max(valid, key=lambda x: stamp(x['quoteAt']))
    out = copy.deepcopy(q)
    out.update(copy.deepcopy(pair))
    out.update(found=True, marketOpen=True, paperQuoteAccepted=True,
               paperIssuerSource=q.get('source'), paperIssuerSourceUrl=q.get('sourceUrl'),
               paperQuoteLabel='Simulationskurs · '+pair['source']+' · keine bestätigte DEGIRO-Ausführung')
    return out

def quote_block_reason(q, now, isin):
    if not isinstance(q,dict):return 'Noch keine Kursantwort vorhanden'
    if q.get('isin')!=isin:return 'ISIN der Kursantwort stimmt nicht überein'
    if not q.get('paperQuoteAccepted'):
        pair=q.get('secondaryQuote') or {}
        at=stamp(pair.get('quoteAt'))
        # Explain a structurally valid but expired backup rather than blaming
        # the newer chart. Validation at its original clock never permits entry.
        if at is not None and at <= now and now-at > 90000:
            historical=paper_quote(q,at,isin)
            if historical.get('paperQuoteAccepted'):
                return 'comdirect-Geld-/Briefkurs älter als 90 Sekunden; neue Quellenquote wird abgerufen'
    if (q.get('priceKind') in ('calculated','issuer-chart') and not q.get('paperFxConversion')) or (q.get('isExecutableQuote') is False and q.get('paperQuoteAccepted') is not True):
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
    q=paper_quote(q,now,isin)
    if quote_block_reason(q,now,isin):return None
    return {k:q.get(k) for k in ('isin','bid','ask','currency','source','quoteAt','bidAt','askAt','paperQuoteLabel','paperNativeQuote','paperFxConversion','isExecutableQuote','degiroExecutable')}

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
    paper_stop_study.init(conn)

def sync(conn, payload):
    products=payload.get('products')
    if not isinstance(products,list) or not 0<len(products)<=12:raise ValueError('Produktliste ungültig')
    # Empty UI slots are not products. Keep nonempty uncertain OCR rows visible.
    products=[p for p in products if isinstance(p,dict) and
              (str(p.get('isin') or '').strip() or str(p.get('name') or '').strip())]
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
    if old_time is not None and new_time==old_time and previous.get('listCorrection'):
        return dict(ok=True, products=len(previous.get('products') or []), preserved=True,
                    reason='Geprüfte Listenkorrektur bleibt aktiv; neue Listenbilder können sie ersetzen')
    if old_time is not None and new_time==old_time:
        expected={p.get('isin') for p in previous.get('products') or [] if isinstance(p,dict) and p.get('isin')}
        current={p.get('isin') for p in products if isinstance(p,dict) and p.get('isin')}
        if expected!=current:
            return dict(ok=True,products=len(previous.get('products') or []),
                        preserved=True, reason='Dieselbe Upload-Version enthält widersprüchliche ISINs')
    keys=('isin','name','productDirection','direction','isinConfirmed','price','leverage','ko','spread','spot',
          'quote','snapshot','listVenueEvidence','type','currency','basisPrice','ratio','underlying','contract','maturity')
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
    # Save original listing proofs before a newer generation replaces snapshots.
    if previous.get('listOrigin') == 'degiro-screenshot' and new_time != old_time:
        import broker_venue_evidence
        broker_venue_evidence.archive_feed(conn, previous)
    conn.execute('''INSERT INTO bob_paper_products(id,payload) VALUES(1,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload,synced_at=now()''',(text,))
    if new_time is not None and (old_time is None or new_time > old_time):
        # Previously approved product-Push candidates belong to the old list.
        # Clear just their selection evidence; leave active trade/stop monitors,
        # trade journals and independent market alerts untouched.
        conn.execute('''UPDATE subscriptions SET selection_evidence=NULL, product_selection=NULL
            WHERE selection_evidence IS NOT NULL OR product_selection IS NOT NULL''')
    return dict(ok=True,products=len(safe['products']),listUploadedAt=uploaded)

def new_case(market, choice, quote, now, cash=100., cost_model=None,bundle=None):
    p=copy.deepcopy(market['plan']);direction=p['direction'];risk=abs(p['entry']-p['stop'])
    local=datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich'))
    end=min(now+4*3600000,local.replace(hour=21,minute=45,second=0,microsecond=0).timestamp()*1000)
    key=hashlib.sha256(json.dumps([VERSION,market.get('ruleVersion'),market.get('learningPolicy'),market.get('analysisBarAt'),direction,choice['isin']],sort_keys=True).encode()).hexdigest()
    # No currency model is guessed from a leverage number or future contract.
    q=None if choice.get('indicative') or choice.get('estimated') else fresh_quote(quote,now,choice['isin'])
    quantity=(paper_ledger_costs.units(cash,q['ask'],cost_model) if cost_model else math.floor((cash+1e-9)/q['ask'])) if q else None
    if quantity==0:raise ValueError('Kapital reicht nicht für ein Produktstück')
    t=dict(tradeId=key,dir=direction,entry=p['entry'],stop=p['stop'],target=p['target'],initialRisk=risk,instrument='XAU/USD',active=True,product=None)
    return dict(stopStudySetup=paper_stop_study.setup(market,bundle,now),id=key,version=VERSION,status='open',day=local.date().isoformat(),startedAt=now,endsAt=end,
                plan=p,ledgerCostModel=copy.deepcopy(cost_model),product=copy.deepcopy(choice),koGuardRequired=choice.get('koGuardRequired') is True,
                priceBasis=copy.deepcopy(choice.get('priceBasis')),
                entryQuote=q,entryAsk=q['ask'] if q else None,
                analysis=copy.deepcopy(market),lastAt=market['dataAt'],remaining=1.,goldR=0.,productGrossPct=0. if q else None,
                productReturnKnown=bool(q),netReturnKnown=False,modelOnly=True,partialTaken=False,
                observedPeakValue=quantity*q['ask'] if quantity else None,
                observedMaxDrawdownPct=(1-q['bid']/q['ask'])*100 if quantity else None,
                observedValuationChecks=1 if quantity else 0,
                quantity=quantity,remainingUnits=quantity,pendingUnits=0,cashReleased=0.,bookedUnits=0,
                allocated=quantity*q['ask'] if quantity else None,availableAtEntry=cash,
                entrySpreadEur=round(quantity*(q['ask']-q['bid']),8) if quantity else None,
                entrySpreadPct=round((q['ask']/q['bid']-1)*100,4) if quantity else None,
                capitalMode=('EUR-Ganzstück-Modell nach Beispielkosten' if cost_model else 'EUR-Ganzstück-Bruttomodell') if quantity else 'Goldplan ohne Europosition',
                engine=dict(trade=t),events=[dict(kind='entry',at=market['dataAt'],recordedAt=now,gold=market['price'],quote=q,
                    reason=market.get('decisionReason'),ruleVersion=market.get('ruleVersion'),learningPolicy=market.get('learningPolicy'))])

def advance_case(original, market, quote, now):
    """Stop checks precede trailing; resumed gaps cannot manufacture a win."""
    c=copy.deepcopy(original)
    def event(kind,**extra):
        c['events'].append(dict(kind=kind,at=market.get('dataAt'),recordedAt=now,
            inputEvidence={key:copy.deepcopy(market.get(key)) for key in
                ('dataAt','analysisBarAt','ready','priceFresh','ruleVersion','decisionReason')},**extra))
    def defer_remaining():
        if c.get('remainingUnits'):
            c['pendingUnits']+=c['remainingUnits'];c['remainingUnits']=0;c['remaining']=0.
            c['pendingSince']=now
    terminal_status = paper_ko_guard.terminal(quote, c['product']['isin'])
    if terminal_status and (c['status']=='open' or c.get('pendingUnits')):
        # Provider-confirmed terminal status is not a known executable price
        # or a proven zero recovery. Keep unpriced units pending.
        changed = c.get('koWatchStatus') != terminal_status
        c.update(status='inconclusive',closedAt=c.get('closedAt') or now,
                 productReturnKnown=False,productGrossPct=None,
                 koWatchStatus=terminal_status)
        defer_remaining()
        if changed:event(terminal_status,reason='Emittent meldet Produktende; Abrechnungswert unbekannt, kein erfundener Verkauf')
        return c
    q=fresh_quote(quote,now,c['product']['isin']) if c.get('quantity') else None
    if q and c.get('quantity'):
        value=c.get('cashReleased',0)+(c.get('remainingUnits',0)+c.get('pendingUnits',0))*q['bid']
        peak=max(c.get('observedPeakValue') or c.get('allocated') or value,value)
        if peak>0:
            c['observedPeakValue']=peak
            c['observedMaxDrawdownPct']=max(c.get('observedMaxDrawdownPct') or 0,(1-value/peak)*100)
            c['observedValuationChecks']=c.get('observedValuationChecks',0)+1
    if (c.get('pendingUnits') and q and
            c.get('koWatchStatus') not in ('knockout-confirmed','product-terminated') and
            stamp(q.get('bidAt') or q.get('quoteAt'))>=c['pendingSince']):
        units=c['pendingUnits'];c['cashReleased']+=units*q['bid'];c['bookedUnits']+=units;c['pendingUnits']=0
        event('deferred-sale',units=units,quote=q,reason='Späterer Modellverkauf zum ersten verfügbaren frischen Geldkurs; kein rückdatierter Ausstieg')
        if not c.get('remainingUnits'):
            c.update(productReturnKnown=True,productGrossPct=(c['cashReleased']/c['allocated']-1)*100,settledAt=now)
    if c['status']!='open':return c
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
    if c.get('comparisonFixedPlan') is True:
        # Read-only shadow case: original stop/target, same KO/time/gap checks.
        if (p>=t['target'] if long else p<=t['target']):
            realize('target-exit',c['remaining'])
        return c
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
    control['costPeriodProfit']=(equity-control['costsOpeningEquity'] if equity is not None and control.get('costsOpeningEquity') is not None else None)

def entry_block_context(market, choice, control):
    """Copy only decision-time fields needed for later paper-entry review."""
    market = market if isinstance(market, dict) else {}
    choice = choice if isinstance(choice, dict) else {}
    control = control if isinstance(control, dict) else {}
    plan = market.get('plan')
    safe_plan = ({key:copy.deepcopy(plan.get(key))
                  for key in ('kind', 'entry', 'stop', 'target', 'unit')
                  if plan.get(key) is not None}
                 if isinstance(plan, dict) else None)
    return {
        'direction':market.get('direction', 'NEUTRAL'),
        'isin':choice.get('isin'),
        'goldAt':market.get('dataAt'),
        'ruleVersion':market.get('ruleVersion'),
        'signalSource':control.get('signalSource'),
        'plan':safe_plan,
    }


def day_update(conn, day, closed=None, wait=None, now=None,capital=None,product=None,entry=None,checklist=None):
    row=conn.execute('SELECT payload FROM bob_paper_days WHERE day=%s',(day,)).fetchone()
    d=row[0] if row else dict(cases=0,closed=0,inconclusive=0,goldPositive=0,goldNegative=0,goldFlat=0,
                             productKnown=0,productPositive=0,productNegative=0,waitChecks=0)
    d.update(lastCheckedAt=now)
    if checklist:
        d['lastEntryChecklist']=copy.deepcopy(checklist)
        counters=d.setdefault('entryCheckCounts',{})
        for item in checklist['checks']:
            key=item['label']+' · '+item['state']
            counters[key]=counters.get(key,0)+1
    if capital:
        d.update(openingCapital=capital.get('dayOpeningEquity'),capital=capital.get('equity'),cash=capital['cash'],
                 dayProfit=capital.get('dayProfit'),totalProfit=capital.get('totalProfit'),openUnits=capital.get('openUnits',0),
                 capitalAt=now,valuationKnown=capital.get('valuationKnown',True),initialCapital=capital['initialCapital'],
                  observedMaxDrawdownPct=capital.get('maxDrawdownPct'),
                  quoteMissingChecksSinceStart=capital.get('quoteMissingChecks',0),
                  quoteConfirmedChecksSinceStart=capital.get('quoteConfirmedChecks',0))
        d.update(costsDebitedEur=capital.get('costsDebitedEur'),costPeriodProfit=capital.get('costPeriodProfit'),costsStartedAt=capital.get('costsStartedAt'))
        d.update(realizedProfit=capital.get('realizedProfit',0),dayRealizedProfit=capital.get('realizedProfit',0)-capital.get('dayOpeningRealized',0))
    if wait:
        d.update(waitChecks=d['waitChecks']+1,lastWait=wait)
        if entry:
            counts=d.setdefault('entryBlockCounts',{})
            counts[wait]=counts.get(wait,0)+1
            records=d.setdefault('entryBlocks',[])
            observed=dict(at=now,reason=wait,**entry)
            if records and all(records[-1].get(k)==observed.get(k) for k in ('reason','direction','isin')):
                records[-1].update(lastAt=now,checks=records[-1].get('checks',1)+1)
            else:records.append({**observed,'lastAt':now,'checks':1})
            if len(records)>200:
                d['entryBlocksTruncated']=True
                del records[:-200]
    if closed:
        d['cases']+=1
        if closed['status']=='closed':
            d['closed']+=1
            value=closed['goldR'];d['goldPositive' if value>0 else 'goldNegative' if value<0 else 'goldFlat']+=1
        else:d['inconclusive']+=1
    product=product or closed
    if product:
        product['performanceAccountingVersion'] = 2
    if product and product.get('status') == 'closed' and product['productReturnKnown']:
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
    exclusions = paper_case_review.legacy_exclusions(conn)
    profile = getattr(conn, 'profile', None)
    phase = background_push.degiro_session()
    closed = phase == 'weekend'
    status = dict(control)
    if phase != 'trading' and status.get('status') not in ('completed','ending-pending-quotes') and status.get('enabled') and time.time()*1000 >= status.get('startAt', START):
        status.update(status='market-closed' if closed else 'night-paused' if phase=='night' else 'preparing',
                      reason='Goldmarkt geschlossen · Simulation pausiert' if closed
                             else 'DEGIRO-Nachtmodus · Simulation pausiert, gespeichert und geschützt' if phase=='night'
                             else 'Vorbereitung ab 07:30 Uhr · Simulation startet ab 08:00 Uhr')
    return dict(ok=True,version=VERSION,note=NOTE,control=status,marketClosed=closed,sessionMode=phase,day=day,stats=paper_case_review.adjust_daily(stats[0] if stats else {}, exclusions.get(day)),
                products=[dict(isin=p.get('isin'),direction=p.get('productDirection'),name=p.get('name')) for p in feed[0]['products'] if p.get('isin')] if feed else [],
                productSyncedAt=feed[1].isoformat() if feed else None,cases=[paper_case_review.project_case(r[0], profile) for r in cases],
                evidenceReview=__import__('paper_costs').evidence_report([paper_case_review.project_case(r[0],profile) for r in cases]),
                costReview=__import__('paper_costs').report([r[0] for r in cases]),
                decisionReview=paper_entry_review.daily([r[0] for r in cases],stats[0] if stats else {},day),
                daily=[dict(day=d,**paper_case_review.adjust_daily(s, exclusions.get(d))) for d,s in totals],detailsLimit=100,detailRetentionDays=None,detailRetention='permanent',
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
    campaign_end=(profile_policy or {}).get('campaign_end')
    if finite(campaign_end) and control.get('endAt') != campaign_end:
        previous_end=control.get('endAt')
        if finite(previous_end) and campaign_end > previous_end:
            # Record the observed balance at extension; never reseed cash or replay
            # the interval after the old deadline. Existing cases remain untouched.
            extensions=list(control.get('campaignExtensions') or [])
            extensions.append(dict(previousEndAt=previous_end,endAt=campaign_end,appliedAt=now,
                previousStatus=control.get('status'),cash=control.get('cash'),
                equity=control.get('equity'),totalProfit=control.get('totalProfit')))
            control['campaignExtensions']=extensions
        control['endAt']=campaign_end
    campaign_over=finite(campaign_end) and now>=campaign_end
    if now >= control['startAt'] and control.get('enabled') and phase != 'trading' and not campaign_over:
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
        if campaign_over and not active:
            control.update(status='completed',reason='Vergleich beendet · Freitag 16:00 Zürich',endAt=campaign_end)
            conn.execute('UPDATE bob_paper_control SET payload=%s::jsonb WHERE id=1',(json.dumps(control),))
            return
        if active:
            key,c=active;released=c.get('cashReleased',0);booked=c.get('bookedUnits',0);q=quotes.get(c['product']['isin'])
            if profile_policy and profile_policy.get('bob_stop_reentry') and c.get('trendFollow'):
                c=copy.deepcopy(c)
                c.update(trendFollow=False,exitPolicy='bob-stop-reentry-v1')
                c['events'].append(dict(kind='stop-policy-changed',at=market.get('dataAt'),recordedAt=now,
                  stop=c['engine']['trade']['stop'],reason='800-EUR-Test übernimmt Bobs gemeinsame Stoppverwaltung; vorhandener Schutzstopp bleibt erhalten'))
            if finite(campaign_end):
                c=copy.deepcopy(c)
                c['endsAt']=min(c['endsAt'],campaign_end)
            c=advance_case(c,market,q,now)
            if c.get('exitReason')=='ko-safety-exit' or c.get('koWatchStatus') in ('knockout-confirmed','product-terminated','crossed-observed'):
                excluded=control.get('koExcluded') or {}
                if excluded.get('day')!=day:excluded={'day':day,'isins':[]}
                if c['product']['isin'] not in excluded['isins']:
                    excluded['isins'].append(c['product']['isin'])
                control['koExcluded']=excluded
            control['cash']+=c.get('cashReleased',0)-released
            control['realizedProfit']+=c.get('cashReleased',0)-released-(c.get('bookedUnits',0)-booked)*(c.get('entryAsk') or 0)
            paper_ledger_costs.apply(control,c)
            capital_snapshot(control,c,q,now)
            if c['status']!='open' and not c.get('counted'):
                day_update(conn,c['day'],closed=c,now=now);c['counted']=True;c['productCounted']=c['productReturnKnown']
            elif c['status']!='open' and c['productReturnKnown'] and not c.get('productCounted'):
                day_update(conn,c['day'],product=c,now=now);c['productCounted']=True
            finished=c['status']!='open' and not c.get('pendingUnits')
            if finished:
                paper_reflection.record(control,c,now)
            if finished and c.get('exitReason')=='stop':
                control.update(lastStopAt=c.get('closedAt'),lastStopBar=market.get('analysisBarAt'))
            conn.execute('UPDATE bob_paper_cases SET payload=%s::jsonb,closed_at=to_timestamp(%s) WHERE id=%s',
                         (json.dumps(c),(c.get('settledAt') or c.get('closedAt'))/1000 if finished else None,key))
            control.update(status='running',reason='Simulationsfall '+c['status']+(' · Euroverkauf wartet auf Kurs' if c.get('pendingUnits') else ''),activeCase=None if finished else key)
            if campaign_over:
                control.update(status='completed' if finished else 'ending-pending-quotes',
                    reason='Vergleich beendet' if finished else 'Vergleich beendet · unbelegte Ausstiegsbewertung bleibt offen',endAt=campaign_end)
            day_update(conn,day,now=now,capital=control)
        else:
            capital_snapshot(control,None,None,now)
            cost_model=paper_ledger_costs.MODEL if profile_policy and now>=paper_ledger_costs.START else None
            if cost_model:paper_ledger_costs.activate(control,now)
            entered=False
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
            elif profile_policy and profile_policy.get('early_warning') and market.get('paperEntrySource')!='early-warning-paper-v2':
                reason='Frühwarn-Test: '+str(market.get('warningPaperBlockReason') or 'Keine aktuelle gültige Frühwarnung')
            elif not stop_target_audit.valid_plan(plan):
                reason=('ABWARTEN: kein bestätigter gültiger Goldplan' if market.get('direction') not in ('LONG','SHORT')
                        else 'Stopp-/Zielplan fehlt oder ist ungültig: '+str(market.get('decisionReason') or 'Planprüfung nicht bestanden'))
            elif not choice:
                reason=('KO-Schutz: heute ausgeschlossene ISIN; ' if blocked else 'Kein passendes belegtes Produkt: ')+ '; '.join(selection.get('reasons') or ['kein geeigneter neuer Kandidat'])
            elif profile_policy and (profile_policy.get('early_impulse') or profile_policy.get('campaign')) and choice.get('koGuardRequired') is not True:
                reason='Frühimpuls-KO-Schutz: Nur ausdrücklich vollständig geprüfte Produkte zulässig'
            elif choice.get('indicative') or choice.get('estimated'):reason='Unverbindlicher Kandidat: kein virtueller Eurokauf ohne Produktfreigabe'
            elif not q:reason='Geld-/Briefkurs nicht freigegeben · Produkteinstieg gesperrt · '+choice['isin']+': '+str(quote_block_reason(quotes.get(choice['isin']),now,choice['isin']))
            elif choice.get('koGuardRequired') and paper_ko_guard.entry_reason(choice,quotes.get(choice['isin']),market,now)[0]:
                reason='KO-Schutz: '+paper_ko_guard.entry_reason(choice,quotes.get(choice['isin']),market,now)[0]
            elif profile_policy and __import__('paper_portfolios').entry_block_reason(profile_policy,market):
                reason=__import__('paper_portfolios').entry_block_reason(profile_policy,market)
            elif (q['ask']*(1+cost_model['slippageBpsPerSide']/10000)+3*cost_model['feeEurPerOrder'] if cost_model else q['ask'])>min(control['cash'], (control.get('equity') or control['cash'])*
                   (profile_policy['exposure_fraction'] if profile_policy else 1.)):
                reason='Risikobudget reicht nicht für ein ganzes Produktstück einschließlich Kostenreserve' if cost_model else 'Risikobudget reicht nicht für ein ganzes Produktstück'
            elif (control.get('dayProfit') is not None and control.get('dayOpeningEquity') is not None
                  and control['dayOpeningEquity']>0 and control['dayProfit']<=-
                  (profile_policy['daily_loss_fraction'] if profile_policy else .03)*control['dayOpeningEquity']):
                reason='Tagesverlustgrenze für neue virtuelle Einstiege erreicht ('+str(round(100*(profile_policy['daily_loss_fraction'] if profile_policy else .03)))+' %)'
            elif finite(control.get('lastStopBar')) and (not finite(market.get('analysisBarAt')) or market['analysisBarAt']<=control['lastStopBar']):
                reason='Nach Stop-Loss: neue bestätigte Signal-Kerze für Wiedereinstieg abwarten'
            elif control.get('lastEntryKey')==entry_key:reason='Diese Signal-Kerze wurde bereits simuliert'
            elif paper_entry_review.capture(market,choice,quotes.get(choice['isin']),now,False,'Pflichtprüfung',control,profile_policy)['requiredFailures']:
                reason='Einstiegscheckliste: Pflichtprüfung nicht erfüllt; Richtung, Produkt und Originalnachweise prüfen'
            else:
                budget=min(control['cash'], (control.get('equity') or control['cash'])*
                           (profile_policy['exposure_fraction'] if profile_policy else 1.))
                entry_checklist=paper_entry_review.capture(market,choice,quotes.get(choice['isin']),now,True,'Alle bisherigen Einstiegssperren bestanden',control,profile_policy)
                c=new_case(market,choice,quotes.get(choice['isin']),now,cash=budget,cost_model=cost_model,bundle=bundle)
                c['entryChecklist']=entry_checklist
                c['selectionEvidence']=__import__('paper_evidence_chain').capture_selection(selection, choice, now)
                if c.get('koGuardRequired'):
                    _,c['koWatch']=paper_ko_guard.entry_reason(choice,quotes.get(choice['isin']),market,now)
                    c['koWatchStatus']='confirmed'
                if profile_policy:
                    c['profile']=profile_policy['id']
                    if profile_policy.get('bob_stop_reentry'):c['exitPolicy']='bob-stop-reentry-v1'
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
                if profile_policy and profile_policy.get('campaign'):
                    c['endsAt']=min(c['endsAt'],profile_policy['campaign_end'])
                    c['campaign']='signal-comparison-20261027'
                    c['entryHypothesis']=market.get('paperEntrySource') or 'confirmed-main'
                    c['entrySignalAt']=(market.get('earlyWarning') or {}).get('signalBarAt') if profile_policy.get('early_warning') else market.get('analysisBarAt')
                entry_control=copy.deepcopy(control)
                entry_control['cash']-=c.get('allocated') or 0
                paper_ledger_costs.apply(entry_control,c)
                inserted=conn.execute('''INSERT INTO bob_paper_cases(id,day,started_at,payload)
                    VALUES(%s,%s,to_timestamp(%s),%s::jsonb) ON CONFLICT DO NOTHING RETURNING id''',
                    (c['id'],day,now/1000,json.dumps(c))).fetchone()
                entered=bool(inserted)
                control.update(lastEntryKey=entry_key,activeCase=c['id'] if inserted else None)
                if inserted:
                    for field in ('cash','realizedProfit','costsDebitedEur'):
                        if field in entry_control:control[field]=entry_control[field]
                    capital_snapshot(control,c,quotes.get(choice['isin']),now)
                reason='Neuer Simulationsfall gespeichert' if inserted else 'Signal bereits dokumentiert'
            if not entered:
                entry_checklist=paper_entry_review.capture(market,choice,quotes.get(choice['isin']) if choice else None,now,False,reason,control,profile_policy)
            control['lastEntryChecklist']=entry_checklist
            control.update(status='running',reason=reason)
            day_update(conn,day,wait=None if entered else reason,now=now,capital=control,checklist=entry_checklist,
                       entry=entry_block_context(market, choice, control)
                         if not entered else None)
        # Preserve original entry/exit evidence; bounded report queries limit reads, not retention.
    conn.execute('UPDATE bob_paper_control SET payload=%s::jsonb WHERE id=1',(json.dumps(control),))

def newer_queued_paper_bundle(current, candidate, now_ms):
    """Take a complete fresher observed bundle, never an inferred or mixed tick.

    Running quote-cache calls can overlap with new upstream observations. Only
    replace a stale worker input with a newer timestamped collector bundle
    that satisfies the unchanged 60-second input-age requirement.
    """
    def source_at(bundle):
        if not isinstance(bundle,dict):
            return None
        spots=bundle.get('spots')
        history=bundle.get('history')
        if not isinstance(spots,dict) or not isinstance(history,dict):
            return None
        if not isinstance(history.get('bars_by_tf'),dict):
            return None
        if spots.get('is_genuine_xauusd_spot') is not True or spots.get('xaus_is_spot') is not True:
            return None
        source=spots.get('spot_price_as_of')
        if not isinstance(source,str):
            return None
        try:
            at=datetime.fromisoformat(source.replace('Z','+00:00'))
            if at.tzinfo is None:
                return None
            ms=at.timestamp()*1000
            return ms if math.isfinite(ms) and ms>0 else None
        except (TypeError,ValueError,OverflowError):
            return None
    if type(now_ms) not in (int,float) or not math.isfinite(now_ms):
        return current
    new_time=source_at(candidate)
    old_time=source_at(current)
    return (candidate if new_time is not None and 0<=now_ms-new_time<=60000
            and (old_time is None or new_time>old_time) else current)


def late_risk_retry_bundle(current, candidate, now_ms):
    """Return one newer verified snapshot for a paper-only late retry, else None."""
    selected=newer_queued_paper_bundle(current,candidate,now_ms)
    return selected if selected is not current else None


# Independent bounded worker: product network calls never delay /background or Push.
_guard=threading.Lock();_latest=None;_thread=None
_bundle_ready=quote_updates.updates
_pool=None;_pending={};_quotes={};_requested={}
_observed_snapshot={}
def observed_quotes(products):
    """Read completed raw issuer observations without network work or paper projection."""
    with _guard:
        return {p['isin']: copy.deepcopy(_observed_snapshot[p['isin']])
                for p in products if p.get('isin') in _observed_snapshot}

def quote_cache(products, active, now):
    global _pool, _observed_snapshot
    if _pool is None:_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='bob-paper-quotes')
    for isin,future in list(_pending.items()):
        if not future.done():continue
        try:_quotes[isin]=future.result()
        except Exception as exc:print('BOB_PAPER quote_failed='+type(exc).__name__,flush=True)
        del _pending[isin]
    active_isins=active if isinstance(active,(list,tuple,set)) else [active] if active else []
    isins=list(dict.fromkeys([i for i in active_isins if i]+[p.get('isin') for p in products if p.get('isin')]))
    quote_updates.updates.track(isins)
    from product_quotes import get_quote
    # Oldest request first: slow sources must not repeatedly monopolize the
    # four slots just because their products occur first in the uploaded list.
    # Active positions retain priority among equally due requests.
    from product_repair_learning import request_order
    due=request_order([isin for isin in isins if isin not in _pending], active_isins, _requested, now)
    for isin in due:
        if len(_pending)>=4:break
        if now-_requested.get(isin,0)>=30000:
            _requested[isin]=now;_pending[isin]=_pool.submit(get_quote,isin)
            _pending[isin].add_done_callback(lambda future, key=isin: quote_updates.completed(key, future))
    by_isin={p['isin']:p.get('quote') for p in products if p.get('isin')}
    # Primary issuer work is limited to four products per cycle. Completed
    # backup observations must not wait for that slow rotation to reach the
    # ledgers (ten products otherwise take at least three 30-second cycles).
    # apply() is nonblocking and shares the bounded 30-second source cache.
    from comdirect_quotes import apply as refresh_backup
    from swissquote_quotes import apply as refresh_third_source
    from leverage_backup import apply as refresh_leverage
    from comdirect_fields import apply as refresh_fields
    from hybrid_product_price import apply as refresh_calculated_price
    observations={}
    observed={}
    for isin in isins:
        raw=_quotes.get(isin,by_isin.get(isin))
        # Independently harvest the shared nonblocking source cache even while
        # all issuer slots are occupied. Identity checks remain in each parser.
        from product_source_recovery import enrich
        recovery=[]
        raw=enrich('comdirect-terms',isin,refresh_fields,raw if isinstance(raw,dict) else {'isin':isin},recovery)
        refreshed=enrich('comdirect-quote',isin,refresh_backup,raw,recovery)
        refreshed=enrich('swissquote-quote',isin,refresh_third_source,refreshed,recovery)
        # Push receives the same refreshed source evidence, before paper-only
        # price projection. Publish a complete batch atomically below.
        if isinstance(refreshed, dict):
            refreshed = refresh_leverage(refreshed)
            observed[isin] = copy.deepcopy(refreshed)
            observations[isin] = refresh_calculated_price(copy.deepcopy(refreshed))
        else:
            observations[isin] = refreshed
        if recovery:
            observations[isin]['sourceRecovery']=recovery
            if any(event['state'] in ('failed','waiting') for event in recovery):
                observations[isin]['eligible']=False
            if isin in observed:
                observed[isin]['sourceRecovery'] = copy.deepcopy(recovery)
                if any(event['state'] in ('failed','waiting') for event in recovery):
                    observed[isin]['eligible'] = False
    with _guard:
        _observed_snapshot = observed
    return observations

# Morning research-only preparation. Never creates/changes paper positions,
# delivers a push, enables an order, or certifies an executable DEGIRO quote.
_PREFLIGHT_LOCK = threading.Lock()
_PREFLIGHT_THREAD = None


def preflight_once(database, now_ms=None):
    """Refresh stored screenshot product evidence during 07:30–08:00 Zurich.

    This uses the SAME bounded issuer caches, validator and audit used after
    08:00, but deliberately does not call any simulation or trade method.
    """
    current_clock = now_ms is None
    now_ms = int(time.time()*1000) if current_clock else now_ms
    if background_push.degiro_session(now_ms) != 'preparation':
        return {'state': 'paused', 'auditUpdated': False, 'ordersEnabled': False}
    with database() as conn:
        acquired = conn.execute('SELECT pg_try_advisory_xact_lock(72610408)').fetchone()
        if not acquired or acquired[0] is not True:
            return {'state': 'busy', 'auditUpdated': False, 'ordersEnabled': False}
        feed = conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
        evidence = feed[0] if feed else {}
        if (not isinstance(evidence, dict)
                or evidence.get('listOrigin') != 'degiro-screenshot'
                or not evidence.get('listUploadedAt')
                or not any(p.get('isin') for p in evidence.get('products') or []
                           if isinstance(p, dict))):
            return {'state': 'waiting-for-screenshot', 'auditUpdated': False, 'ordersEnabled': False}
        # Advance shared quote-cache requests over repeated, bounded iterations.
        # Result may be missing/closed/stale before issuer opening: that is not
        # converted to a valid quote or an executable broker price.
        observations = quote_cache(evidence['products'], [], now_ms)
        from degiro_product_audit import store as store_audit
        with conn.transaction():
            store_audit(conn, evidence, observations, int(time.time()*1000) if current_clock else now_ms)
        conn.commit()
        return {'state': 'research-only', 'auditUpdated': True, 'ordersEnabled': False}



def audit_offhours_once(database, now_ms=None):
    """Record missing proof for one newly imported screenshot generation off-hours.

    The ordinary issuer refresh remains restricted to the existing preparation
    and trading paths. This only creates the current list's fail-closed audit
    using *no* quote observations, so a midnight image import need not look
    indefinitely unexamined. It neither fetches providers nor performs orders.
    One advisory-locked write per generation avoids periodic database growth.
    """
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    if background_push.degiro_session(now_ms) in ('trading', 'preparation'):
        return {'state': 'paused', 'auditUpdated': False, 'ordersEnabled': False}
    with database() as conn:
        with conn.transaction():
            locked = conn.execute('SELECT pg_try_advisory_xact_lock(72610408)').fetchone()
            if not locked or locked[0] is not True:
                return {'state': 'busy', 'auditUpdated': False, 'ordersEnabled': False}
            feed = conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
            evidence = feed[0] if feed else {}
            if (not isinstance(evidence, dict)
                    or evidence.get('listOrigin') != 'degiro-screenshot'
                    or not evidence.get('listUploadedAt')
                    or not any(isinstance(p, dict) and p.get('isin')
                               for p in evidence.get('products') or [])):
                return {'state': 'waiting-for-screenshot', 'auditUpdated': False, 'ordersEnabled': False}
            latest = conn.execute('SELECT payload FROM bob_degiro_product_audit WHERE id=1').fetchone()
            if latest and latest[0].get('listUploadedAt') == evidence['listUploadedAt']:
                return {'state': 'already-checked', 'auditUpdated': False, 'ordersEnabled': False}
            from degiro_product_audit import store as store_audit
            store_audit(conn, evidence, {}, now_ms)
        conn.commit()
    return {'state': 'evidence-only', 'auditUpdated': True, 'ordersEnabled': False}


def _preflight_loop(database, wait=time.sleep):
    """Idle outside preparation. Exact 07:30 and 08:00 boundaries are bounded."""
    while True:
        phase = background_push.degiro_session()
        if phase == 'preparation':
            try:
                outcome = preflight_once(database)
                print('BOB_PRODUCT_PREFLIGHT state='+outcome['state'], flush=True)
            except Exception as exc:
                # Never print source payload, ISIN, broker identity or credentials.
                print('BOB_PRODUCT_PREFLIGHT error='+type(exc).__name__, flush=True)
            wait(30)
        else:
            # The ordinary paper worker pauses off-hours; record the *new*
            # screenshot's missing-proof state once, without provider calls.
            # Product detail validity is established only by later real quotes.
            try:
                if phase in ('night', 'weekend'):
                    outcome = audit_offhours_once(database)
                    if outcome['auditUpdated']:
                        print('BOB_PRODUCT_PREFLIGHT state=evidence-only', flush=True)
            except Exception as exc:
                print('BOB_PRODUCT_PREFLIGHT error='+type(exc).__name__, flush=True)
            wait(max(1, min(300, background_push.degiro_seconds_to_transition())))


def start_preflight(database):
    """One read-only morning worker on the existing push service."""
    global _PREFLIGHT_THREAD
    with _PREFLIGHT_LOCK:
        if _PREFLIGHT_THREAD and _PREFLIGHT_THREAD.is_alive():
            return False
        _PREFLIGHT_THREAD = threading.Thread(
            target=_preflight_loop, args=(database,), daemon=True,
            name='bob-product-preflight')
        _PREFLIGHT_THREAD.start()
    return True


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
                        try:
                            with conn.transaction():active_isins+=ranking_lifecycle.active_isins(conn)
                            with conn.transaction():active_isins+=paper_stop_study.active_isins(conn)
                            with conn.transaction():active_isins+=__import__("risk_paper").active_isins(conn)
                        except Exception as exc:print('BOB_RANKING_EXITS lookup_error='+type(exc).__name__,flush=True)
                        import product_repair_learning
                        try:
                            with conn.transaction():
                                saved=conn.execute('SELECT payload FROM bob_degiro_product_audit WHERE id=1').fetchone()
                            product_repair_learning.install(saved[0] if saved else {},now)
                        except Exception:
                            product_repair_learning.install({})
                        quotes=quote_cache(evidence['products'],active_isins,now)
                        # Reuse a complete newer collector snapshot only if it
                        # already arrived; never fetch or change a source clock.
                        with _guard:
                            queued_bundle=_latest
                        fresh=newer_queued_paper_bundle(bundle,queued_bundle,time.time()*1000)
                        if fresh is not bundle:
                            bundle=fresh
                            print('BOB_PAPER reused_newer_observed_bundle=1',flush=True)
                        # Source refresh may fetch newer timestamps. Audit against
                        # completion time, never the clock from before those reads.
                        now=time.time()*1000
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
                        precision_quotes=dict(quotes)
                        quotes={isin:paper_quote(q,now,isin) for isin,q in quotes.items()}
                        try:
                            with conn.transaction():
                                __import__('risk_paper').tick(conn,bundle,evidence,quotes,time.time()*1000)
                        except Exception as exc:
                            print('BOB_RISK_PAPER error='+type(exc).__name__,flush=True)
                        # Original four paper policies consume unchanged confirmed direction.
                        market=background_push.analyze(bundle,settings,priority=2)
                        selection=dict(choices=[],reasons=[])
                        ranking_policy=ranking_learning.policy(conn)
                        precision_due=now%(2*3600000)<=300000
                        if market.get('ready') and market.get('direction') in ('LONG','SHORT') and (precision_due or any(
                             p not in active_cases for p,policy in paper_portfolios.POLICIES.items() if not policy.get('early_impulse') and not policy.get('early_warning'))):
                            request={**evidence,'quotes':quotes,'market':market,'bundle':bundle,'rankingPolicy':ranking_policy}
                            p=evaluator_runtime.run(['node',str(Path(__file__).with_name('paper_selection.js'))],input=json.dumps(request),
                                             text=True,capture_output=True,timeout=6,check=True,priority=2)
                            selection=json.loads(p.stdout)
                        try:
                            with conn.transaction():
                                import product_precision
                                product_precision.capture(conn,market,selection,precision_quotes,bundle.get('spots'),time.time()*1000)
                                ranking_learning.capture(conn,market,selection,precision_quotes,bundle.get('spots'),time.time()*1000,simulation_quotes=quotes)
                                ranking_lifecycle.tick(conn,market,quotes,int(time.time()*1000))
                        except Exception as exc:print('BOB_PRECISION_CAPTURE error='+type(exc).__name__,flush=True)
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
                        warning_market=paper_portfolios.warning_paper_market(market,now)
                        warning_selection=dict(choices=[],reasons=['Kein freigegebenes Frühwarnprodukt'])
                        if now<paper_portfolios.CAMPAIGN_END and 'early1000oct' not in active_cases and warning_market.get('paperEntrySource'):
                            try:
                                request={**evidence,'quotes':quotes,'market':warning_market,'bundle':bundle,'rankingPolicy':ranking_policy}
                                p=evaluator_runtime.run(['node',str(Path(__file__).with_name('paper_selection.js'))],
                                    input=json.dumps(request),text=True,capture_output=True,timeout=6,check=True,priority=2)
                                warning_selection=json.loads(p.stdout)
                            except Exception as exc:
                                warning_selection['reasons']=['Frühwarn-Produktauswahl nicht verfügbar: '+type(exc).__name__]
                        input_observations=[]
                        outcomes=paper_portfolios.run_all(conn,bundle,market,selection,quotes,
                                                          time.time()*1000,settings,active_cases,
                                                          early_market=early_market,early_selection=early_selection,
                                                          input_observations=input_observations,
                                                          warning_market=warning_market,warning_selection=warning_selection)
                        try:
                            with conn.transaction():paper_stop_study.tick(conn,market,quotes,time.time()*1000)
                        except Exception as exc:print('BOB_STOP_STUDY error='+type(exc).__name__,flush=True)
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
                        # Quote and portfolio work can overlap the next collector cycle.
                        # Re-evaluate only the virtual risk paper on one strictly newer,
                        # complete observed snapshot; all provider-open guards stay intact.
                        try:
                            with _guard:
                                late_candidate=_latest
                            late_bundle=late_risk_retry_bundle(bundle,late_candidate,time.time()*1000)
                            if late_bundle is not None:
                                with conn.transaction():
                                    __import__('risk_paper').tick(conn,late_bundle,evidence,quotes,time.time()*1000)
                                print('BOB_RISK_PAPER retried_newer_observed_bundle=1',flush=True)
                        except Exception as late_risk_exc:
                            print('BOB_RISK_PAPER late_retry_error='+type(late_risk_exc).__name__,flush=True)
                        conn.commit()
                        # A post-commit observation of the exact input quality passed
                        # to each virtual account. Failure never changes paper ledgers.
                        try:
                            import paper_input_evidence
                            paper_input_evidence.capture(bundle,input_observations,time.time()*1000)
                        except Exception:
                            print('BOB_PAPER_INPUT_AUDIT unavailable',flush=True)
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



