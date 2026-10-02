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

def screenshot_interval(raw):
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

def align(raw, gold, fx, now=None):
    now = time.time() if now is None else now
    start, end = screenshot_interval(raw)
    if start > now:
        raise ValueError('Kurszeit liegt in der Zukunft')
    if gold.get('symbol') != 'xau' or gold.get('currency') != 'USD' or gold.get('unit') != 'troy_oz':
        raise ValueError('Gold-Spot-Identität nicht bestätigt')
    r = fx['chart']['result'][0]
    if r['meta'].get('symbol') != 'EURUSD=X' or r['meta'].get('currency') != 'USD' or r['meta'].get('instrumentType') != 'CURRENCY' or r['meta'].get('dataGranularity') != '1m':
        raise ValueError('EUR/USD-Minutenhistorie nicht bestätigt')
    def fits(a,b):
        return b <= now and a <= b and max(abs(start-a),abs(end-a),abs(start-b),abs(end-b)) <= 90
    gs = [(p['t'],p['p']) for p in gold.get('points',[]) if positive(p.get('t')) and positive(p.get('p')) and p['t']<=now and max(abs(start-p['t']),abs(end-p['t']))<=90]
    closes = r['indicators']['quote'][0]['close']
    fs = [(t,1/closes[i]) for i,t in enumerate(r.get('timestamp',[])) if i<len(closes) and positive(t) and positive(closes[i]) and fits(t,t+60)]
    pairs = [(g,f) for g in gs for f in fs if max(g[0],f[0]+60,end)-min(g[0],f[0],start) <= 90]
    if not pairs:
        return dict(available=False,reason='Kein vollständiges Gold-/FX-Paar innerhalb von 90 Sekunden zur Originalzeit. Neueren Kurs-Screenshot verwenden; alte Kurse werden nicht ersetzt.',originalTime=raw)
    g,f = max(pairs,key=lambda p:min(p[0][0],p[1][0]))
    iso=lambda t:datetime.fromtimestamp(t,timezone.utc).isoformat()
    return dict(available=True,isEstimate=True,isExchangeRealtime=False,originalTime=raw,
                timezone='Europe/Zurich',timezoneAssumed=True,goldReference=g[1],fxReference=f[1],
                goldAt=iso(g[0]),fxStart=iso(f[0]),fxEnd=iso(f[0]+60),
                maxSkewSeconds=round(max(end,g[0],f[0]+60)-min(start,g[0],f[0]),3),
                goldSource='XAUS · gespeicherte Gold-API Spot-Beobachtung',goldUrl=GOLD_URL,
                fxSource='Yahoo Finance · EUR/USD abgeschlossener Minutenkurs, USD/EUR = 1 / EUR/USD',
                fxUrl='https://finance.yahoo.com/quote/EURUSD=X/',
                note='Historische Näherungsreferenz; Gold-Beobachtung kann vor oder nach der Screenshotzeit liegen. Sekunden nicht ergänzt. Zeitzone Schweiz angenommen. Kein bestätigter Echtzeit- oder Ausführungskurs. FX am Ausstieg bleibt eine Annahme.')

def lookup(raw):
    global _cache
    screenshot_interval(raw)
    with _lock:
        if _cache is None or time.monotonic()-_cache[0] > 120:
            with ThreadPoolExecutor(max_workers=2) as pool:
                g=pool.submit(issuer_json,GOLD_URL,'https://xaus.com/',12)
                f=pool.submit(issuer_json,FX_URL,'https://query1.finance.yahoo.com/',12)
                _cache=(time.monotonic(),g.result(),f.result())
        return align(raw,_cache[1],_cache[2])
