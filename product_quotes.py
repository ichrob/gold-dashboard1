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
    if url.startswith(SG_ORIGIN) or origin == SG_ORIGIN:
        raise PermissionError('SG_LIVE_DISABLED_BY_USER')
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


def sg_disabled(isin):
    """User decision: no SG network research, including relayed OTC quotes."""
    return dict(found=False, eligible=False, fresh=False, productVerified=False,
                isin=isin, source='SG-Abruf deaktiviert', sourceDisabled=True,
                sourceFailure=False,
                reason='SG-Liveabruf auf Nutzerwunsch deaktiviert. DEGIRO-Screenshotdaten verwenden; Berechnungen bleiben als berechnet gekennzeichnet.')


def get_sg_quote(isin):
    return sg_disabled(isin)


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

def bnp_product_data(data, isin, now=None):
    """Keep identified conditions even when the issuer has no dated quote.

    responseDate/keyFigures.lastUpdate date the response/calculations, not the
    strike or KO. determinationDate can be future-dated; none is a terms clock.
    """
    now = now or datetime.now(timezone.utc)
    r = data['result']
    first, config = r['first'], r['config']
    if (r['isin'] != isin or first['underlyingISIN'] != 'USFX00000XAU'
            or first['currency']['isoCode'] != 'USD' or r['currency']['isoCode'] != 'EUR'
            or not r['issuerCompanyName'].startswith('BNP Paribas')
            or config.get('hasMultipleUnderlying') is not False):
        raise ValueError('Produktidentität, Basiswert oder Währung nicht bestätigt')
    name = r['productName']
    sides = [side for side in ('LONG', 'SHORT') if side in name.upper()]
    if len(sides) != 1:
        raise ValueError('Produktrichtung fehlt')
    terminal = ('isKnockedOut', 'isMaturedOrKnockOut', 'isCanceled', 'isLifeCycleEnded')
    if any(type(config.get(k)) is not bool for k in terminal):
        raise ValueError('Produktstatus fehlt')
    inactive = any(config[k] for k in terminal)
    url = ORIGIN+'product-details/'+isin+'/'
    values = dict(underlying='XAU/USD', currency='EUR')
    metadata = dict(name=name, direction=sides[0], underlying='XAU/USD',
                    underlyingType='SPOT', underlyingIsin=first['underlyingISIN'],
                    currency='EUR', status=2 if inactive else 1,
                    tradingHalted=inactive, termsDated=False, observedAt=now.isoformat())
    for source, target in (('knockOutAbsolute', 'ko'), ('strikeAbsolute', 'strike'), ('ratio', 'ratio')):
        if source in first:
            value = number(first[source])
            if value <= 0:
                raise ValueError('Ungültige Produktbedingung')
            metadata[target] = value
            if target == 'ratio':
                values[target] = value
    typ = r.get('derivativeTypeName')
    if typ in ('Unlimited Long', 'Unlimited Short'):
        if typ.upper().split()[-1] != sides[0]:
            raise ValueError('Widersprüchliche Produktrichtung')
        values['type'] = typ
    if r.get('keyFigures', {}).get('maturityDateTimestamp') == -1:
        values['maturity'] = 'Open End'
    conditions = {key:dict(value=value, at=None, source=url, conditionVerified=True,
                           reviewedAt=now.isoformat()) for key, value in values.items()}
    return dict(found=False, eligible=False, fresh=False, productVerified=True,
                isin=isin, name=name, source='BNP Paribas · offizielle Produktdaten',
                sourceUrl=url, checkedAt=now.isoformat(), metadata=metadata,
                conditions=conditions, isDegiroQuote=False,
                observedTerms=dict(ko=metadata.get('ko'), strike=metadata.get('strike'),
                                   underlying='XAU/USD', source=url, effectiveAt=None),
                reason='Produkt ausgeknockt oder beendet – ausgeschlossen' if inactive else
                       'BNP-Produktbedingungen erkannt; Kurszeiten und Gültigkeitsstand von Basispreis/KO separat prüfen')


def bnp_source_error(exc):
    """Stable diagnostic codes; never return raw provider bodies or exceptions."""
    if isinstance(exc, HTTPError):
        return 'HTTP_'+str(exc.code), 'BNP antwortet mit HTTP '+str(exc.code)
    if isinstance(exc, (TimeoutError, URLError, OSError)):
        return 'CONNECTION', 'BNP-Verbindung fehlgeschlagen oder Zeitlimit erreicht'
    if isinstance(exc, KeyError) and exc.args and exc.args[0] in ('bidDate', 'askDate', 'lastUpdate', 'responseDate'):
        labels = {'bidDate':'Geldkurs', 'askDate':'Briefkurs', 'lastUpdate':'Hebel', 'responseDate':'Quellenantwort'}
        return 'MISSING_QUOTE_TIME', 'BNP: Quellenzeit für '+labels[exc.args[0]]+' fehlt; keine aktuelle Kursfreigabe'
    if isinstance(exc, KeyError):
        return 'MISSING_FIELD', 'BNP-Antwort unvollständig; erforderliche Produkt- oder Kursangaben fehlen'
    return 'INVALID_RESPONSE', 'BNP-Antwort nicht eindeutig prüfbar; Produktidentität, Werte oder Zeitstempel prüfen'


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

