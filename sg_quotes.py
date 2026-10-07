"""SG metadata + dated SG OTC quotes relayed by onvista.

Only simple, non-quanto gold turbos are supported. The displayed gearing is
a calculated approximation (delta assumed +/-1, FX held constant), never SG's
undated CurrentLeverage. Every changing input keeps its own observation time.
"""
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import product_quotes as q
import future_estimate
import product_estimate
import future_analysis
import future_reference

ONVISTA = 'https://www.onvista.de/'
SPOT_ORIGIN = 'https://xaus.com/'
FX_ORIGIN = 'https://api.exchangerate.dev/'
# Verified public product-page identities for the user's imported SG products.
# Unknown products remain blocked; IDs are never guessed from an ISIN.
PRODUCT_IDS = {
    'DE000FG4JXV7': 340459583, 'DE000FG309G0': 339518150,
    'DE000FG7EPT1': 341071258, 'DE000FG6XB39': 339841792,
    'DE000FC1CHB7': 309138945, 'DE000FA06UL6': 298878008,
    'DE000FG5GUT0': 336000321,
}
_INPUT_CACHE = {}
_INPUT_LOCKS = {'fx': threading.Lock(), 'spot': threading.Lock()}


def product_url(isin):
    return ONVISTA+'derivate/Knock-Outs/'+str(PRODUCT_IDS[isin])+'-'+isin[5:11]+'-'+isin


def fetch_snapshot(isin):
    # Deliberately unconditional: old provider-consent settings cannot re-enable
    # a source which the user explicitly disabled.
    raise PermissionError('SG_LIVE_DISABLED_BY_USER')


def market_input(kind):
    # One FX request per 45 seconds across all products/browsers. The cache never
    # changes observation times; a carried input still fails the 60-second gate.
    ttl = 45 if kind == 'fx' else 15
    with _INPUT_LOCKS[kind]:
        cached = _INPUT_CACHE.get(kind)
        if cached and time.monotonic()-cached[0] < ttl:
            return cached[1]
        url, origin = ((FX_ORIGIN+'v1/latest/USD?symbols=EUR,CHF', FX_ORIGIN) if kind == 'fx'
                       else (SPOT_ORIGIN+'api/v1/spot?compact=1', SPOT_ORIGIN))
        value = q.issuer_json(url, origin, timeout=12)
        _INPUT_CACHE[kind] = (time.monotonic(), value)
        return value


def fetch_future_reference():
    """Dated GCZ26 research, independent of SG OTC terms and FX availability."""
    raise PermissionError('SG_LIVE_DISABLED_BY_USER')


def parse_future_reference(snapshot):
    """Validate supplied evidence without retrieving a product page."""
    isin = 'DE000FG309G0'
    contract = q.SG_GOLD_FUTURES[isin]
    instrument = snapshot['instrument']
    underlyings = snapshot['derivativesUnderlyingList']['list']
    if (instrument['isin'] != isin
            or str(instrument['entityValue']) != str(PRODUCT_IDS[isin])
            or len(underlyings) != 1):
        raise ValueError('GCZ26-Referenzidentität nicht bestätigt')
    underlying = underlyings[0]
    figures = underlying['derivativesBarrierFigureList']
    if (underlying['isoCurrency'] != 'USD'
            or underlying['instrument']['entityType'] != 'FUTURE'
            or str(underlying['instrument']['entityValue']) != contract['instrument_id']
            or underlying['market']['idNotation'] != contract['notation_id']
            or underlying['market']['codeExchange'] != 'CXE'
            or figures['idNotationUnderlying'] != contract['notation_id']
            or figures['isoCurrencyUnderlying'] != 'USD'):
        raise ValueError('GCZ26-Referenzidentität nicht bestätigt')
    at = q.stamp(figures['datetimePriceUnderlying'])
    value = future_estimate.number(figures['priceUnderlying'])
    if not 0 <= (datetime.now(timezone.utc)-at).total_seconds() <= future_estimate.MAX_REFERENCE_AGE:
        raise ValueError('GCZ26-Referenzkurs veraltet oder Kurszeit zukünftig')
    return dict(contract=contract['ric'], underlying=contract['name'], underlyingType='FUTURE',
                underlyingPriceUsd=value, underlyingAt=at.isoformat(),
                source='onvista · datierter GCZ26-Basiswert', sourceUrl=product_url(isin),
                isExchangeRealtime=False, eligible=False)


