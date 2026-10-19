"""Public SG/BNP LiveTrading observations; never a DEGIRO execution guarantee."""
import copy
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request

from public_product_terms import ORIGIN, open_public_page, plain, parse_page as parse_terms

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='comdirect-quotes')
_LOCK = threading.Lock()
_CACHE = {}
_PENDING = set()

# Exact issuer/venue bindings verified on comdirect product pages.
ISSUERS = {
    'Société Générale': ('SG', 'LT Societe Generale'),
    'BNP Paribas': ('BNP', 'LT BNP Paribas'),
}


def matches_primary(result, row):
    meta = result.get('metadata') or {}
    if row.get('currency') != 'EUR' or (result.get('currency') or meta.get('currency')) != 'EUR':
        return False
    if row.get('source') == 'comdirect · SG LiveTrading' and row.get('venue') == 'LT Societe Generale':
        return meta.get('issuerExchangeCode') == 'CBDE'
    if row.get('source') == 'comdirect · BNP LiveTrading' and row.get('venue') == 'LT BNP Paribas':
        return (str(result.get('source', '')).startswith('BNP Paribas ·')
                and result.get('sourceUrl') == 'https://derivate.bnpparibas.com/product-details/'+str(result.get('isin'))+'/')
    return False



def parse_page(html, isin, now=None):
    # Validate full product identity, currency and knockout status, not just a
    # search result mentioning the ISIN. Prices come from ONE labelled row.
    from comdirect_fields import parse_page as parse_fields
    terms = parse_fields(html, isin, now)
    observed = terms['observations']
    if terms['inactive']:
        raise ValueError('PRODUCT_INACTIVE')
    if observed.get('currency', {}).get('value') != 'EUR' or observed.get('issuer', {}).get('value') not in ISSUERS:
        raise ValueError('UNSUPPORTED_QUOTE_IDENTITY')
    issuer, venue = ISSUERS[observed['issuer']['value']]
    candidates = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.S | re.I):
        cells = {}
        for label, value in re.findall(r'<t[dh]\b[^>]*data-label="([^"]+)"[^>]*>(.*?)</t[dh]>', row, re.S | re.I):
            if label in cells:
                raise ValueError('AMBIGUOUS_ROW')
            cells[label] = plain(value)
        if cells.get('LiveTrading') != venue:
            continue
        def price(label):
            raw = cells.get(label, '')
            if not re.fullmatch(r'Realtime Kurs (?:\d+|\d{1,3}(?:\.\d{3})+),\d{1,6}', raw):
                raise ValueError('MISSING_REALTIME_PRICE')
            value = float(raw.removeprefix('Realtime Kurs ').replace('.', '').replace(',', '.'))
            if not math.isfinite(value) or value <= 0:
                raise ValueError('INVALID_PRICE')
            return value
        bid, ask = price('Geld'), price('Brief')
        if ask < bid:
            raise ValueError('CROSSED_QUOTE')
        at = datetime.strptime(cells['Datum']+' '+cells['Zeit'], '%d.%m.%y %H:%M')
        zone = ZoneInfo('Europe/Berlin')
        if at.replace(tzinfo=zone, fold=0).utcoffset() != at.replace(tzinfo=zone, fold=1).utcoffset():
            raise ValueError('AMBIGUOUS_TIME')
        at = at.replace(tzinfo=zone).isoformat()
        candidates.append(dict(isin=isin, bid=bid, ask=ask, price=ask,
            bidAt=at, askAt=at, quoteAt=at, currency='EUR',
            source='comdirect · '+issuer+' LiveTrading', sourceUrl=ORIGIN+'inf/zertifikate/'+isin,
            venue=venue, upstream=issuer, priceKind='market-observation',
            timeBasis='Gemeinsame Kurszeile; Europe/Berlin; Minutenauflösung',
            researchOnly=True, isExecutableQuote=False, degiroExecutable=False))
    if len(candidates) != 1:
        raise ValueError('QUOTE_ROW_MISSING_OR_AMBIGUOUS')
    return candidates[0]


