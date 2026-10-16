"""Start observation of a reported purchase server-side; never place orders."""
import json, threading, time
from datetime import datetime, timezone
import background_push as bp
import product_trade_history as curve
import trade_workflow as workflow

_lock=threading.Lock()
_state={'status':'waiting','message':'Warte auf eindeutigen Kaufbeleg.','checkedAt':None}
_last=0

def timing(snapshot):
    purchase=snapshot.get('purchase') or {}
    started=snapshot.get('monitorStartedAt')
    if not started:return None
    try:
        from zoneinfo import ZoneInfo
        at=datetime.fromisoformat(started.replace('Z','+00:00'))
        if at.tzinfo is None:return None
        bought=workflow.receipt_clock({'executedAt':purchase.get('at'),'executedLocal':purchase.get('executedLocal')})
        delay=(at.astimezone(ZoneInfo('Europe/Zurich')).replace(tzinfo=None)-bought).total_seconds()
        return dict(startedAt=started,delaySeconds=round(max(0,delay)),timezoneAssumed=not bool(purchase.get('at')))
    except (ValueError,TypeError,KeyError):return None

def status():
    return dict(_state)

def product_reference(quote, receipt, lookup):
    isin=receipt['isin'];m=quote.get('metadata') or {};model=quote.get('productModel') or {}
    if quote.get('isin')!=isin or quote.get('productVerified') is not True or model.get('isin')!=isin or model.get('verifiedSimpleTurbo') is not True:
        raise ValueError('Produktidentität oder einfaches Turbo-Modell noch offen')
    if m.get('status')==2 or m.get('tradingHalted') is True or (m.get('underlyingType')!='SPOT' and model.get('underlying')!='XAU/USD'):
        raise ValueError('Kein aktives bestätigtes Gold-Spot-Produkt')
    currency=m.get('currency') or quote.get('currency')
    if currency!='EUR':raise ValueError('EUR-Mailbeleg passt nicht zu nativer Produktwährung')
    q=quote.get('analysisQuote') or quote
    if q.get('currency','EUR')!='EUR':raise ValueError('Referenzwährung stimmt nicht')
    when=q.get('bidAt') or q.get('quoteAt') or q.get('pointAt')
    if not when or not bp.positive(q.get('bid')):raise ValueError('Datierter Referenzkurs fehlt')
    ref=lookup(when,currency)
    if ref.get('available') is not True or ref.get('originalTime')!=when or not isinstance(ref.get('maxSkewSeconds'),(int,float)) or not 0<=ref['maxSkewSeconds']<=90:
        raise ValueError('Zeitlich passendes Gold-/FX-Paar fehlt')
    c=quote.get('conditions') or {}
    p=dict(isin=isin,currency=currency,direction=m.get('direction') or model.get('direction'),
      entry=receipt['priceEur'],quantity=receipt['quantity'],bid=q['bid'],referenceAt=when,
      source=str(q.get('source') or quote.get('source') or 'Emittentenreferenz')+' · historische Gold/FX-Zuordnung',
      goldReference=ref.get('goldReference'),fxReference=ref.get('fxReference'),fxScenario=ref.get('fxReference'),
      referenceConfirmed=True,simpleSpotTurbo=True)
    for k in ('ratio','strike','ko'):
        p[k]=(c.get(k) or {}).get('value',model.get(k,m.get(k)))
    return bp.product_model(p,p['direction'])

