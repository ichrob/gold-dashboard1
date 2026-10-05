"""Display-only change against Investing.com's explicit XAU/USD previous close."""
import json
import math
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

URL = 'https://de.investing.com/currencies/xau-usd'
_lock = threading.Lock()
_thread = None
_reference = None


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def parse(body, now=None):
    now = time.time() if now is None else now
    match = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not match:
        raise ValueError('Spot-Vortagesschluss fehlt')
    instrument = json.loads(match[1])['props']['pageProps']['state']['currencyStore']['instrument']
    base, quote = instrument['base'], instrument['price']
    if (str(base['id']) != '68' or base['path'] != '/currencies/xau-usd'
            or base['isCfd'] is not False or base['type'] != 'currency'
            or instrument['name']['shortName'] != 'XAU/USD'
            or instrument['isFuture'] is not False or quote['currency'] != 'USD'):
        raise ValueError('Spot-Identität nicht bestätigt')
    raw = str(quote['lastUpdateTime'])
    if not re.fullmatch(r'\d{13}', raw):
        raise ValueError('Spot-Quellenzeit fehlt')
    at = int(raw)/1000
    if not 0 <= now-at <= 300 or not positive(quote.get('lastClose')):
        raise ValueError('Spot-Vergleichskurs oder Quellenzeit ungültig')
    return dict(previousClose=quote['lastClose'], observedAt=at,
                source='Investing.com · XAU/USD', sourceUrl=URL)


def refresh():
    global _reference
    request = Request(URL+'?_bob_ts='+str(int(time.time()//60)), headers={'User-Agent':'Mozilla/5.0 (Bob spot change)', 'Cache-Control':'no-cache'})
    with urlopen(request, timeout=6) as response:
        if response.url.split('?',1)[0] != URL:
            raise ValueError('Unerwartete Spot-Weiterleitung')
        body = response.read(2000001)
        if len(body)>2000000:
            raise ValueError('Spot-Seite zu groß')
        reference = parse(body.decode('utf-8'))
    with _lock:
        if _reference and reference['observedAt'] < _reference['observedAt']:
            raise ValueError('Spot-Vergleichszeit rückläufig')
        _reference = reference
    print('BOB_SPOT_CHANGE reference_checked source_at='+datetime.fromtimestamp(reference['observedAt'],timezone.utc).isoformat()+' previous_close='+str(reference['previousClose']), flush=True)


def change(price, at, now=None):
    """Calculate from Bob's exact displayed spot; never replace that quote."""
    now = time.time() if now is None else now
    with _lock:
        reference = dict(_reference) if _reference else None
    if not reference or not positive(price):
        return None
    try:
        quote_at = datetime.fromisoformat(at.replace('Z','+00:00'))
        ref_at = datetime.fromtimestamp(reference['observedAt'],timezone.utc)
        if quote_at.tzinfo is None or not 0 <= now-quote_at.timestamp() <= 120 or not 0 <= now-ref_at.timestamp() <= 300:
            return None
        # Never carry a previous-close basis across the NY FX day boundary.
        ny = ZoneInfo('America/New_York')
        if (quote_at.astimezone(ny)-timedelta(hours=17)).date() != (ref_at.astimezone(ny)-timedelta(hours=17)).date():
            return None
        return dict(changePct=(price/reference['previousClose']-1)*100,
                    changeLabel='zum Spot-Vortagesschluss (Investing.com)', **reference)
    except (ValueError, TypeError, AttributeError):
        return None


def _run():
    while True:
        started=time.monotonic()
        try:refresh()
        except Exception as exc:print('BOB_SPOT_CHANGE error='+type(exc).__name__,flush=True)
        threading.Event().wait(max(1,60-(time.monotonic()-started)))


def start():
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_run,name='bob-spot-change',daemon=True)
            _thread.start()
