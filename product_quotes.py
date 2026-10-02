"""Free public BNP issuer snapshot; no accounts, orders, keys or subscriptions.
Endpoint and public client headers are those used by the issuer's product page.
Never substitute request time for bid, ask or leverage timestamps.
"""
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

MAX_AGE_SECONDS = 90
_CACHE = {}
_LOCK = threading.Lock()
ORIGIN = 'https://derivate.bnpparibas.com/'
SG_ORIGIN = 'https://www.sg-zertifikate.de/'
# Exact contract identities confirmed from SG and the secondary product snapshot.
SG_GOLD_FUTURES = {
    'DE000FG309G0': dict(nmp='C_CMX_GOLD_F_Z26', ric='GCZ26',
                         isin='XC0009656924', name='Gold Future Dec 2026',
                         instrument_id='188570012', notation_id=317423266),
}

def sg_future_contract(product, isin):
    # The verified underlying identity applies to other SG products on the
    # same contract too. Every product still needs its own verified quote ID.
    contract = next((c for c in SG_GOLD_FUTURES.values() if product.get('AssetRic') == c['ric']), None)
    if contract and all(product.get(key) == contract[field] for key, field in
                        [('AssetNMP', 'nmp'), ('AssetRic', 'ric'), ('AssetIsin', 'isin'),
                         ('AssetName', 'name')]):
        return contract
    return None