def _refresh(isin):
    result = dict(state='unavailable')
    try:
        req = Request(ORIGIN+'inf/zertifikate/'+isin, headers={
            'User-Agent': 'Bob public product research', 'Accept': 'text/html'})
        with open_public_page(req, timeout=8) as response:
            if not response.url.startswith(ORIGIN):
                raise ValueError('UNEXPECTED_REDIRECT')
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('RESPONSE_TOO_LARGE')
        html = data.decode('utf-8')
        from comdirect_fields import parse_page as parse_fields
        result = dict(state='observed', fields=parse_fields(html, isin))
        try:
            result['quote'] = parse_page(html, isin)
        except (ValueError, KeyError) as exc:
            result['quoteState'] = 'unavailable'
            result['reasonCode'] = str(exc)[:80]
    except Exception as exc:
        result['reasonCode'] = 'HTTP_'+str(exc.code) if hasattr(exc, 'code') else 'SOURCE_UNAVAILABLE'
    finally:
        with _LOCK:
            prior = _CACHE.get(isin)
            historical = prior[1].get('quote') if prior else None
            if (not result.get('quote') and isinstance(historical, dict)
                    and historical.get('isin') == isin
                    and not (result.get('fields') or {}).get('inactive')):
                # Carry the ORIGINAL quote clock; this never renews freshness.
                result['quote'] = copy.deepcopy(historical)
                result['retainedAfterFailure'] = True
            if len(_CACHE) >= 128:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[isin] = (time.monotonic(), result)
            _PENDING.discard(isin)


def get_observation(isin):
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < 30:
            return copy.deepcopy(cached[1])
        if isin not in _PENDING and len(_PENDING) < 16:
            _PENDING.add(isin)
            _POOL.submit(_refresh, isin)
        # Retain the original timestamp while refreshing; apply rechecks age.
        return copy.deepcopy(cached[1]) if cached else dict(state='checking')


def apply(result, isin, now=None):
    from product_quotes import valid_isin
    meta = result.get('metadata') or {}
    if (not valid_isin(isin) or result.get('isin') != isin or not result.get('productVerified')
            or result.get('sourceDisabled')
            or meta.get('status') != 1
            or not (meta.get('issuerExchangeCode') == 'CBDE' or str(result.get('source', '')).startswith('BNP Paribas ·'))
            or (result.get('currency') or meta.get('currency')) != 'EUR'):
        return result
    now = now or datetime.now(timezone.utc)
    out = copy.deepcopy(result)
    evidence = get_observation(isin)
    out['comdirectQuoteBackup'] = dict(state=evidence['state'], refreshSeconds=30, reasonCode=evidence.get('reasonCode'))
    quote = evidence.get('quote')
    if not quote or not matches_primary(result, quote):
        return out
    age = (now-datetime.fromisoformat(quote['quoteAt'])).total_seconds()
    out['comdirectQuoteBackup'].update(state='current' if 0 <= age <= 90 else 'stale',
                                     sourceAt=quote['quoteAt'])
    # The audit can display historical evidence without granting freshness.
    secondary = out.get('secondaryQuote') or {}
    try:
        secondary_at = datetime.fromisoformat(str(secondary.get('quoteAt','')).replace('Z','+00:00'))
        if secondary_at.tzinfo is None:raise ValueError('undated source clock')
    except ValueError:
        secondary_at = datetime.min.replace(tzinfo=timezone.utc)
    if (not secondary or secondary.get('source') == quote['source']
            and datetime.fromisoformat(quote['quoteAt']) >= secondary_at):
        out['secondaryQuote'] = copy.deepcopy(quote)
    if 0 <= age <= 90:
        current = out.get('analysisQuote') or {}
        try:
            current_at = datetime.fromisoformat(current['askAt'].replace('Z', '+00:00'))
        except (KeyError, ValueError, TypeError):
            current_at = datetime.min.replace(tzinfo=timezone.utc)
        if current_at.tzinfo is None:
            current_at = datetime.min.replace(tzinfo=timezone.utc)
        if datetime.fromisoformat(quote['quoteAt']) > current_at:
            out['analysisQuote'] = copy.deepcopy(quote)
    return out