def validate_snapshot(product, properties, snapshot, isin, now):
    now = now or datetime.now(timezone.utc)
    metadata = q.parse_sg(product, properties, isin, now)
    attrs = {p['Name']: p for p in properties}
    instrument = snapshot['instrument']
    details = snapshot['derivativesDetails']
    quote = snapshot['quote']
    market = quote['market']
    underlyings = snapshot['derivativesUnderlyingList']['list']
    if (isin not in PRODUCT_IDS or instrument['isin'] != isin
            or str(instrument['entityValue']) != str(PRODUCT_IDS[isin])
            or str(quote['idInstrument']) != str(PRODUCT_IDS[isin])
            or instrument['entitySubType'] != 'KNOCKOUT_CERTIFICATE'
            or snapshot['derivativesIssuer']['id'] != 53159
            or market['codeContributor'] != 'SGED' or market['codeMarket'] != '@_SGED'
            or market['codeExchange'] != '@DE' or quote['codeQualityPriceBidAsk'] != 'RLT'
            or quote['isoCurrency'] != 'EUR' or details['isoCurrency'] != 'EUR'
            or details['numberUnderlyings'] != 1 or len(underlyings) != 1
            or details['quanto'] is not False or details['hasIndicativeDetails'] is not False
            or details['dataStatus'] != 1 or isinstance(details['dataStatus'], bool)
            or details['hasBarrierBeenHit'] is not False or details['hasOnlyBidPrices'] is not False
            or product['ProductClassificationId'] not in (43, 45, 47)):
        raise ValueError('SG-Kursidentität, Echtzeitstatus oder Turbo-Typ nicht bestätigt')
    status = metadata['metadata']['status']
    if bool(status & (2 | 8 | 16 | 32)) or not status & 1 or product.get('TodayBarrierHitDate'):
        raise ValueError('SG-Produkt nicht aktiv')
    underlying = underlyings[0]
    contract = q.sg_future_contract(product, isin)
    if contract:
        if (underlying['isoCurrency'] != 'USD'
                or underlying['instrument']['entityType'] != 'FUTURE'
                or str(underlying['instrument']['entityValue']) != contract['instrument_id']
                or underlying['market']['idNotation'] != contract['notation_id']
                or underlying['market']['codeExchange'] != 'CXE'):
            raise ValueError('Gold-Futures-Kontrakt nicht bestätigt')
    elif (underlying['isoCurrency'] != 'USD' or underlying['instrument']['symbol'] != 'XAU'
            or underlying['instrument']['entityType'] != 'PRECIOUS_METAL'):
        raise ValueError('Gold-Spot-Basiswert nicht bestätigt')
    direction = metadata['metadata']['direction']
    if details['nameExerciseRight'] != ('CALL' if direction == 'LONG' else 'PUT'):
        raise ValueError('Widersprüchliche SG-Richtung')
    barriers = underlying['derivativesBarrierList']['list']
    ko_list = [b for b in barriers if b['typeBarrier'] == 'KNOCK_OUT']
    strike_list = [b for b in barriers if b['typeBarrier'] == 'STRIKE']
    if len(ko_list) != 1 or len(strike_list) != 1:
        raise ValueError('KO oder Finanzierungskomponente nicht eindeutig')
    # onvista's quote and static key figures have different refresh cycles.
    # Use only SG as the authoritative source of KO/funding levels, never an
    # older secondary barrier. Keep disagreements explicit in provenance.
    for barrier in (ko_list[0], strike_list[0]):
        if (barrier['isoCurrencyUnderlying'] != 'USD' or barrier['hasBeenHit'] is not False
                or q.number(barrier['barrier']) <= 0):
            raise ValueError('SG-Kursquelle meldet ungültige Barriere')
    secondary_ko = q.number(ko_list[0]['barrier'])
    secondary_strike = q.number(strike_list[0]['barrier'])
    ratio = q.number(underlying['coverRatio'])
    sg_ratio = q.number(attrs['Ratio']['Value'])
    if ratio <= 0 or sg_ratio <= 0 or not math.isclose(ratio*sg_ratio, 1, rel_tol=1e-9):
        raise ValueError('Bezugsverhältnis nicht bestätigt')
    bid, ask = q.number(quote['bid']), q.number(quote['ask'])
    if bid <= 0 or ask < bid or q.number(quote['volumeBid']) <= 0 or q.number(quote['volumeAsk']) <= 0:
        raise ValueError('Kein gültiger zweiseitiger SG-Kurs')
    return metadata, attrs, instrument, details, quote, underlying, ratio, bid, ask, secondary_ko, secondary_strike


