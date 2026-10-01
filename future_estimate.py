"""GCZ26 nowcast using an exact-contract anchor and Gold-API spot changes.

No fitted beta, synthetic history, API key, or exchange-realtime claim. The runtime
spot model assumes a constant Future/Spot factor between anchors. The old CFD
parser/model remains available for regression checks but is no longer fetched. Only observations actually collected by this process are aligned.
"""
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import estimate_quality

URL = 'https://www.investing.com/commodities/gold'
CONTRACT = 'GCZ26'
POLL_SECONDS = 30
MAX_PROXY_AGE = 60
MAX_REFERENCE_AGE = 1800
MAX_ALIGNMENT = 30
MAX_GAP = 90
_lock = threading.Lock()
_ticks = []
_spot_ticks = []
_spot_source_error = 'Investing.com ersetzt durch Gold-API.com'
_thread = None
_active_until = 0
_source_error = None


def stamp(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('Kurszeit ohne Zeitzone')
    return at.astimezone(timezone.utc)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Ungültiger Kurs')
    return float(value)


def parse_page(body, now=None):
    now = now or datetime.now(timezone.utc)
    match = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not match:
        raise ValueError('Investing.com Kursdaten fehlen')
    state = json.loads(match[1])['props']['pageProps']['state']['commodityStore']
    instrument, metrics = state['instrument'], state['keyMetrics']
    base, price = instrument['base'], instrument['price']
    # GC1! is the site's CFD label, not evidence of an exchange contract.
    # Check the declared contract month, expiry AND rollover to pin the proxy.
    if (str(state['instrumentId']) != '8830' or str(base['id']) != '8830'
            or base['path'] != '/commodities/gold' or base['isCfd'] is not True
            or base['isOpen'] is not True or base['isActive'] is not True
            or price['currency'] != 'USD' or price['isDelayed'] is not False
            or instrument['commodityData']['unit'] != '_instr_unit_troy_ounce'
            or metrics['month'] != 'Dec 26'
            or stamp(metrics['settlement_day']).date().isoformat() != '2026-12-29'
            or stamp(metrics['last_rollover_day']).date().isoformat() != '2026-08-27'):
        raise ValueError('CFD-Identität, Marktstatus oder Dezember-Kontrakt nicht bestätigt')
    raw_time = str(price['lastUpdateTime'])
    if not re.fullmatch(r'\d{13}', raw_time):
        raise ValueError('CFD-Kurszeit fehlt')
    at = datetime.fromtimestamp(int(raw_time)/1000, timezone.utc)
    if not 0 <= (now-at).total_seconds() <= MAX_PROXY_AGE:
        raise ValueError('Investing.com CFD-Kurs veraltet oder Kurszeit zukünftig')
    return dict(price=number(price['last']), at=at.isoformat(), contract=CONTRACT,
                source='Investing.com · Gold-CFD (abgeleitet)', sourceUrl=URL,proxyKind='investing-cfd')


def fetch_tick():
    request = Request(URL, headers={'User-Agent': 'Bob/1.9 public price research',
                                   'Accept': 'text/html', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=12) as response:
        if response.url != URL:
            raise ValueError('Unerwartete CFD-Weiterleitung')
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise ValueError('CFD-Antwort zu groß')
    return parse_page(body.decode('utf-8'))


def record_tick(tick, now=None):
    global _source_error
    now = now or datetime.now(timezone.utc)
    at, price = stamp(tick['at']), number(tick['price'])
    if tick['contract'] != CONTRACT or not 0 <= (now-at).total_seconds() <= MAX_PROXY_AGE:
        raise ValueError('CFD-Beobachtung nicht aktuell')
    with _lock:
        # Out-of-order/cached pages do not refresh a quote or rewrite history.
        if _ticks and at <= stamp(_ticks[-1]['at']):
            if at == stamp(_ticks[-1]['at']) and price != _ticks[-1]['price']:
                raise ValueError('Widersprüchlicher CFD-Kurszeitstempel')
            return
        _ticks.append(dict(tick))
        _ticks[:] = [t for t in _ticks if (now-stamp(t['at'])).total_seconds() <= 3600][-240:]
        _source_error = None


GOLD_API_URL='https://api.gold-api.com/price/XAU'


def parse_gold_api(data, now=None):
    now=now or datetime.now(timezone.utc)
    # Provider contract: /price/XAU returns USD per troy ounce. Require the
    # explicit asset/currency fields and the actual price update timestamp.
    if (data['symbol']!='XAU' or data['name']!='Gold' or data['currency']!='USD'
            or isinstance(data['exchangeRate'],bool) or data['exchangeRate']!=1):
        raise ValueError('Gold-API Spot-Identität oder USD-Einheit nicht bestätigt')
    at=stamp(data['updatedAt'])
    if not 0 <= (now-at).total_seconds() <= MAX_PROXY_AGE:
        raise ValueError('Gold-API Spot-Kurs veraltet oder Kurszeit zukünftig')
    return dict(price=number(data['price']),at=at.isoformat(),contract=CONTRACT,
                proxyKind='gold-api-spot',underlying='XAU/USD',
                source='Gold-API.com · XAU/USD Spot',sourceUrl=GOLD_API_URL)


def fetch_spot_tick():
    from product_quotes import issuer_json
    return parse_gold_api(issuer_json(GOLD_API_URL,'https://api.gold-api.com/',timeout=12))


def record_spot_tick(tick, now=None):
    global _spot_source_error
    now=now or datetime.now(timezone.utc)
    at=stamp(tick['at']);number(tick['price'])
    if (tick.get('proxyKind')!='gold-api-spot' or tick.get('underlying')!='XAU/USD'
            or tick.get('contract')!=CONTRACT or not 0 <= (now-at).total_seconds() <= MAX_PROXY_AGE):
        raise ValueError('Gold-Spot-Beobachtung nicht aktuell oder Identität fehlt')
    with _lock:
        if _spot_ticks and at <= stamp(_spot_ticks[-1]['at']):
            if at == stamp(_spot_ticks[-1]['at']) and tick['price'] != _spot_ticks[-1]['price']:
                raise ValueError('Widersprüchlicher Gold-Spot-Kurszeitstempel')
            return
        _spot_ticks.append(dict(tick))
        _spot_ticks[:]=[t for t in _spot_ticks if (now-stamp(t['at'])).total_seconds()<=3600][-240:]
        _spot_source_error=None


def _collect():
    global _spot_source_error
    while True:
        started=time.monotonic()
        with _lock:active=started<_active_until
        if active:
            try:
                record_spot_tick(fetch_spot_tick())
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                error=str(exc) if isinstance(exc,ValueError) else 'Gold-API.com nicht erreichbar oder Datenformat geändert'
                with _lock:_spot_source_error=error
        # Respect the provider's documented 30-second cache interval.
        # This daemon never delays an /api/live request.
        threading.Event().wait(max(1,POLL_SECONDS-(time.monotonic()-started)))


def ensure_collector():
    global _thread, _active_until
    with _lock:
        _active_until = time.monotonic()+3600
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_collect, name='bob-future-spot', daemon=True)
            _thread.start()


def calculate(research, ticks, now=None, proxy_kind="investing-cfd"):
    now = now or datetime.now(timezone.utc)
    out = dict(available=False, kind='calculated-future', label='Berechneter Future-Kurs',
               contract=research.get('contract'), currency='USD', unit='troy_oz',
               isExchangeRealtime=False, eligible=False,
               formula='F(t₀) + [CFD(t) − CFD(t₀)]',
               note='Näherung bei konstantem Abstand zwischen Future und CFD. '
                    'Basisänderungen und Zeitversatz verursachen Abweichungen; Genauigkeit nicht garantiert.')
    try:
        if proxy_kind not in ('investing-cfd','gold-api-spot'):
            raise ValueError('Nicht unterstützte Näherungsquelle')
        out['proxyKind']=proxy_kind
        if proxy_kind=='gold-api-spot':
            out.update(formula='F(t₀) × Spot(t) / Spot(t₀)',
                       note='Näherung bei unverändertem Future/Spot-Faktor. Finanzierung, Basisänderungen und Zeitversatz können den tatsächlichen Future-Kurs verändern; Genauigkeit nicht garantiert.')
        if research['contract'] != CONTRACT:
            raise ValueError('Futures-Kontrakt nicht unterstützt')
        ref_at, ref_price = stamp(research['underlyingAt']), number(research['underlyingPriceUsd'])
        ref_age = (now-ref_at).total_seconds()
        out['referenceAgeSeconds'] = round(ref_age, 1)
        if not 0 <= ref_age <= MAX_REFERENCE_AGE:
            raise ValueError('Echter Future-Referenzkurs fehlt oder ist älter als 30 Minuten')
        rows = [(stamp(t['at']), number(t['price'])) for t in ticks if t['contract'] == CONTRACT and t.get('proxyKind','investing-cfd') == proxy_kind]
        if not rows:
            raise ValueError(('Gold-API Spot' if proxy_kind=='gold-api-spot' else 'CFD')+'-Erfassung startet; zeitgleiche Referenzbeobachtung fehlt noch')
        rows.sort()
        current_at, current = rows[-1]
        proxy_age = (now-current_at).total_seconds()
        out['proxyAgeSeconds'] = round(proxy_age, 1)
        if not 0 <= proxy_age <= MAX_PROXY_AGE:
            raise ValueError(('Gold-API Spot' if proxy_kind=='gold-api-spot' else 'CFD')+'-Bewegung nicht aktuell: Berechnung ausgesetzt')
        # The reference is delayed: both bracketing observations are already
        # known at calculation time. Interpolation aligns the reference time;
        # it does not pretend to observe the missing sub-second quote.
        left = [(at, p) for at, p in rows if 0 <= (ref_at-at).total_seconds() <= MAX_ALIGNMENT]
        right = [(at, p) for at, p in rows if 0 <= (at-ref_at).total_seconds() <= MAX_ALIGNMENT]
        if not left or not right:
            raise ValueError('Zeitgleicher '+('Gold-API Spot' if proxy_kind=='gold-api-spot' else 'CFD')+'-Referenzkurs fehlt noch (je höchstens 30 Sekunden Abstand)')
        anchor_at, left_price = left[-1]
        right_at, right_price = right[0]
        span = (right_at-anchor_at).total_seconds()
        weight = (ref_at-anchor_at).total_seconds()/span if span else 0
        anchor = left_price+weight*(right_price-left_price)
        path = [(at, p) for at, p in rows if anchor_at <= at <= current_at]
        if any((b[0]-a[0]).total_seconds() > MAX_GAP for a, b in zip(path, path[1:])):
            raise ValueError('Lücke in Quellenbeobachtungen: Berechnung ausgesetzt')
        if current_at < ref_at:
            raise ValueError('Quellenkurs liegt vor dem Future-Referenzzeitpunkt')
        estimate = ref_price*current/anchor if proxy_kind=='gold-api-spot' else ref_price+(current-anchor)
        if not math.isfinite(estimate) or estimate <= 0:
            raise ValueError('Ungültiges Berechnungsergebnis')
        out.update(available=True, priceUsd=round(estimate, 2), priceAt=current_at.isoformat(),
                   calculatedAt=now.isoformat(), referencePriceUsd=ref_price,
                   referenceAt=ref_at.isoformat(), proxyPriceUsd=current,
                   proxyReferencePriceUsd=anchor, proxyReferenceAt=ref_at.isoformat(),
                   proxyReferenceKind='observed' if not span else 'linear-interpolation',
                   proxyLeftAt=anchor_at.isoformat(), proxyRightAt=right_at.isoformat(),
                   alignmentSeconds=round(max((ref_at-anchor_at).total_seconds(),
                                              (right_at-ref_at).total_seconds()), 3),
                   proxyChangeUsd=round(current-anchor, 4), assumedBasisUsd=round(ref_price-anchor, 4),
                   proxySource='Gold-API.com · XAU/USD Spot' if proxy_kind=='gold-api-spot' else 'Investing.com · Gold-CFD (abgeleitet)',
                   proxySourceUrl=GOLD_API_URL if proxy_kind=='gold-api-spot' else URL,
                   assumedFutureSpotFactor=ref_price/anchor if proxy_kind=='gold-api-spot' else None,
                   referenceSource='onvista · datierter GCZ26-Basiswert')
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        out['reason'] = str(exc) if isinstance(exc, ValueError) else 'Pflichtdaten für die Kursberechnung fehlen'
    return out


def validation_key(contract,kind):
    # Separate empirical results when switching source or formula.
    return 'future:'+str(contract)+':'+('gold-api-spot-ratio-v1' if kind=='gold-api-spot' else 'cfd-change-v1')


def current_estimate(research, now=None):
    now=now or datetime.now(timezone.utc)
    with _lock:
        sources=[('investing-cfd',list(_ticks),_source_error),('gold-api-spot',list(_spot_ticks),_spot_source_error)]
    alternatives=[]
    for kind,ticks,error in sources:
        key=validation_key(research.get('contract'),kind)
        if research.get('underlyingPriceUsd') and research.get('underlyingAt'):
            estimate_quality.observe(key,research['underlyingPriceUsd'],research['underlyingAt'],now.isoformat())
        out=calculate(research,ticks,now,kind)
        rows=sorted(stamp(t['at']) for t in ticks if t.get('contract')==CONTRACT)
        out['collection']=dict(sampleCount=len(rows),
            coveredSeconds=round((rows[-1]-rows[0]).total_seconds(),1) if rows else 0,
            firstAt=rows[0].isoformat() if rows else None,lastAt=rows[-1].isoformat() if rows else None,
            currentFresh=bool(rows and 0 <= (now-rows[-1]).total_seconds() <= MAX_PROXY_AGE),maxGapSeconds=MAX_GAP)
        if out['available']:
            estimate_quality.record(key,out['priceUsd'],out['priceAt'],out['referenceAt'],now.isoformat())
            horizon=(stamp(out['priceAt'])-stamp(out['referenceAt'])).total_seconds()
            out['validation']=estimate_quality.quality(key,horizon,now)
            if out['validation']['ready']:out['comparisonErrorUsd']=max(.1,out['validation']['maxAbsoluteError'])
        if error:out['sourceStatus']=error
        alternatives.append(out)
    # Prefer empirically validated estimates, then smaller measured maximum
    # error. With no validation yet the CFD has priority when usable; spot is
    # a labelled fallback. Both models are shadow-measured independently.
    available=[v for v in alternatives if v['available']]
    if available:
        available.sort(key=lambda v:(not v.get('validation',{}).get('ready',False),
            v['validation'].get('maxAbsoluteError',float('inf')) if v.get('validation',{}).get('ready') else float('inf'),
            v['proxyKind']!='investing-cfd'))
        selected=dict(available[0])
    else:
        selected=dict(max(alternatives,key=lambda v:(v['collection']['currentFresh'],v['collection']['coveredSeconds'],v['collection']['sampleCount'],v['proxyKind']=='gold-api-spot')))
    selected['alternatives']=[dict(proxyKind=v['proxyKind'],available=v['available'],reason=v.get('reason'),
        validation=v.get('validation'),collection=v['collection'],sourceStatus=v.get('sourceStatus')) for v in alternatives]
    return selected
