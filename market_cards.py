"""Display-only gold quotes. Never feed card data into trade authorization."""
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen

_lock = threading.Lock()
_cache = None
_cached_at = 0


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def parse_quote(payload, symbol, now=None):
    now = time.time() if now is None else now
    meta = payload['chart']['result'][0]['meta']
    if (meta.get('symbol') != symbol or meta.get('currency') != 'USD'
            or meta.get('instrumentType') != 'FUTURE'):
        raise ValueError('Quote identity mismatch')
    price, at = meta.get('regularMarketPrice'), meta.get('regularMarketTime')
    if not positive(price) or not positive(at) or at > now + 5:
        raise ValueError('Invalid quote or timestamp')
    # range=1d is intentional: never use the start of a multi-day chart as yesterday's close.
    previous = meta.get('previousClose', meta.get('chartPreviousClose'))
    change = (price / previous - 1) * 100 if positive(previous) else None
    return dict(price=price, at=datetime.fromtimestamp(at, timezone.utc).isoformat(),
                changePct=change, previousClose=previous if positive(previous) else None,
                symbol=symbol, source='Yahoo Finance', kind='reference',
                note='Echtzeit nicht bestätigt', changeLabel='zum Vortagesschluss')


def fetch_quote(symbol):
    request = Request('https://query2.finance.yahoo.com/v8/finance/chart/' + symbol + '?interval=1d&range=1d',
                      headers={'User-Agent': 'Mozilla/5.0 (Bob gold cards)', 'Accept': 'application/json'})
    with urlopen(request, timeout=6) as response:
        return parse_quote(json.loads(response.read(500000)), symbol)


def fetch_spot():
    # Existing Bob source. It does not publish a previous close; never substitute
    # its chart endpoint here (that can contain futures rather than spot bars).
    request = Request('https://xaus.com/api/v1/spot?compact=1', headers={'User-Agent': 'Bob/1.3'})
    with urlopen(request, timeout=6) as response:
        payload = json.loads(response.read(500000))
    xau = payload.get('xau', {})
    price, at = payload.get('spot_usd_oz'), payload.get('price_as_of')
    if xau.get('currency') != 'USD' or xau.get('unit') != 'troy_oz' or not positive(price):
        raise ValueError('Spot identity mismatch')
    stamp = datetime.fromisoformat(at.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.timestamp() > time.time() + 5:
        raise ValueError('Invalid spot time')
    return dict(price=price, at=at, changePct=None, symbol='XAU/USD', source='XAUS · Gold-API',
                kind='spot', note='Letzter Stand · Quelle veraltet' if payload.get('stale') is not False else 'Spot · Quellenzeit')


def unavailable(symbol):
    return dict(price=None, at=None, changePct=None, symbol=symbol,
                source='', kind='unavailable', note='Kurs momentan nicht verfügbar')


def snapshot():
    global _cache, _cached_at
    with _lock:
        if _cache is not None and time.monotonic() - _cached_at < 30:
            return _cache
        result = dict(spot=unavailable('XAU/USD'), future=unavailable('GCZ26'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {'spot': pool.submit(fetch_spot), 'future': pool.submit(fetch_quote, 'GCZ26.CMX')}
            for key, job in jobs.items():
                try:
                    result[key] = job.result()
                except (OSError, ValueError, KeyError, TypeError, IndexError):
                    pass
        # Reuse Bob's existing model, preserving its freshness and contract checks.
        if result['future']['price'] is None:
            try:
                import future_estimate
                estimate = future_estimate.current_estimate({'contract': 'GCZ26'})
                if estimate.get('available'):
                    result['future'].update(price=estimate['priceUsd'], at=estimate['priceAt'],
                        source=estimate.get('proxySource', ''), kind='calculated',
                        note='Berechneter Kurs · keine Börsenquotierung')
            except (OSError, ValueError, KeyError, TypeError):
                pass
        _cache, _cached_at = result, time.monotonic()
        return result
