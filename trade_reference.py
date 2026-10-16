"""Historical scenario inputs, not exchange realtime or executable quotes."""
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from product_quotes import issuer_json

GOLD_URL = 'https://xaus.com/api/v1/intraday?symbol=xau&hours=48'
FX_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=1m&range=1d'
_lock = threading.Lock()
_cache = None
_chf_cache = None

def screenshot_interval(raw):
    # API/issuer timestamps carry an explicit offset; preserve their instant.
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})', str(raw)):
        dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        start = dt.timestamp()
        minute_only = bool(re.fullmatch(r'.*T\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})', str(raw)))
        return start, start+59.999 if minute_only else start
    m = re.fullmatch(r'(\d{2})[./](\d{2})[./](\d{4})[ ,]+(\d{2}):(\d{2})(?::(\d{2}))?', str(raw))
    if not m:
        raise ValueError('Originalzeit mit Datum fehlt')
    day, month, year, hour, minute, second = m.groups()
    dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second or 0), tzinfo=ZoneInfo('Europe/Zurich'))
    if dt.utcoffset() != dt.replace(fold=1).utcoffset() or dt.astimezone(timezone.utc).astimezone(ZoneInfo('Europe/Zurich')).replace(tzinfo=None) != dt.replace(tzinfo=None):
        raise ValueError('Zeitzonenwechsel: genaue Zeit mit Offset erforderlich')
    start = dt.timestamp()
    return start, start if second is not None else start+59.999

def positive(v):
    return not isinstance(v, bool) and isinstance(v, (float, int)) and math.isfinite(v) and v > 0

def align(raw, gold, fx, now=None, currency="EUR"):
    if currency not in ("EUR","CHF"):raise ValueError("Produktwährung muss EUR oder CHF sein")
    now = time.time() if now is None else now
    start, end = screenshot_interval(raw)
    if start > now:
        raise ValueError('Kurszeit liegt in der Zukunft')
    if gold.get('symbol') != 'xau' or gold.get('currency') != 'USD' or gold.get('unit') != 'troy_oz':
        raise ValueError('Gold-Spot-Identität nicht bestätigt')
    r = fx['chart']['result'][0]
    if r['meta'].get('symbol') != ('USDCHF=X' if currency=='CHF' else 'EURUSD=X') or r['meta'].get('currency') != ('CHF' if currency=='CHF' else 'USD') or r['meta'].get('instrumentType') != 'CURRENCY' or r['meta'].get('dataGranularity') != '1m':
        raise ValueError('Passende FX-Minutenhistorie nicht bestätigt')
    def fits(a,b):
        return b <= now and a <= b and max(abs(start-a),abs(end-a),abs(start-b),abs(end-b)) <= 90
    gs = [(p['t'],p['p']) for p in gold.get('points',[]) if positive(p.get('t')) and positive(p.get('p')) and p['t']<=now and max(abs(start-p['t']),abs(end-p['t']))<=90]
    closes = r['indicators']['quote'][0]['close']
    fs = [(t,closes[i] if currency=="CHF" else 1/closes[i]) for i,t in enumerate(r.get('timestamp',[])) if i<len(closes) and positive(t) and positive(closes[i]) and fits(t,t+60)]
    pairs = [(g,f) for g in gs for f in fs if max(g[0],f[0]+60,end)-min(g[0],f[0],start) <= 90]
    if not pairs:
        return dict(available=False,reason='Kein vollständiges Gold-/FX-Paar innerhalb von 90 Sekunden zur Originalzeit. Neueren Kurs-Screenshot verwenden; alte Kurse werden nicht ersetzt.',originalTime=raw)
    g,f = max(pairs,key=lambda p:min(p[0][0],p[1][0]))
    iso=lambda t:datetime.fromtimestamp(t,timezone.utc).isoformat()
    return dict(available=True,isEstimate=True,isExchangeRealtime=False,originalTime=raw,
                currency=currency,timezone='Europe/Zurich',timezoneAssumed=True,goldReference=g[1],fxReference=f[1],
                goldAt=iso(g[0]),fxStart=iso(f[0]),fxEnd=iso(f[0]+60),
                maxSkewSeconds=round(max(end,g[0],f[0]+60)-min(start,g[0],f[0]),3),
                goldSource='XAUS · gespeicherte Gold-API Spot-Beobachtung',goldUrl=GOLD_URL,
                fxSource='Yahoo Finance · USD/CHF abgeschlossener Minutenkurs' if currency=='CHF' else 'Yahoo Finance · EUR/USD abgeschlossener Minutenkurs, USD/EUR = 1 / EUR/USD',
                fxUrl='https://finance.yahoo.com/quote/'+('USDCHF=X' if currency=='CHF' else 'EURUSD=X')+'/',
                note='Historische Näherungsreferenz; Gold-Beobachtung kann vor oder nach der Screenshotzeit liegen. Sekunden nicht ergänzt. Zeitzone Schweiz angenommen. Kein bestätigter Echtzeit- oder Ausführungskurs. FX am Ausstieg bleibt eine Annahme.')

