"""Public Swiss DOTS research evidence. Native CHF, no execution clearance."""
import copy
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ORIGIN = 'https://www.swissquote.ch/'
SOURCE = 'Swissquote · Swiss DOTS'
# Previously verified stock keys for prewarming. New products require issuer metadata.
PRODUCTS = {'DE000FG14AV8': 'LONG', 'DE000FG8NHQ3': 'SHORT'}
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='swissquote')
_LOCK = threading.Lock()
_CACHE = {}
_PENDING = set()


def source_url(isin):
    return ORIGIN+'trading-platform/#fullQuote/'+isin+'/672_CHF'


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('MISSING_SOURCE_TIME')
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('UNDATED_TIMEZONE')
    return at


def parse_payload(payload, isin, now=None):
    now = now or datetime.now(timezone.utc)
    data = payload['fullQuoteData']
    underlying = data.get('underlyings') or []
    direction = {'CALL': 'LONG', 'PUT': 'SHORT'}.get(data.get('optionType'))
    from product_quotes import valid_isin
    if (not isinstance(isin, str) or not valid_isin(isin) or data.get('stockKey') != dict(isin=isin, exchangeId=672, currency='CHF')
            or data.get('issuerName') != 'Societe Generale'
            or data.get('stockExchangeName') != 'Swiss DOTS' or data.get('marketCode') != 'DOTS'
            or data.get('productType') != 'WARRANT' or data.get('eusipaCode') != '2200'
            or direction not in ('LONG', 'SHORT')
            or (isin in PRODUCTS and direction != PRODUCTS[isin]) or len(underlying) != 1
            or underlying[0].get('isin') != 'XC0009655157' or underlying[0].get('currency') != 'USD'):
        raise ValueError('IDENTITY_MISMATCH')
    url = source_url(isin)
    # Retrieval time is deliberately NOT a validity/quote/leverage timestamp.
    fields = {}
    values = {'direction': direction, 'currency': 'CHF', 'underlying': 'XAU/USD',
              'issuer': data['issuerName'], 'marketStatus': data.get('marketStatus')}
    for key, api_key in [('ko', 'knockOut'), ('strike', 'strike')]:
        item = underlying[0].get(api_key) or {}
        if item.get('currency') == 'USD' and positive(item.get('value')):
            values[key] = item['value']
    if positive(data.get('ratio')):
        values['ratio'] = 1 / data['ratio']  # Swissquote units per underlying (10:1).
    if data.get('isOpenEnd') is True:
        values['maturity'] = 'Open End'
    elif data.get('expirationDate'):
        values['maturity'] = stamp(data['expirationDate']).date().isoformat()
    for key, value in values.items():
        if value is not None:
            fields[key] = dict(value=value, source=url, observedAt=now.isoformat(),
                               sourceAt=None, validityUnconfirmed=True)
    out = dict(state='observed', isin=isin, source=SOURCE, sourceUrl=url,
               checkedAt=now.isoformat(), fields=fields,
               leverageState='not-supplied', leverageTimeState='not-supplied')
    quote = data.get('quote') or {}
    try:
        bid, ask = quote['bidPrice'], quote['askPrice']
        if (bid.get('status') != 'AVAILABLE' or ask.get('status') != 'AVAILABLE'
                or not positive(bid.get('amount')) or not positive(ask.get('amount'))
                or ask['amount'] < bid['amount']):
            raise ValueError('INVALID_PAIR')
        bid_at, ask_at = stamp(bid['timestamp']), stamp(ask['timestamp'])
        out['quote'] = dict(isin=isin, bid=bid['amount'], ask=ask['amount'], price=ask['amount'],
            bidAt=bid_at.isoformat(), askAt=ask_at.isoformat(), quoteAt=min(bid_at, ask_at).isoformat(),
            currency='CHF', source=SOURCE, sourceUrl=url, venue='Swiss DOTS', upstream='SG',
            direction=direction, priceKind='market-observation',
            delayed=quote.get('serviceLevel') != 'REALTIME', marketOpen=data.get('marketStatus') == 'MARKET_OPEN',
            researchOnly=True, isExecutableQuote=False, degiroExecutable=False)
    except (ValueError, KeyError, TypeError):
        out['reasonCode'] = 'QUOTE_UNAVAILABLE'
    return out