def get_issuer_quote(isin):
    isin = str(isin or '').strip().upper()
    if not valid_isin(isin):
        return dict(found=False, eligible=False, fresh=False, reason='ISIN-Prüfziffer ungültig')
    # Known SG identities are local routing information, not verified terms.
    # Check before cache: an earlier SG response must never be reused as live.
    from sg_quotes import PRODUCT_IDS
    if isin in PRODUCT_IDS or isin in SG_GOLD_FUTURES:
        return sg_disabled(isin)
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < 15 and str(cached[1].get('source', '')).startswith('BNP Paribas'):
            return freshness(cached[1])
    # Unknown products may be researched at BNP only. No speculative SG request.
    result = get_bnp_quote(isin)
    with _LOCK:
        if len(_CACHE) >= 256:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin] = (time.monotonic(), result)
    return freshness(result)


def get_bnp_quote(isin):
    # Some intermediaries replay the same header response despite no-cache.
    # A bounded 15-second URL bucket matches our local cache. This is only a
    # request parameter, never evidence of quote freshness; original clocks win.
    url = ORIGIN+'apiv2/api/v1/product/header/'+isin+'?_='+str(int(time.time()//15)*15000)
    terms = None
    try:
        request = Request(url, headers={'User-Agent':'Bob/1.6 public product research','Accept':'application/json',
                                       'clientid':'0','languageid':'de','Cache-Control':'no-cache'})
        with urlopen(request, timeout=12) as response:
            if not response.url.startswith(ORIGIN):
                raise ValueError('Unerwartete Weiterleitung')
            body = response.read(500_001)
        if len(body) > 500_000:
            raise ValueError('Produktantwort zu groß')
        data = json.loads(body)
        terms = bnp_product_data(data, isin)
        result = dict(terms, **parse_bnp(data, isin))
    except Exception as exc:
        code, reason = bnp_source_error(exc)
        result = dict(terms or dict(found=False, eligible=False, fresh=False, productVerified=False,
                      isin=isin, source='BNP Paribas · öffentliche Produktrecherche',
                      sourceUrl=ORIGIN+'product-details/'+isin+'/', checkedAt=datetime.now(timezone.utc).isoformat()))
        result.update(sourceFailure=terms is None, quoteFailureCode=code, reason=reason)
        if terms and terms['metadata']['status'] == 2:
            result['reason'] = terms['reason']+' · '+reason
    return result



def get_quote(isin):
    """Combine dated issuer quotes with independently identified exchange terms."""
    isin = str(isin or '').strip().upper()
    if not valid_isin(isin):
        return dict(found=False, eligible=False, fresh=False, reason='ISIN-Prüfziffer ungültig')
    from public_product_terms import get_product
    terms = get_product(isin)
    if terms.get('productVerified') and terms.get('metadata', {}).get('status') == 2:
        return terms
    issuer = get_issuer_quote(isin)
    if issuer.get('productVerified') and issuer.get('metadata', {}).get('status') == 2:
        return dict(issuer, found=False, eligible=False, exchangeResearch=terms)
    if not terms.get('productVerified'):
        if issuer.get('found') or issuer.get('productVerified'):
            return dict(issuer, exchangeResearch=terms)
        return dict(issuer, exchangeResearch=terms, sourceDisabled=False,
                    sourceFailure=True, source=terms.get('source', 'Öffentliche Produktrecherche'),
                    reason=terms.get('reason', 'Produktrecherche nicht verfügbar')+
                    (' · '+issuer['reason'] if issuer.get('quoteFailureCode') else ''))
    if not issuer.get('found'):
        # Preserve the working terms source and the reason the independent
        # quote attempt failed. Previously both layers discarded this evidence.
        if not issuer.get('quoteFailureCode') and not issuer.get('productVerified'):
            return terms
        result = dict(terms, issuerResearch=issuer)
        if issuer.get('quoteFailureCode'):
            result.update(quoteFailureCode=issuer['quoteFailureCode'],
                          reason=terms['reason']+' · '+issuer['reason'])
        return result
    result = dict(issuer, productVerified=True, metadata=terms['metadata'],
                  conditions=terms['conditions'], observedTerms=terms['observedTerms'],
                  termsSource=terms['source'], termsSourceUrl=terms['sourceUrl'],
                  termsCheckedAt=terms['checkedAt'])
    if terms['metadata']['status'] != 1 or terms['metadata']['tradingHalted']:
        result.update(eligible=False, marketOpen=False, reason=terms['reason'])
    return result