def historical_lookup(raw,currency="EUR"):
    global _cache,_chf_cache
    if currency not in ('EUR','CHF'):raise ValueError('Produktwährung muss EUR oder CHF sein')
    screenshot_interval(raw)
    with _lock:
        cached=_chf_cache if currency=='CHF' else _cache
        if cached is None or time.monotonic()-cached[0]>120:
            with ThreadPoolExecutor(max_workers=2) as pool:
                g=pool.submit(issuer_json,GOLD_URL,'https://xaus.com/',12)
                url=FX_URL.replace('EURUSD=X','USDCHF=X') if currency=='CHF' else FX_URL
                f=pool.submit(issuer_json,url,'https://query1.finance.yahoo.com/',12)
                cached=(time.monotonic(),g.result(),f.result())
            if currency=='CHF':_chf_cache=cached
            else:_cache=cached
        return align(raw,cached[1],cached[2],currency=currency)


def align_live(raw, gold, fx, now=None, currency="EUR"):
    """Use actual source timestamps; never substitute retrieval time."""
    if currency not in ("EUR","CHF"):raise ValueError("Produktwährung muss EUR oder CHF sein")
    now = time.time() if now is None else now
    start,end = screenshot_interval(raw)
    if (gold.get('stale') is not False or gold.get('data_state',{}).get('status')!='fresh'
        or gold.get('xau',{}).get('currency')!='USD' or gold.get('xau',{}).get('unit')!='troy_oz'
        or fx.get('result')!='success' or fx.get('base')!='USD'
        or fx.get('source')!='live' or fx.get('sources',{}).get(currency)!='live'
        or fx.get('market_session')!='open'):
        raise ValueError('Live-Gold-/FX-Identität oder Aktualität nicht bestätigt')
    def stamp(raw):
        dt=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError('Quellenzeitzone fehlt')
        return dt.timestamp()
    gt=stamp(gold.get('price_as_of'));ft=stamp(fx.get('effective_at',{}).get(currency));updated=stamp(fx.get('data_updated_at'))
    gp=gold.get('spot_usd_oz');rate=fx.get('rates',{}).get(currency)
    times=[start,end,gt,ft,updated]
    if not positive(gp) or not positive(rate):raise ValueError('Positive Live-Werte fehlen')
    if any(t>now or now-t>90 for t in times) or max(times)-min(times)>90:
        return dict(available=False,reason='Live-Quellen liegen nicht gemeinsam innerhalb von 90 Sekunden zur Produktreferenz.')
    iso=lambda t:datetime.fromtimestamp(t,timezone.utc).isoformat()
    return dict(available=True,isEstimate=True,isExchangeRealtime=False,originalTime=raw,
        currency=currency,timezone='UTC',timezoneAssumed=False,goldReference=gp,fxReference=rate,
        goldAt=iso(gt),fxStart=iso(ft),fxEnd=iso(ft),fxDataAt=iso(updated),
        maxSkewSeconds=round(max(times)-min(times),3),
        goldSource='XAUS · datierte Gold-Spot-Beobachtung',goldUrl='https://xaus.com/api/v1/spot?compact=1',
        fxSource=fx.get('provider','Datierter USD/'+currency+'-Kurs'),
        fxUrl='https://biquote.io/' if fx.get('backupActive') else 'https://api.exchangerate.dev/',
        note='Zeitlich abgeglichene Live-Beobachtungen; indikative Modellreferenz, kein ausführbarer Produktkurs. FX am Ausstieg bleibt eine Annahme.')

def lookup(raw,currency="EUR"):
    if currency not in ("EUR","CHF"):raise ValueError("Produktwährung muss EUR oder CHF sein")
    # Recent issuer observations must not depend on a delayed minute archive.
    start,end=screenshot_interval(raw)
    now=time.time()
    if start>now:raise ValueError('Kurszeit liegt in der Zukunft')
    live_reason=None
    if now-start<=90:
        try:
            from sg_quotes import market_input
            with ThreadPoolExecutor(max_workers=2) as pool:
                g=pool.submit(market_input,'spot');f=pool.submit(market_input,'fx')
                live=align_live(raw,g.result(),f.result(),currency=currency)
            if live['available']:return live
            live_reason=live['reason']
        except (OSError,ValueError,KeyError,TypeError) as exc:
            live_reason='Live-Referenz: '+str(exc)
    result=historical_lookup(raw) if currency=='EUR' else historical_lookup(raw,currency=currency)
    if not result.get('available') and live_reason:result['reason']+=' '+live_reason
    return result