def fetch(isin):
    from product_quotes import valid_isin
    if not isinstance(isin, str) or not valid_isin(isin):
        return dict(state='unsupported')
    try:
        url = ORIGIN+'securities-retail-fullquote-plugin/api/fullQuote/'+isin+'/672_CHF'
        # Public disclaimer acceptance explicitly authorized by the owner on
        # 2026-10-14. This is the site's non-secret consent flag, not a login.
        req = Request(url, headers={'Accept': 'application/json',
            'User-Agent': 'Bob public product research', 'Cookie': 'SQCB=accepted'})
        with urlopen(req, timeout=8) as response:
            if response.url != url:
                raise ValueError('UNEXPECTED_REDIRECT')
            data = response.read(500_001)
        if len(data) > 500_000:
            raise ValueError('RESPONSE_TOO_LARGE')
        return parse_payload(json.loads(data), isin)
    except Exception as exc:
        return dict(state='unavailable', reasonCode='HTTP_'+str(exc.code) if hasattr(exc, 'code') else 'SOURCE_UNAVAILABLE')


def _refresh(isin):
    try:
        evidence = fetch(isin)
        with _LOCK:
            _CACHE[isin] = (time.monotonic(), evidence)
            while len(_CACHE) > 64:
                oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
                del _CACHE[oldest]
    finally:
        with _LOCK:
            _PENDING.discard(isin)
    if evidence.get('state') == 'observed':
        from quote_updates import updates
        updates.notify(isin)


def eligible_primary(result, isin):
    from product_quotes import valid_isin
    meta = result.get('metadata') or {}
    return (isinstance(isin, str) and valid_isin(isin) and result.get('isin') == isin
        and result.get('productVerified') is True and not result.get('sourceDisabled')
        and meta.get('status') == 1 and meta.get('issuerExchangeCode') == 'CBSW'
        and meta.get('currency') == 'CHF'
        and (meta.get('direction') or result.get('direction')) in ('LONG', 'SHORT'))


def get_observation(isin, primary=None):
    if isin not in PRODUCTS and not eligible_primary(primary or {}, isin):
        return dict(state='unsupported')
    with _LOCK:
        cached = _CACHE.get(isin)
        if (not cached or time.monotonic()-cached[0] >= 30) and isin not in _PENDING and len(_PENDING) < 12:
            _PENDING.add(isin)
            _POOL.submit(_refresh, isin)
        return copy.deepcopy(cached[1]) if cached else dict(state='checking')


def matches_primary(result, row):
    meta = result.get('metadata') or {}
    isin = result.get('isin')
    return (eligible_primary(result, isin)
        and row.get('isin') == isin
        and row.get('direction') == (meta.get('direction') or result.get('direction'))
        and row.get('currency') == 'CHF' and row.get('source') == SOURCE
        and row.get('sourceUrl') == source_url(isin) and row.get('venue') == 'Swiss DOTS')


def current_pair(result, now):
    row = result.get('thirdQuote') or {}
    if (not matches_primary(result, row) or row.get('priceKind') != 'market-observation'
            or row.get('delayed') is not False or row.get('marketOpen') is not True
            or row.get('isExecutableQuote') is not False or row.get('degiroExecutable') is not False
            or not positive(row.get('bid')) or not positive(row.get('ask')) or row['ask'] < row['bid']):
        return None
    try:
        dates = [stamp(row[k]) for k in ('bidAt', 'askAt')]
        if any(not 0 <= (now-at).total_seconds() <= 90 for at in dates):
            return None
    except (ValueError, TypeError, KeyError):
        return None
    return row


def apply(result, isin, now=None):
    if not eligible_primary(result, isin):
        return result
    now = now or datetime.now(timezone.utc)
    out = copy.deepcopy(result)
    evidence = get_observation(isin, result)
    out['swissquoteBackup'] = dict(evidence, refreshSeconds=30)
    row = evidence.get('quote')
    if not row or not matches_primary(result, row):
        return out
    out['thirdQuote'] = copy.deepcopy(row)
    current = current_pair(out, now)
    out['swissquoteBackup']['quoteState'] = 'current' if current else 'stale-or-unavailable'
    # Keep native currency. The existing calculation understands CHF inputs.
    previous = out if out.get('found') else out.get('analysisQuote') or {}
    try:
        previous_at = stamp(previous.get('askAt'))
    except (ValueError, TypeError):
        previous_at = datetime.min.replace(tzinfo=timezone.utc)
    if current and not out.get('found') and stamp(row['askAt']) > previous_at:
        out['analysisQuote'] = copy.deepcopy(row)
    return out
