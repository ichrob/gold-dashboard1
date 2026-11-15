"""Shared background Investing.com Gold CFD feed; never a GCZ26 exchange quote."""
import json
import math
import re
import html
import time
import threading
import background_push
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

URL = 'https://de.investing.com/commodities/gold'
_fetch_lock = threading.Lock()
_cached = None
_last_observed = None
_chart_observations = []
_next_fetch = 0
_thread = None
_state_lock = threading.Lock()
_health = {"state": "starting", "lastCheckedAt": None, "sourceAt": None,
           "providerMarketOpen": None, "failureCode": None, "failureAt": None}
POLL_SECONDS = 30
PROVIDER_CLOSE_ERROR_GRACE_SECONDS = 65 * 60

class FetchCooldownError(OSError):
    """Shared 30s poll was already attempted; keep that original error code."""


def failure_code(exc):
    """Bounded public failure reason; never expose provider HTML or secrets."""
    if isinstance(exc, FetchCooldownError):
        return None
    if isinstance(exc, HTTPError):
        return ('http-' + str(exc.code) if exc.code in (401, 403, 404, 429, 500, 502, 503, 504)
                else 'http-other')
    if isinstance(exc, TimeoutError):
        return 'provider-timeout'
    if isinstance(exc, URLError):
        return 'provider-timeout' if isinstance(exc.reason, TimeoutError) else 'provider-network'
    if isinstance(exc, UnicodeError):
        return 'provider-decode'
    if isinstance(exc, ValueError):
        return 'provider-content-invalid'
    if isinstance(exc, OSError):
        return 'provider-network'
    return 'provider-exception'




def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)



def _public_page_explicit_troy_ounce(body):
    """Strictly verify the visible German unit on the same identified page.

    Investing.com has stopped populating commodityData.unit in some pages.
    Never trust strings embedded only in scripts or an arbitrary unit label.
    """
    visible = re.sub(r'(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>',
                     ' ', body)
    visible = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', visible)))
    return bool(re.search(r'\bEinheit\s*:?\s*.{0,110}?\b1\s+Feinunze\b',
                          visible, re.I))


def parse(body, now=None):
    now = time.time() if now is None else now
    match = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not match:
        raise ValueError('Investing.com Kursdaten fehlen')
    store = json.loads(match[1])['props']['pageProps']['state']['commodityStore']
    instrument = store['instrument']
    base, quote = instrument['base'], instrument['price']
    if (str(store['instrumentId']) != '8830' or str(base['id']) != '8830'
            or base['path'] != '/commodities/gold' or base['isCfd'] is not True
            or base['isActive'] is not True or quote['currency'] != 'USD'
            ):
        raise ValueError('Gold-CFD Identität nicht bestätigt')
    commodity_data = instrument.get('commodityData') or {}
    unit = commodity_data.get('unit') if isinstance(commodity_data, dict) else None
    if unit == '_instr_unit_troy_ounce':
        unit_evidence = 'provider-json'
    elif unit is None and _public_page_explicit_troy_ounce(body):
        # Preserve instrument 8830, active CFD, gold path, USD and provider
        # timestamp checks above. An explicitly different unit is never OK.
        unit_evidence = 'provider-visible-1-feinunze'
    else:
        raise ValueError('Gold-CFD Feinunzen-Einheit nicht bestätigt')
    raw = str(quote['lastUpdateTime'])
    if not re.fullmatch(r'\d{13}', raw):
        raise ValueError('CFD Quellenzeit fehlt')
    epoch = int(raw) / 1000
    price = quote['last']
    if not numeric(price) or price <= 0 or epoch > now + 5:
        raise ValueError('CFD Kurs oder Quellenzeit ungültig')
    fresh = 0 <= now - epoch <= 120
    paused = background_push.weekend_quote_at_close(now * 1000, epoch * 1000)
    realtime = fresh and not paused and base.get('isOpen') is True and quote.get('isDelayed') is False
    note = ('Echtzeit CFD · laut Investing.com' if realtime else
            'Markt geschlossen · letzter CFD-Kurs' if paused or base.get('isOpen') is False else
            'CFD-Kurs verzögert' if quote.get('isDelayed') is True else
            'CFD-Kurs nicht aktuell' if not fresh else 'CFD · Echtzeitstatus unbestätigt')
    metrics = store.get('keyMetrics', {})
    december = (metrics.get('month') in ('Dec 26', 'Dez. 2026')
                and metrics.get('settlement_day') == '2026-12-29T00:00:00Z'
                and metrics.get('last_rollover_day') == '2026-08-27T00:00:00Z')
    return dict(price=price, at=datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                declaredContract='GCZ26' if december else None,
                changePct=quote.get('changePcr') if numeric(quote.get('changePcr')) else None,
                change=quote.get('change') if numeric(quote.get('change')) else None,
                symbol='Gold CFD', source='Investing.com', sourceUrl=URL, kind='cfd',
                unitEvidence=unit_evidence,
                note=note, realtimeCfd=realtime,
                providerMarketOpen=base.get('isOpen') if type(base.get('isOpen')) is bool else None,
                isExchangeRealtime=False,
                changeLabel='zum Vortagesschluss')