def parse_snapshot(product, properties, snapshot, spot, fx, isin, now=None):
    now = now or datetime.now(timezone.utc)
    if product.get('AssetNMP') != 'XAUUSD':
        raise ValueError('Futures dürfen keine Spot-Berechnung verwenden')
    metadata, attrs, instrument, details, quote, underlying, ratio, bid, ask, secondary_ko, secondary_strike = validate_snapshot(product, properties, snapshot, isin, now)
    direction = metadata['metadata']['direction']
    if (spot['stale'] is not False or spot['data_state']['status'] != 'fresh'
            or spot['xau']['currency'] != 'USD' or spot['xau']['unit'] != 'troy_oz'
            or fx['result'] != 'success' or fx['base'] != 'USD'
            or fx['source'] != 'live' or fx['sources']['EUR'] != 'live'
            or fx['market_session'] != 'open'):
        raise ValueError('Goldpreis oder Wechselkurs nicht aktuell bestätigt')
    gold, usd_eur = q.number(spot['spot_usd_oz']), q.number(fx['rates']['EUR'])
    if gold <= 0 or usd_eur <= 0:
        raise ValueError('Ungültige Hebel-Berechnungsgrundlage')
    ko = metadata['metadata']['ko']
    strike = q.number(attrs['Strike']['Value'])
    if ((direction == 'LONG' and (ko >= gold or strike >= gold))
            or (direction == 'SHORT' and (ko <= gold or strike <= gold))):
        raise ValueError('KO oder Finanzierungskomponente jenseits des aktuellen Goldpreises')
    bid_at, ask_at = q.stamp(quote['datetimeBid']), q.stamp(quote['datetimeAsk'])
    gold_at = q.stamp(spot['price_as_of'])
    fx_data_at, fx_effective_at = q.stamp(fx['data_updated_at']), q.stamp(fx['effective_at']['EUR'])
    fx_at = min(fx_data_at, fx_effective_at)
    # Effective gearing magnitude at the ask; constant FX and unit delta.
    # No undated issuer leverage or delayed onvista figures are used here.
    leverage = gold*usd_eur*ratio/ask
    if leverage < 1 or not math.isfinite(leverage):
        raise ValueError('Hebel-Berechnung außerhalb des unterstützten Bereichs')
    oldest = min(bid_at, ask_at, gold_at, fx_at)
    local = now.astimezone(ZoneInfo('Europe/Berlin'))
    start = local.replace(hour=8, minute=0, second=0, microsecond=0)
    end = local.replace(hour=22, minute=0, second=0, microsecond=0)
    last_day = details.get('datetimeLastTradingDay')
    if last_day:
        # Stop conservatively at the source's last-trading timestamp.
        end = min(end, q.stamp(last_day).astimezone(ZoneInfo('Europe/Berlin')))
    market_open = local.weekday() < 5 and start <= local < end
    result = dict(found=True, productVerified=True, isin=isin, name=instrument['name'],
                  source='SG OTC via onvista · Hebel rechnerisch (Näherung)',
                  sourceUrl=product_url(isin), issuerSourceUrl=metadata['sourceUrl'],
                  checkedAt=now.isoformat(), quoteAt=oldest.isoformat(),
                  bidAt=bid_at.isoformat(), askAt=ask_at.isoformat(),
                  leverageAt=oldest.isoformat(), snapshotAt=oldest.isoformat(),
                  spotAt=gold_at.isoformat(), fxAt=fx_at.isoformat(),
                  fxDataAt=fx_data_at.isoformat(), fxEffectiveAt=fx_effective_at.isoformat(),
                  bid=bid, ask=ask, price=ask, leverage=leverage, ko=ko,
                  spread=round(ask-bid, 8), spreadPct=round((ask-bid)/ask*100, 4),
                  currency='EUR', direction=direction, marketOpen=market_open,
                  tradingEndAt=end.astimezone(timezone.utc).isoformat(),
                  isDegiroQuote=False, maxAgeSeconds=q.MAX_AGE_SECONDS,
                  leverageKind='calculated-gearing', leverageEstimated=True,
                  leverageInputs=dict(spotUsd=gold, usdEur=usd_eur, ratio=ratio, askEur=ask),
                  koSource='Société Générale · offizielle Produktdaten',
                  secondaryMetadataDiffers=(not math.isclose(secondary_ko, ko, rel_tol=1e-9)
                                            or not math.isclose(secondary_strike, strike, rel_tol=1e-9)),
                  leverageNote='Rechnerischer Hebel: Goldpreis × USD/EUR × Bezugsverhältnis / Briefkurs. '
                               'Näherung bei konstantem Wechselkurs und Delta ±1; kein SG-Hebelwert. '
                               'KO und Basispreis stammen direkt von SG.',
                  metadata=metadata['metadata'])
    result['productModel'] = dict(isin=isin, underlying='XAU/USD', direction=direction,
                                ratio=ratio, strike=strike, ko=ko,
                                classification=product['ProductClassificationId'],
                                verifiedSimpleTurbo=True, tradingEndAt=result['tradingEndAt'])
    return q.freshness(result, now)


