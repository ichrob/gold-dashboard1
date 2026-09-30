"""Free public BNP issuer snapshot; no accounts, orders, keys or subscriptions.
Endpoint and public client headers are those used by the issuer's product page.
Never substitute request time for bid, ask or leverage timestamps.
"""
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MAX_AGE_SECONDS = 60
_CACHE = {}
_LOCK = threading.Lock()
ORIGIN = 'https://derivate.bnpparibas.com/'

def valid_isin(value):
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', value) or re.match(r'DE(?=[0O]{3})(?=[0O]{0,2}O)', value):
        return False
    digits = ''.join(str(ord(c)-55) if c.isalpha() else c for c in value)
    return sum((int(c)*2//10+int(c)*2%10) if i%2 else int(c) for i,c in enumerate(reversed(digits)))%10 == 0

def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Ungültige Kurszahl')
    return float(value)

def stamp(value, local=False):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        if not local:
            raise ValueError('Zeitzone fehlt')
        result = result.replace(tzinfo=ZoneInfo('Europe/Berlin'))
    return result.astimezone(timezone.utc)

def freshness(result, now=None):
    result = dict(result)
    now = now or datetime.now(timezone.utc)
    try:
        times = [stamp(result[k]) for k in ('quoteAt', 'bidAt', 'askAt', 'leverageAt', 'snapshotAt')]
        ages = [(now-t).total_seconds() for t in times]
        result['ageSeconds'] = round(max(ages), 1)
        result['fresh'] = all(-5 <= age <= MAX_AGE_SECONDS for age in ages)
    except (KeyError, ValueError, TypeError):
        result['fresh'] = False
    result['eligible'] = bool(result.get('found') and result['fresh'] and result.get('marketOpen') and now <= stamp(result['tradingEndAt']))
    if result.get('found') and not result['eligible']:
        result['reason'] = 'Kurs veraltet, Markt geschlossen oder Zeitstempel nicht prüfbar'
    return result

def parse_bnp(data, isin, now=None):
    now = now or datetime.now(timezone.utc)
    r = data['result']
    first, figures, config, hours = r['first'], r['keyFigures'], r['config'], data['tradingHours']
    if r['isin'] != isin or first['underlyingISIN'] != 'USFX00000XAU' or first['currency']['isoCode'] != 'USD' or r['currency']['isoCode'] != 'EUR' or not r['issuerCompanyName'].startswith('BNP Paribas') or config.get('hasMultipleUnderlying') is not False:
        raise ValueError('Produktidentität, Basiswert oder Währung nicht bestätigt')
    bid, ask, leverage, ko = (number(r['bid']), number(r['ask']), number(r['leverage']), number(first['knockOutAbsolute']))
    if bid <= 0 or ask < bid or leverage < 1 or ko <= 0 or number(r['bidSize']) <= 0 or number(r['askSize']) <= 0:
        raise ValueError('Kein gültiger zweiseitiger Kurs')
    if number(figures['leverage']) != leverage:
        raise ValueError('Widersprüchlicher Hebel')
    name = r['productName']
    direction = 'LONG' if 'LONG' in name.upper() else 'SHORT' if 'SHORT' in name.upper() else ''
    if not direction:
        raise ValueError('Produktrichtung fehlt')
    bid_at, ask_at = stamp(r['bidDate'], True), stamp(r['askDate'], True)
    leverage_at, snapshot_at = stamp(figures['lastUpdate']), stamp(data['responseDate'])
    market_open = (hours.get('isTradeable') is True and config.get('isPublicTradable') is True
                   and config.get('isMarketClosed') is False
                   and all(config.get(k) is False for k in ('isKnockedOut','isMaturedOrKnockOut','isCanceled','isLifeCycleEnded','isBidOnly','isPercentageQuotation'))
                   and stamp(hours['tradingStart']) <= now <= stamp(hours['tradingEnd']))
    result = dict(found=True, isin=isin, name=name, source='BNP Paribas · Emittent OTC',
                  sourceUrl=ORIGIN+'product-details/'+isin+'/', checkedAt=now.isoformat(),
                  quoteAt=min(bid_at,ask_at,leverage_at,snapshot_at).isoformat(),
                  bidAt=bid_at.isoformat(),askAt=ask_at.isoformat(),leverageAt=leverage_at.isoformat(),snapshotAt=snapshot_at.isoformat(),
                  bid=bid, ask=ask, price=ask, leverage=leverage, ko=ko,
                  spread=round(ask-bid, 8), spreadPct=round((ask-bid)/ask*100, 4),
                  currency='EUR', direction=direction, marketOpen=market_open,
                  isDegiroQuote=False, tradingEndAt=stamp(hours['tradingEnd']).isoformat(), maxAgeSeconds=MAX_AGE_SECONDS)
    return freshness(result, now)

def get_quote(isin):
    isin = str(isin or '').strip().upper()
    if not valid_isin(isin):
        return dict(found=False, eligible=False, fresh=False, reason='ISIN-Prüfziffer ungültig')
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < 15:
            return freshness(cached[1])
    # Fixed public endpoint from the issuer's own web client. No arbitrary URL.
    url = ORIGIN+'apiv2/api/v1/product/header/'+isin
    try:
        request = Request(url, headers={'User-Agent':'Bob/1.6 public product research','Accept':'application/json',
                                       'clientid':'0','languageid':'de','Cache-Control':'no-cache'})
        with urlopen(request, timeout=12) as response:
            if not response.url.startswith(ORIGIN):
                raise ValueError('Unerwartete Weiterleitung')
            body = response.read(500_001)
        if len(body) > 500_000:
            raise ValueError('Produktantwort zu groß')
        result = parse_bnp(json.loads(body), isin)
    except Exception:
        result = dict(found=False, eligible=False, fresh=False, isin=isin, source='Öffentliche Emittentenrecherche',
                      reason='Keine verlässlich datierten Kurse verfügbar (Quelle nicht unterstützt oder nicht erreichbar)',
                      checkedAt=datetime.now(timezone.utc).isoformat())
    with _LOCK:
        if len(_CACHE) >= 256:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin] = (time.monotonic(), result)
    return freshness(result)