def tick(db,bundle,quote_fetch=None,lookup=None):
    import real_trade_journal as journal
    from product_quotes import get_quote
    from trade_reference import historical_lookup
    quote_fetch=quote_fetch or get_quote;lookup=lookup or historical_lookup
    _state.update(status='checking',checkedAt=datetime.now(timezone.utc).isoformat())
    with db() as conn:
        if conn.execute('SELECT 1 FROM bob_real_trades WHERE active=TRUE LIMIT 1').fetchone():
            _state.update(status='active',message='Serverüberwachung läuft.');return
        rows=conn.execute('SELECT message_id,payload FROM bob_trade_email_import ORDER BY imported_at DESC LIMIT 100').fetchall()
        records=[p.get('result') or {} for _,p in rows]
        candidates={}
        for mid,payload in rows:
            r=payload.get('result') or {}
            if workflow.eligible_purchase(r,records):
                key=r.get('orderIdDigest')
                if isinstance(key,str) and len(key)==64:candidates[key]=(mid,r)
        if len(candidates)!=1:
            _state.update(status='waiting',message='Kein eindeutiger offener Kaufbeleg für heute.');return
        digest,(mid,receipt)=next(iter(candidates.items()))
        tid='degiro-email-'+digest
        old=conn.execute('SELECT active,snapshot FROM bob_real_trades WHERE id=%s',(tid,)).fetchone()
        if old and not old[1].get('recordOnly'):
            _state.update(status='closed',message='Bereits abgeschlossenen Trade nicht erneut starten.');return
    # Network and expensive analysis happen outside the database transaction.
    product=product_reference(quote_fetch(receipt['isin']),receipt,lookup)
    point=curve.calculate(product,bundle.get('spots'))
    if not point:raise ValueError('Frisches Gold-/FX-Paar für Überwachung fehlt')
    product['fxScenario']=point['fxRate']
    market=bp.analyze(bundle,{'timeframe':'15m','monitorDirection':product['direction']})
    plan=market.get('monitorPlan') or {}
    if market.get('ready') is not True or market.get('priceFresh') is not True or plan.get('direction')!=product['direction']:
        raise ValueError('Frischer geprüfter Stopp-/Zielplan fehlt')
    if not all(bp.positive(plan.get(k)) for k in ('entry','stop','target')) or not abs(plan['entry']-plan['stop'])>0:
        raise ValueError('Stopp-/Zielplan ungültig')
    if not all(bp.product_price(product,plan[k]) for k in ('entry','stop','target')):
        raise ValueError('Stopp-/Zielplan außerhalb der Produktgrenzen')
    if not curve.calculate(product,bundle.get('spots')):
        raise ValueError('Marktdaten während der Vorbereitung veraltet; erneuter Versuch folgt')
    with db() as conn:
        # Serialize against imports, and re-read receipts to catch a sale during lookup.
        conn.execute('SELECT pg_advisory_xact_lock(72143619)')
        if conn.execute('SELECT 1 FROM bob_real_trades WHERE active=TRUE LIMIT 1').fetchone():return
        result=workflow.import_purchase(conn,{'emailReceiptId':mid,'direction':product['direction']})
        old=conn.execute('SELECT active,snapshot FROM bob_real_trades WHERE id=%s FOR UPDATE',(result['tradeId'],)).fetchone()
        if not old or not old[1].get('recordOnly'):return
        now=datetime.now(timezone.utc).isoformat()
        trade=dict(old[1],active=True,recordOnly=False,dir=product['direction'],product=product,
          entry=plan['entry'],stop=plan['stop'],target=plan['target'],
          initialRisk=abs(plan['entry']-plan['stop']),monitorStartedAt=now)
        journal.handle(conn,'write',{'trade':trade,'timeframe':'15m'})
        journal.event(conn,trade['tradeId'],'server-monitor-started',
          {'at':now,'source':'Kauf-Mail + geprüfte Produkt-/Marktdaten','brokerOrder':False},'server-start')
        journal.sync_devices(conn)
        conn.commit()
    _state.update(status='active',message='Überwachung automatisch auf dem Server gestartet.')

def enqueue(db,bundle):
    global _last
    if time.monotonic()-_last<25 or not _lock.acquire(blocking=False):return
    _last=time.monotonic()
    def run():
        try:tick(db,bundle)
        except Exception as exc:
            _state.update(status='waiting-evidence',message=str(exc) if isinstance(exc,ValueError) else 'Datenabruf vorübergehend nicht verfügbar; nächster Serverversuch folgt.')
        finally:_lock.release()
    threading.Thread(target=run,name='bob-trade-autostart',daemon=True).start()