def apply_product_estimate(result, now):
    """No network here: cache expiry can never refresh the input timestamps."""
    model = result.get('productModel')
    if not model:
        return result
    product_estimate.remember(result, model, now)
    if result.get('eligible'):
        result.pop('calculatedProduct', None)
        result['priceKind'] = 'observed-issuer'
        return result
    with _INPUT_LOCKS['spot']:
        spot = _INPUT_CACHE.get('spot', (0, {}))[1]
    with _INPUT_LOCKS['fx']:
        fx = _INPUT_CACHE.get('fx', (0, {}))[1]
    result['calculatedProduct'] = product_estimate.current(model, spot, fx, now)
    result['priceKind'] = 'calculated' if result['calculatedProduct']['available'] else 'unavailable'
    return result


def restore_product_model(fallback, product, properties):
    """Reuse only a recently observed model whose current issuer terms agree."""
    if (product.get('AssetNMP') != 'XAUUSD' or product.get('TodayBarrierHitDate')
            or not fallback.get('productVerified') or fallback['metadata']['status'] & (2|8|16|32)
            or not fallback['metadata']['status'] & 1):
        return fallback
    attrs = {p['Name']:p for p in properties}
    with product_estimate._lock:
        candidates = [a for a in product_estimate._anchors.values() if a['isin'] == fallback['isin']]
    for anchor in candidates:
        try:
            if (anchor['classification'] == product['ProductClassificationId']
                    and anchor['direction'] == fallback['metadata']['direction']
                    and anchor['ko'] == fallback['metadata']['ko']
                    and anchor['strike'] == q.number(attrs['Strike']['Value'])
                    and math.isclose(anchor['ratio']*q.number(attrs['Ratio']['Value']),1,rel_tol=1e-9)):
                fallback['productModel'] = {k:anchor[k] for k in
                    ('isin','underlying','direction','ratio','strike','ko','classification',
                     'verifiedSimpleTurbo','tradingEndAt')}
                return q.freshness(fallback)
        except (KeyError,ValueError,TypeError):
            pass
    return fallback


# Research is deliberately a separate envelope. Even fresh OTC product prices
# cannot authorize a future using the spot trend or a delayed basis price.
def refresh_future_research(research, now=None):
    now = now or datetime.now(timezone.utc)
    result = dict(research)
    def ages(keys):
        try:
            values = [(now-q.stamp(result[k])).total_seconds() for k in keys]
            return values if all(age >= -5 for age in values) else None
        except (KeyError, ValueError, TypeError):
            return None
    product_ages = ages(['bidAt', 'askAt'])
    basis_ages = ages(['underlyingAt'])
    fx_ages = ages(['fxDataAt', 'fxEffectiveAt'])
    result['productQuoteFresh'] = bool(product_ages and max(product_ages) <= q.MAX_AGE_SECONDS)
    result['productQuoteAgeSeconds'] = round(max(product_ages), 1) if product_ages else None
    result['underlyingAgeSeconds'] = round(max(basis_ages), 1) if basis_ages else None
    result['underlyingFresh'] = bool(basis_ages and max(basis_ages) <= q.MAX_AGE_SECONDS)
    result['eligible'] = False
    result['analysisAvailable'] = False
    result['calculatedFuture'] = future_estimate.current_estimate(result, now)
    result['futureReference'] = future_reference.select(result, result['calculatedFuture'], now)
    result['contractAnalysis'] = future_analysis.current(now)
    result['analysisAvailable'] = bool(result['contractAnalysis'].get('available'))
    local=now.astimezone(ZoneInfo('Europe/Berlin'))
    result['marketOpen'] = bool(local.weekday()<5 and 8<=local.hour<22 and result.get('tradingEndAt')
                                and now<=q.stamp(result['tradingEndAt']))
    # A labelled research estimate is bounded to a 30-minute observation.
    # It never enters price/leverage/KO inputs of the spot comparison.
    result.pop('indicativeLeverage', None)
    result.pop('indicativeKoDistancePct', None)
    result.pop('estimateAt', None)
    if (result['productQuoteFresh'] and basis_ages and max(basis_ages) <= 1800
            and fx_ages and max(fx_ages) <= q.MAX_AGE_SECONDS):
        basis, ko = result['underlyingPriceUsd'], result['ko']
        if ((result['direction'] == 'SHORT' and basis < ko and basis < result['strike'])
                or (result['direction'] == 'LONG' and basis > ko and basis > result['strike'])):
            estimate = basis*result['usdEur']*result['ratio']/result['ask']
            if math.isfinite(estimate) and estimate >= 1:
                result['indicativeLeverage'] = estimate
                result['indicativeKoDistancePct'] = abs(ko-basis)/basis*100
                result['estimateAt'] = min(q.stamp(result[k]) for k in
                    ['underlyingAt', 'askAt', 'fxDataAt', 'fxEffectiveAt']).isoformat()
    return result