def issuer_json(url, origin, timeout=6):
    """Read a bounded response only from the selected issuer's fixed host."""
    request = Request(url, headers={'User-Agent': 'Bob/1.7 public product research',
                                   'Accept': 'application/json', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=timeout) as response:
        if not response.url.startswith(origin):
            raise ValueError('Unerwartete Weiterleitung')
        body = response.read(500_001)
    if len(body) > 500_000:
        raise ValueError('Produktantwort zu groß')
    return json.loads(body)

def parse_sg(product, properties, isin, now=None):
    """SG's AllProperties is metadata, not a dated live quote snapshot.

    Its TimeStamp is BIDTIME only, has no offset, and does not date ASK or
    current_leverage. Never invent those timestamps or promote chart history
    to an executable snapshot. Preserve identified metadata separately.
    """
    now = now or datetime.now(timezone.utc)
    contract = sg_future_contract(product, isin)
    if (product.get('Isin') != isin or product.get('ExchangeCode') != 'CBDE'
            or (product.get('AssetNMP') != 'XAUUSD' and contract is None) or product.get('AssetCurrency') != 'USD'
            or product.get('Currency') != 'EUR' or not isinstance(properties, list)):
        raise ValueError('SG-Produktidentität oder Gold-Basiswert nicht bestätigt')
    attrs = {}
    for item in properties:
        name = item['Name']
        if name in attrs:
            raise ValueError('Widersprüchliche SG-Eigenschaften')
        attrs[name] = item
    if attrs['Isin']['Value'] != isin:
        raise ValueError('SG-Eigenschaften gehören zu anderer ISIN')
    side = attrs['PutOrCall']['Value']
    if side not in ('Call', 'Put'):
        raise ValueError('SG-Produktrichtung fehlt')
    barrier = attrs.get('BarrierTurboCertificate') or attrs.get('Barrier')
    if not barrier or barrier.get('Suffix', '').strip() != 'USD':
        raise ValueError('SG-KO-Barriere in USD fehlt')
    ko = number(barrier['Value'])
    if ko <= 0:
        raise ValueError('Ungültige SG-KO-Barriere')
    # Barrier updates are separate from BIDTIME. Preserve the issuer's own
    # date without assigning an undocumented timezone or a validity window.
    ko_evidence = None
    update = attrs.get('StrikeBarrierUpdateTime', {}).get('Value')
    if isinstance(update, str) and re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?', update):
        try:
            parsed_update = datetime.fromisoformat(update.replace('Z', '+00:00'))
        except ValueError:
            pass
        else:
            ko_evidence = dict(value=ko, currency='USD', updatedAtRaw=update,
                               timezoneKnown=parsed_update.tzinfo is not None,
                               retrievedAt=now.isoformat(),
                               source='SG · StrikeBarrierUpdateTime',
                               state='issuer_reported')
    status = product.get('Status')
    if isinstance(status, bool) or not isinstance(status, int):
        raise ValueError('SG-Produktstatus fehlt')
    inactive = bool(status & (2 | 8 | 16 | 32)) or not status & 1
    reason = ('SG-Produkt abgelaufen oder Barriere getroffen' if inactive else
              'SG-Produkt erkannt; getrennte aktuelle Zeitstempel für Geld, Brief und Hebel fehlen')
    return dict(found=False, productVerified=True, eligible=False, fresh=False,
                isin=isin, source='Société Générale · offizielle Produktdaten',
                sourceUrl=SG_ORIGIN+'product-details/'+isin.lower(),
                checkedAt=now.isoformat(), reason=reason,
                metadata=dict(name=product.get('Name', ''), underlying=contract['name'] if contract else 'XAU/USD',
                              underlyingType='FUTURE' if contract else 'SPOT',
                              contract=contract['ric'] if contract else None,
                              underlyingIsin=product.get('AssetIsin'), currency='EUR',
                              direction='LONG' if side == 'Call' else 'SHORT', ko=ko,
                              status=status, koEvidence=ko_evidence), maxAgeSeconds=MAX_AGE_SECONDS)

def sg_source_error(exc, stage):
    # Fixed descriptions only: never expose provider bodies, URLs or headers.
    stages = {'identity': 'Produktidentität', 'properties': 'Produkteigenschaften',
              'dated-quotes': 'datierte Kurse'}
    label = stages.get(stage, 'Produktdaten')
    if isinstance(exc, PermissionError) and str(exc) == 'ONVISTA_AUTOMATION_NOT_APPROVED':
        detail = 'automatischer Onvista-Abruf gesperrt: ausdrückliche Anbietereinwilligung fehlt'
    elif isinstance(exc, HTTPError):
        detail = 'Datenanbieter antwortet mit HTTP '+str(exc.code)
    elif isinstance(exc, (TimeoutError, URLError, OSError)):
        detail = 'Verbindung fehlgeschlagen oder Zeitlimit erreicht'
    elif isinstance(exc, ValueError) and str(exc) == 'Kursdaten fehlen':
        detail = 'Kursdaten fehlen'
    else:
        detail = 'Antwort nicht verwendbar oder Pflichtangaben fehlen'
    return 'SG '+label+': '+detail


def get_sg_quote(isin):
    stage = 'identity'
    verified_metadata = None
    try:
        product = issuer_json(SG_ORIGIN+'EmcWebApi/api/Products/'+isin, SG_ORIGIN)
        product_id = product['Id']
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
            raise ValueError('Ungültige SG-Produktkennung')
        if product.get('Isin') != isin:
            raise ValueError('Falsche SG-ISIN')
        if product.get('AssetNMP') != 'XAUUSD' and sg_future_contract(product, isin) is None:
            return dict(found=False, productVerified=True, eligible=False, fresh=False, isin=isin,
                        source='Société Générale · offizielle Produktdaten',
                        sourceUrl=SG_ORIGIN+'product-details/'+isin.lower(),
                        checkedAt=datetime.now(timezone.utc).isoformat(),
                        reason='SG-Basiswert '+str(product.get('AssetNMP', 'unbekannt'))+
                               ' ist kein XAU/USD-Spot; eigene Basiswertdaten erforderlich',
                        metadata=dict(name=product.get('Name', ''), underlying=product.get('AssetNMP'),
                                      underlyingIsin=product.get('AssetIsin'), currency=product.get('Currency'),
                                      underlyingType='UNSUPPORTED',
                                      direction='nicht bestätigt', ko='nicht bestätigt'))
        stage = 'properties'
        properties = issuer_json(SG_ORIGIN+'EmcWebApi/api/Products/AllProperties/'+str(product_id), SG_ORIGIN)
        verified_metadata = parse_sg(product, properties, isin)
        # Dated OTC quotes are a separate source. SG's undated ASK/leverage
        # fields and chart prices must never become an executable snapshot.
        from sg_quotes import get_quote as sg_quote
        stage = 'dated-quotes'
        result = sg_quote(product, properties, isin)
        research = result.get('futureResearch', {})
        print(f'BOB_SG isin={isin} found={bool(result.get("found"))} eligible={bool(result.get("eligible"))} '
              f'product_verified={bool(result.get("productVerified"))} '
              f'research_available={bool(research)} contract={research.get("contract")} '
              f'estimate_available={bool(research.get("calculatedFuture", {}).get("available"))} '
              f'age={result.get("ageSeconds")} source=sg-otc-onvista', flush=True)
        return result
    except Exception as exc:
        print(f'BOB_SG isin={isin} stage={stage} error={type(exc).__name__}', flush=True)
        if verified_metadata is not None:
            return dict(verified_metadata, found=False, eligible=False, fresh=False,
                        sourceFailure=True, reason=sg_source_error(exc, stage))
        return dict(found=False, eligible=False, fresh=False, isin=isin,
                    source='Société Générale · öffentliche Produktrecherche',
                    productVerified=stage != 'identity', sourceFailure=True,
                    reason=sg_source_error(exc, stage))

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
    if result.get('futureResearch'):
        from sg_quotes import refresh_future_research
        result['futureResearch'] = refresh_future_research(result['futureResearch'], now)
    try:
        keys = ['quoteAt', 'bidAt', 'askAt', 'leverageAt', 'snapshotAt']
        if result.get('leverageKind') == 'calculated-gearing':
            keys += ['spotAt', 'fxAt', 'fxDataAt', 'fxEffectiveAt']
        times = [stamp(result[k]) for k in keys]
        ages = [(now-t).total_seconds() for t in times]
        result['ageSeconds'] = round(max(ages), 1)
        result['fresh'] = all(-5 <= age <= MAX_AGE_SECONDS for age in ages)
    except (KeyError, ValueError, TypeError):
        result['fresh'] = False
    result['eligible'] = bool(result.get('found') and result['fresh'] and result.get('marketOpen') and now <= stamp(result['tradingEndAt']))
    if result.get('metadata', {}).get('underlyingType') == 'FUTURE':
        result['eligible'] = False
        if not result.get('sourceFailure'):
            result['reason'] = 'Gold-Future: eigener bedingter Kontraktvergleich; keine Spot-Freigabe'
    if result.get('found') and not result['eligible'] and result.get('metadata', {}).get('underlyingType') != 'FUTURE':
        result['reason'] = 'Kurs veraltet, Markt geschlossen oder Zeitstempel nicht prüfbar'
    result['pricePolicy'] = 'direct-then-verified-model'
    if result.get('productModel'):
        from sg_quotes import apply_product_estimate
        result = apply_product_estimate(result, now)
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
    # Query issuers independently; a slow BNP miss must not consume SG's
    # entire browser timeout. Neither adapter trusts the ISIN prefix.
    with ThreadPoolExecutor(max_workers=2) as pool:
        bnp = pool.submit(get_bnp_quote, isin)
        sg = pool.submit(get_sg_quote, isin)
        result = bnp.result()
        sg_result = sg.result()
    if not result.get('found') and (sg_result.get('productVerified') or isin in SG_GOLD_FUTURES):
        result = sg_result
    with _LOCK:
        if len(_CACHE) >= 256:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin] = (time.monotonic(), result)
    return freshness(result)

def get_bnp_quote(isin):
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
    return result
