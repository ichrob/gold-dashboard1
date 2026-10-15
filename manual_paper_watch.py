"""Read-only background monitoring for the existing LOCAL manual paper test.

Neither the browser's bobManualTradeTestV1 record nor the three automated
paper portfolios are changed. This module never submits broker orders.
Watch starts at first authenticated sync, not retroactively at user entry time.
"""
import datetime as dt
import json
import math
import re
import threading
import time

from zoneinfo import ZoneInfo

_LOCK = threading.Lock()
_THREAD = None
_EVENT = threading.Event()
_LAST_ATTEMPT = 0.0
VERSION = 'manual-paper-observation-v1'
MAX_QUOTE_AGE_MS = 90_000


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_manual_paper_watch (
        id INTEGER PRIMARY KEY CHECK (id = 1), payload JSONB NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_manual_paper_observations (
        quote_at TIMESTAMPTZ NOT NULL, isin TEXT NOT NULL,
        bid DOUBLE PRECISION NOT NULL, source TEXT NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        pnl_eur DOUBLE PRECISION NOT NULL, value_eur DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (isin,quote_at)
    )""")


def positive(x):
    return type(x) in (int,float) and math.isfinite(x) and x>0


def iso_stamp(raw):
    if not isinstance(raw,str) or len(raw)>45:
        raise ValueError('Zeitstempel fehlt')
    try:
        stamp=dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError('Ungültiger Zeitstempel') from exc
    if stamp.tzinfo is None:raise ValueError('Zeitstempel ohne Zeitzone')
    return stamp.astimezone(dt.timezone.utc)


def validate_position(obj):
    if not isinstance(obj,dict) or obj.get('mode')!='manual-paper-test':
        raise ValueError('Kein bestehender manueller Test')
    isin=obj.get('isin')
    if not isinstance(isin,str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{10}',isin):
        raise ValueError('ISIN ungültig')
    direction=obj.get('direction')
    if direction not in ('LONG','SHORT'):
        raise ValueError('LONG/SHORT ungültig')
    if not positive(obj.get('entry')) or type(obj.get('quantity')) is not int or not 0<obj['quantity']<=100000:
        raise ValueError('Einstieg oder Stückzahl ungültig')
    date=iso_stamp(obj.get('createdAt'))
    if date.timestamp()>time.time()+60:
        raise ValueError('Test-Zeitpunkt liegt in der Zukunft')
    return dict(isin=isin,direction=direction,entry=float(obj['entry']),
                quantity=obj['quantity'],createdAt=date.isoformat())


def sync(conn,payload):
    original=validate_position(payload.get('position'))
    row=conn.execute('SELECT payload FROM bob_manual_paper_watch WHERE id=1 FOR UPDATE').fetchone()
    if row:
        existing=row[0]
        if existing.get('position')!=original:
            return dict(ok=False,reason='Andere Testdaten bereits geschützt. Die bestehende Position wurde nicht verändert.',
                        watch=public_record(existing))
        return dict(ok=True,existing=True,watch=public_record(existing))
    state=dict(version=VERSION,position=original,connectedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
               checkedAt=None,lastSourceAt=None,valuation=None,eventsCount=0,
               status='waiting-market',reason='Erste aktuelle Anbieterquote noch nicht geprüft',
               stopEur=None,targetEur=None,alerts=[],lastEventKind=None)
    conn.execute('INSERT INTO bob_manual_paper_watch(id,payload) VALUES(1,%s::jsonb) ON CONFLICT(id) DO NOTHING',
                 (json.dumps(state),))
    current=conn.execute('SELECT payload FROM bob_manual_paper_watch WHERE id=1').fetchone()[0]
    return dict(ok=current.get('position')==original,existing=False,watch=public_record(current))


def set_levels(conn,payload):
    row=conn.execute('SELECT payload FROM bob_manual_paper_watch WHERE id=1 FOR UPDATE').fetchone()
    if not row:return dict(ok=False,reason='Erst vorhandenen Test synchronisieren')
    s=row[0];p=s['position'];entry=p['entry']
    levels={}
    for k in ('stopEur','targetEur'):
        x=payload.get(k)
        if x is not None and not positive(x):
            raise ValueError('Grenzwert muss positiv sein')
        levels[k]=float(x) if x is not None else None
    stop,target=levels['stopEur'],levels['targetEur']
    # Both LONG and SHORT knock-out certificates are PURCHASED securities.
    # A short certificate rises when gold falls, but the bought certificate
    # still gains when its own bid rises. Stop/target are PRODUCT EUR prices.
    if (stop is not None and stop>=entry) or (target is not None and target<=entry):
        raise ValueError('Gekauftes Knock-out-Produkt: Stop unter, Ziel über Einstieg')
    s.update(levels)
    conn.execute('UPDATE bob_manual_paper_watch SET payload=%s::jsonb WHERE id=1',(json.dumps(s),))
    return dict(ok=True,watch=public_record(s))


def public_record(s):
    return {k:s.get(k) for k in ('version','position','connectedAt','checkedAt','status','reason',
             'lastSourceAt','valuation','eventsCount','stopEur','targetEur','alerts')}


def report(conn,payload=None):
    row=conn.execute('SELECT payload FROM bob_manual_paper_watch WHERE id=1').fetchone()
    if not row:return dict(ok=True,connected=False,reason='Manueller Test muss auf diesem Gerät einmal geöffnet werden')
    s=row[0]
    observations=conn.execute("""SELECT quote_at,bid,source,pnl_eur,value_eur FROM bob_manual_paper_observations
        WHERE isin=%s ORDER BY quote_at DESC LIMIT 30""",(s['position']['isin'],)).fetchall()
    return dict(ok=True,connected=True,watch=public_record(s),
                observations=[dict(quoteAt=row[0].isoformat(),bid=row[1],source=row[2],
                                   pnlEur=row[3],valueEur=row[4]) for row in observations])


def quote_observation(q,isin,now_ms):
    """Only verified, timestamped EUR issuer bids, never chart/model/old quotes."""
    if not isinstance(q,dict) or q.get('isin')!=isin or q.get('productVerified') is not True:
        return None,'Produktidentität/Anbieterquote nicht bestätigt'
    if q.get('found') is not True or q.get('marketOpen') is not True:
        return None,'Kein aktuell handelbarer bestätigter Anbieter-Geldkurs'
    if q.get('currency')!='EUR' or q.get('isExecutableQuote') is False or q.get('priceKind') in ('calculated','issuer-chart'):
        return None,'Kein ausführbarer Euro-Geldkurs'
    if not positive(q.get('bid')) or not isinstance(q.get('source'),str) or not q['source']:
        return None,'Geldkurs oder Quelle fehlt'
    try:
        at=iso_stamp(q.get('bidAt') or q.get('quoteAt'))
    except ValueError:return None,'Quellenzeit fehlt'
    age=now_ms-int(at.timestamp()*1000)
    if not 0<=age<=MAX_QUOTE_AGE_MS or q.get('delayed'):
        return None,'Kurs veraltet oder Zeitbezug unbestätigt'
    return dict(at=at,bid=float(q['bid']),source=q['source'][:160]),None



def research_observation(quote, isin, now_ms):
    """Use existing fail-closed paper projection for MODEL valuation only.

    This is never an issuer execution quote and MUST NOT trigger confirmed
    stop/target notices. Currency conversion and source clocks are validated
    in paper_simulation.paper_quote, not inferred from the latest spot tick.
    """
    if not isinstance(quote, dict) or quote.get('isin') != isin or quote.get('sourceDisabled'):
        return None
    meta = quote.get('metadata') or {}
    if (quote.get('productVerified') is not True or meta.get('status') != 1
            or meta.get('tradingHalted') is True):
        return None
    from paper_simulation import paper_quote
    projected = paper_quote(quote, now_ms, isin)
    if (not isinstance(projected, dict) or projected.get('paperQuoteAccepted') is not True
            or projected.get('isin') != isin or projected.get('currency') != 'EUR'
            or projected.get('marketOpen') is not True
            or projected.get('isExecutableQuote') is not False
            or projected.get('degiroExecutable') is not False
            or not str(projected.get('paperQuoteLabel') or '').startswith('Simulationskurs')
            or not positive(projected.get('bid')) or not positive(projected.get('ask'))
            or projected['ask'] < projected['bid']):
        return None
    try:
        times = [iso_stamp(projected[k]) for k in ('bidAt', 'askAt', 'quoteAt')]
    except (KeyError, ValueError):
        return None
    if any(not 0 <= now_ms - int(t.timestamp()*1000) <= MAX_QUOTE_AGE_MS for t in times):
        return None
    fx = projected.get('paperFxConversion')
    native = projected.get('paperNativeQuote')
    if native and (not isinstance(fx, dict) or fx.get('fromCurrency') != 'CHF'
                   or fx.get('toCurrency') != 'EUR' or not fx.get('evidence')):
        return None
    return dict(at=min(times), bid=float(projected['bid']),
                source=str(projected.get('source') or '')[:160],
                referenceOnly=True, label=projected['paperQuoteLabel'][:180])



def observe(conn,quote,now_ms=None):
    """Persist one quote timestamp once; do not invent interpolation or fills."""
    if now_ms is None:now_ms=int(time.time()*1000)
    row=conn.execute('SELECT payload FROM bob_manual_paper_watch WHERE id=1 FOR UPDATE').fetchone()
    if not row:return dict(ok=False,reason='Manueller Test noch nicht synchronisiert')
    s=row[0];p=s['position'];s['checkedAt']=dt.datetime.fromtimestamp(now_ms/1000,dt.timezone.utc).isoformat()
    metadata = quote.get('metadata') or {} if isinstance(quote, dict) else {}
    issuer_direction = (quote.get('direction') or metadata.get('direction')) if isinstance(quote, dict) else None
    if issuer_direction in ('LONG', 'SHORT') and issuer_direction != p['direction']:
        obs,error = None,'Produktrichtung widerspricht Emittent; keine Kursbewertung'
    else:
        obs,error=quote_observation(quote,p['isin'],now_ms)
        if error:
            # A coherent market-observation may value the PAPER position;
            # only the original verified issuer bid can trigger stop/target.
            obs = research_observation(quote,p['isin'],now_ms)
            if obs:error=None
    if error:
        s.update(status='waiting-quote',reason=error,valuation=None)
    else:
        last=s.get('lastSourceAt')
        stamp=obs['at'].isoformat()
        if last and iso_stamp(last)>=obs['at']:
            s.update(status='waiting-quote',reason='Keine neue datierte Anbieterquote',valuation=None)
        else:
            bid=obs['bid']
            # Profit depends on the PURCHASED certificate price for both sides.
            # SHORT describes the GOLD exposure, not a short sale of shares.
            pnl=(bid-p['entry'])*p['quantity']
            value=bid*p['quantity']
            inserted=conn.execute("""INSERT INTO bob_manual_paper_observations
                (quote_at,isin,bid,source,pnl_eur,value_eur)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING quote_at""",
                (obs['at'],p['isin'],bid,obs['source'],pnl,value)).fetchone()
            research = obs.get('referenceOnly') is True
            s.update(status='model-observed' if research else 'observed',
                     reason=('Datierter Simulationskurs für die Modellbewertung; '
                             'keine ausführbare DEGIRO-Quote und keine bestätigten Stop-/Zielereignisse'
                             if research else 'Neuer bestätigter Anbieter-Geldkurs · nur Modellbewertung'),
                     lastSourceAt=stamp,valuation=dict(bidEur=bid,quoteAt=stamp,source=obs['source'],
                                                      pnlEur=round(pnl,2),valueEur=round(value,2),
                                                      referenceOnly=research,degiroExecutable=False,
                                                      grossOnly=True))
            if inserted:
                s['eventsCount']=s.get('eventsCount',0)+1
                hit=[]
                stop,target=s.get('stopEur'),s.get('targetEur')
                if not research and stop is not None and bid<=stop:
                    hit.append('stop-observed')
                if not research and target is not None and bid>=target:
                    hit.append('target-observed')
                for kind in hit:
                    if s.get('lastEventKind') != kind:
                        s['alerts']=(s.get('alerts') or [])[-19:]+[dict(kind=kind,at=stamp,bidEur=bid,
                              note='Schwelle bei beobachtetem Kurs überschritten; keine Order ausgelöst')]
                        s['lastEventKind']=kind
                if not hit:
                    s['lastEventKind']=None
    conn.execute('UPDATE bob_manual_paper_watch SET payload=%s::jsonb WHERE id=1',(json.dumps(s),))
    return dict(ok=True,watch=public_record(s))


def _run(db):
    global _LAST_ATTEMPT
    while True:
        _EVENT.wait(timeout=30)
        _EVENT.clear()
        now_ms=int(time.time()*1000)
        if _LAST_ATTEMPT and now_ms-_LAST_ATTEMPT<60_000:
            continue
        # Closed app still receives the scanner's background cycles.
        import background_push
        if background_push.degiro_session(now_ms)!='trading':
            continue
        try:
            with db() as conn:
                row=conn.execute('SELECT payload FROM bob_manual_paper_watch WHERE id=1').fetchone()
            if not row:continue
            _LAST_ATTEMPT=now_ms
            isin=row[0]['position']['isin']
            from product_quotes import get_quote
            try:
                quote=get_quote(isin)
            except Exception as exc:
                print('BOB_MANUAL_WATCH quote_error='+type(exc).__name__,flush=True)
                quote=None
            with db() as conn:
                conn.execute('SELECT pg_advisory_xact_lock(72611011)')
                result=observe(conn,quote)
                conn.commit()
            print('BOB_MANUAL_WATCH state='+str(result['watch']['status'])+
                  ' isin='+isin,flush=True)
        except Exception as exc:
            print('BOB_MANUAL_WATCH error='+type(exc).__name__,flush=True)


def enqueue(db):
    import background_push
    if background_push.degiro_session()!='trading':
        return
    global _THREAD
    with _LOCK:
        _EVENT.set()
        if _THREAD is None or not _THREAD.is_alive():
            _THREAD=threading.Thread(target=_run,args=(db,),name='bob-manual-paper-watch',daemon=True)
            _THREAD.start()