def parse_future_research(product, properties, snapshot, fx, isin, now=None):
    now = now or datetime.now(timezone.utc)
    contract = q.sg_future_contract(product, isin)
    if contract is None:
        raise ValueError('Futures-Kontrakt oder Rollover nicht bestätigt')
    metadata, attrs, instrument, details, quote, underlying, ratio, bid, ask, *_ = validate_snapshot(product, properties, snapshot, isin, now)
    research = dict(contract=contract['ric'], underlying=contract['name'], underlyingType='FUTURE',
                    source='SG OTC via onvista · Futures-Recherche', sourceUrl=product_url(isin),
                    bid=bid, ask=ask, bidAt=q.stamp(quote['datetimeBid']).isoformat(),
                    askAt=q.stamp(quote['datetimeAsk']).isoformat(), currency='EUR',
                    direction=metadata['metadata']['direction'], ko=metadata['metadata']['ko'],
                    strike=q.number(attrs['Strike']['Value']), ratio=ratio,
                    underlyingDataState='verzögert oder Echtzeitstatus nicht bestätigt',
                    estimateNote='Nur Recherche: Näherung aus datiertem Futures-Kurs, USD/EUR und Briefkurs; '
                                 'kein aktueller SG-Hebel und kein aktueller KO-Abstand. '
                                 'Kontraktanalyse und Fehlermessung separat beachten. Keine Spot-Freigabe.')
    local=now.astimezone(ZoneInfo('Europe/Berlin'))
    end=local.replace(hour=22,minute=0,second=0,microsecond=0)
    if details.get('datetimeLastTradingDay'):
        end=min(end,q.stamp(details['datetimeLastTradingDay']).astimezone(ZoneInfo('Europe/Berlin')))
    research['tradingEndAt']=end.astimezone(timezone.utc).isoformat()
    # This is a dated figure from the exact underlying notation, not the
    # undated referencePrice or calculation/request timestamp.
    figures = underlying.get('derivativesBarrierFigureList', {})
    if (figures.get('idNotationUnderlying') == contract['notation_id']
            and figures.get('isoCurrencyUnderlying') == 'USD'):
        try:
            value = q.number(figures['priceUnderlying'])
            at = q.stamp(figures['datetimePriceUnderlying'])
            if value > 0 and (now-at).total_seconds() >= -5:
                research.update(underlyingPriceUsd=value, underlyingAt=at.isoformat())
        except (KeyError, ValueError, TypeError):
            pass
    try:
        if (fx['result'] == 'success' and fx['base'] == 'USD' and fx['source'] == 'live'
                and fx['sources']['EUR'] == 'live' and fx['market_session'] == 'open'):
            usd_eur = q.number(fx['rates']['EUR'])
            if usd_eur > 0:
                research.update(usdEur=usd_eur,
                                fxDataAt=q.stamp(fx['data_updated_at']).isoformat(),
                                fxEffectiveAt=q.stamp(fx['effective_at']['EUR']).isoformat())
    except (KeyError, ValueError, TypeError):
        pass
    metadata['futureResearch'] = refresh_future_research(research, now)
    metadata['researchAvailable'] = True
    metadata['reason'] = 'Gold-Future '+contract['ric']+': eigener bedingter Kontraktvergleich; keine Spot-Freigabe'
    return metadata


def get_quote(product, properties, isin):
    return q.sg_disabled(isin)
