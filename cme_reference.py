"""Dated COMEX GCZ26 reference from CME's public delayed quote response.

Only the exchange's original trade update is used, never response time. This
adapter supplies anchors, not technical candles or a realtime exchange claim.
"""
import copy
import json
import math
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

URL = 'https://www.cmegroup.com/CmeWS/mvc/quotes/v2/437'
PAGE = 'https://www.cmegroup.com/markets/metals/precious/gold.quotes.html'
_lock = threading.Lock()
_cache = None
_next_fetch = 0
_failures = 0
_error = None


def parse(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, dict) or payload.get('quoteDelayed') is not True:
        raise ValueError('CME: Kennzeichnung des verzögerten Börsenkurses fehlt')
    rows = payload.get('quotes')
    if not isinstance(rows, list):
        raise ValueError('CME: Kontraktdaten fehlen')
    matches = [r for r in rows if isinstance(r, dict) and r.get('quoteCode') == 'GCZ6']
    if len(matches) != 1:
        raise ValueError('CME: Dezember-2026-Kontrakt fehlt oder ist mehrdeutig')
    r = matches[0]
    if (r.get('productId') != 437 or r.get('productCode') != 'GC'
            or r.get('productName') != 'Gold Futures' or r.get('exchangeCode') != 'XCEC'
            or r.get('expirationMonth') != 'DEC 2026' or r.get('expirationCode') != 'Z6'
            or r.get('mdKey') != 'GCZ6-XCEC-G'
            or not str(r.get('lastTradeDate', '')).startswith('2026-12-29T')):
        raise ValueError('CME: GCZ26-Kontraktidentität nicht bestätigt')
    value = r.get('last')
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError('CME: Letzter Börsenkurs fehlt')
    try:
        price = float(value)
        raw_at = r['updated']
        if not isinstance(raw_at, str): raise ValueError()
        at = datetime.fromisoformat(raw_at.replace('Z', '+00:00'))
        if at.tzinfo is None: raise ValueError()
    except (KeyError, ValueError, TypeError, OverflowError):
        raise ValueError('CME: Börsenkurs oder Original-Kurszeit ungültig') from None
    if not math.isfinite(price) or price <= 0:
        raise ValueError('CME: Börsenkurs ungültig')
    if not 0 <= (now-at).total_seconds() <= 1800:
        raise ValueError('CME: GCZ26-Kurs älter als 30 Minuten oder zukünftig')
    return dict(contract='GCZ26', underlying='Gold Future Dec 2026', underlyingType='FUTURE',
                underlyingPriceUsd=price, underlyingAt=at.astimezone(timezone.utc).isoformat(),
                source='CME Group · COMEX GCZ26 · verzögerter Börsenkurs', sourceUrl=PAGE,
                isExchangeRealtime=False, eligible=False)


def fetch_reference():
    global _cache, _next_fetch, _failures, _error
    with _lock:
        if time.monotonic() < _next_fetch:
            if _cache is not None:
                # Revalidate age without ever changing the original timestamp.
                return parse(copy.deepcopy(_cache))
            raise OSError('CME reference cooldown')
        try:
            req = Request(URL, headers={'User-Agent': 'Bob/2.0 delayed gold reference',
                                        'Accept': 'application/json'})
            with urlopen(req, timeout=10) as response:
                if response.url != URL:
                    raise ValueError('CME: Unerwartete Weiterleitung')
                body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError('CME: Antwort zu groß')
            payload = json.loads(body)
            result = parse(payload)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            _failures += 1
            delay = min(1800, 60 * 2**min(_failures, 5))
            if isinstance(exc, HTTPError):
                _error = 'CME: Datenanbieter antwortet mit HTTP '+str(exc.code)
                if exc.code == 429:
                    from future_analysis import retry_delay
                    delay = retry_delay(exc, _failures)
                elif exc.code in (401, 403):
                    delay = 3600
            else:
                _error = (str(exc) if isinstance(exc, ValueError) and str(exc).startswith('CME:')
                          else 'CME: Referenzabruf fehlgeschlagen')
            _cache = None
            _next_fetch = time.monotonic() + delay
            raise
        _cache, _failures, _error = copy.deepcopy(payload), 0, None
        _next_fetch = time.monotonic() + 60
        return result


def failure():
    with _lock:
        return max(60, math.ceil(_next_fetch-time.monotonic())), (_error or 'CME: Referenz momentan nicht verfügbar')