def _fetch():
    request = Request(URL + '?_bob_ts=' + str(int(time.time() // POLL_SECONDS)), headers={'User-Agent': 'Mozilla/5.0 (Bob gold cards)',
                                   'Accept': 'text/html', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=6) as response:
        if response.url.split('?', 1)[0] != URL:
            raise ValueError('Unerwartete CFD-Weiterleitung')
        body = response.read(2000001)
        if len(body) > 2000000:
            raise ValueError('CFD Seite zu groß')
        return parse(body.decode('utf-8'))


def fetch():
    """Share one bounded request between the display and the shadow study."""
    global _cached, _next_fetch, _last_observed
    with _fetch_lock:
        if time.monotonic() < _next_fetch:
            if _cached is None:raise FetchCooldownError('CFD-Abruf pausiert nach Quellenfehler')
            return aged(_cached)
        _cached = None
        # Count from request start, so a six-second fetch does not accidentally
        # turn a 30-second worker into a 60-second polling cadence.
        _next_fetch = time.monotonic() + POLL_SECONDS
        q = _fetch()
        if _last_observed:
            at = datetime.fromisoformat(q['at'])
            before = datetime.fromisoformat(_last_observed['at'])
            if at < before or (at == before and q['price'] != _last_observed['price']):
                raise ValueError('CFD-Quelle liefert einen älteren oder widersprüchlichen Kursstand')
        if not _chart_observations or q['at'] != _chart_observations[-1]['at']:
            _chart_observations.append(dict(q))
            del _chart_observations[:-20160]
        _last_observed = dict(q)
        _cached = q
        return aged(_cached)


def aged(quote, now=None):
    """Cached quotes keep the original source time and lose stale eligibility."""
    now = time.time() if now is None else now
    q = dict(quote)
    age = now - datetime.fromisoformat(q['at']).timestamp()
    if q.get('providerMarketOpen') is False:
        q['realtimeCfd'] = False
        q['note'] = 'CFD-Markt laut Anbieter geschlossen · letzter Kurs'
    elif background_push.weekend_quote_at_close(now * 1000, datetime.fromisoformat(q['at']).timestamp() * 1000):
        q['realtimeCfd'] = False
        q['note'] = 'Markt geschlossen · letzter CFD-Kurs'
    elif not 0 <= age <= 120:
        q['realtimeCfd'] = False
        q['note'] = 'CFD-Kurs nicht aktuell'
    return q


def collect_once():
    try:
        q = fetch()
        source_ms = datetime.fromisoformat(q['at']).timestamp() * 1000
        state = ('closed' if q.get('providerMarketOpen') is False or
                 background_push.weekend_quote_at_close(time.time() * 1000, source_ms)
                 else 'current' if q.get('realtimeCfd') else 'stale')
        with _state_lock:
            _health.update(state=state, lastCheckedAt=time.time(), successfulAt=time.time(), sourceAt=q['at'],
                           providerMarketOpen=q.get('providerMarketOpen'),
                           failureCode=None, failureAt=None)
        print('BOB_CFD checked state='+state+' source_at='+q['at'], flush=True)
    except Exception as exc:
        now = time.time()
        code = failure_code(exc)
        with _state_lock:
            successful = _health.get('successfulAt')
            recently_closed = (
                background_push.degiro_session() == 'night'
                and _health.get('providerMarketOpen') is False
                and isinstance(successful, (int, float))
                and 0 <= now - successful <= PROVIDER_CLOSE_ERROR_GRACE_SECONDS)
            # The provider can close its page connection during the daily
            # market pause after first declaring the market closed. Preserve
            # that last confirmed state only for the bounded pause window;
            # outside it, fail closed as unavailable.
            _health.update(state='closed' if recently_closed else 'unavailable',
                           lastCheckedAt=now)
            if code is not None:
                _health.update(failureCode=code, failureAt=now)
            current_code = _health.get('failureCode') or 'unknown'
        print('BOB_CFD error='+type(exc).__name__+' code='+current_code, flush=True)


def _collect(stop=None):
    stop = stop or threading.Event()
    while not stop.is_set():
        remaining = background_push.gold_weekend_seconds_remaining()
        if remaining:
            with _state_lock:
                if _health['state'] != 'unavailable':
                    source = _health.get('sourceAt')
                    source_ms = datetime.fromisoformat(source).timestamp() * 1000 if source else None
                    _health['state'] = ('closed' if background_push.weekend_quote_at_close(time.time() * 1000, source_ms)
                                        else 'paused')
                _health['lastCheckedAt'] = time.time()
            print('BOB_CFD weekend_paused', flush=True)
            stop.wait(remaining)
            continue
        started = time.monotonic()
        collect_once()
        interval = background_push.degiro_poll_seconds()
        stop.wait(max(1, interval-(time.monotonic()-started)))


def start():
    """Run independently of browser login and the 06–22 comparison window."""
    global _thread
    with _state_lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_collect, name='bob-cfd-feed', daemon=True)
            _thread.start()


def health():
    with _state_lock:
        actual_interval = 300 if background_push.degiro_session() == 'night' else POLL_SECONDS
        result = dict(_health, running=bool(_thread and _thread.is_alive()), intervalSeconds=actual_interval,
                      sessionMode=background_push.degiro_session())
    if result['sourceAt']:
        now = time.time()
        age = now-datetime.fromisoformat(result['sourceAt']).timestamp()
        result['sourceAgeSeconds'] = round(age)
        checked = result.get('lastCheckedAt')
        checked_recently = (isinstance(checked, (int, float)) and
                            0 <= now-checked <= max(120, actual_interval*2+50))
        if result['state'] != 'unavailable' and result.get('providerMarketOpen') is False and checked_recently:
            # A provider-declared close may legitimately retain an older quote.
            # Require a recent successful source check so a stuck worker cannot
            # hide behind that closed flag indefinitely.
            result['state'] = 'closed'
        elif result['state'] != 'unavailable' and background_push.weekend_quote_at_close(now * 1000, datetime.fromisoformat(result['sourceAt']).timestamp() * 1000):
            result['state'] = 'closed'
        elif result['state'] in ('current', 'closed') and not 0 <= age <= 120:
            result['state'] = 'stale'
    return result


def chart_snapshot(tf):
    """Sampled CFD candles, not exchange OHLC. Original quote times retained."""
    steps={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400}
    step=steps.get(tf,900)*1000
    with _fetch_lock:quotes=list(_chart_observations)
    bars={}
    for q in quotes:
        at=int(datetime.fromisoformat(q['at']).timestamp()*1000);key=at//step*step;p=q['price']
        if key not in bars:bars[key]=dict(openTime=key,open=p,high=p,low=p,close=p,instrument='GOLD-CFD',source='Investing.com · 30-Sekunden-Beobachtungen',isOpen=key+step>time.time()*1000,samples=0)
        b=bars[key];b.update(high=max(b['high'],p),low=min(b['low'],p),close=p,sourceAt=q['at'],samples=b['samples']+1)
    return dict(bars=list(bars.values())[-300:],note='Aus beobachteten Kursen seit Serverstart; keine vollständigen historischen OHLC-Kerzen',sourceAt=quotes[-1]['at'] if quotes else None)
