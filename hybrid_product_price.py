"""Research-only product valuation calibrated to SG/comdirect dated quotes.

The DEGIRO list identifies which instrument to watch; its generic 'last'
price is not silently promoted to a bid/ask anchor. No orders or approvals.
"""
import math
import threading
from datetime import datetime, timezone, time as clock_time
from zoneinfo import ZoneInfo

import product_estimate
import estimate_quality
import product_validation_store

_LOCK = threading.Lock()
_ANCHORS = {}
MAX_ANCHOR_AGE_SECONDS = 1800
MAX_QUOTE_AGE_SECONDS = 90
MAX_MODEL_SKEW_SECONDS = 30  # Larger source/Gold/FX gaps undermine accurate calibration.


def utc(at):
    if not isinstance(at, str):
        raise ValueError('Quellenzeit fehlt')
    t = datetime.fromisoformat(at.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Zeitzone fehlt')
    return t.astimezone(timezone.utc)


def positive(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0


def bnp_model(result, now):
    """Exact BNP terms plus independently matched explicit currency treatment."""
    m = result.get('metadata') or {}
    isin = result.get('isin')
    if (not isinstance(isin, str) or result.get('sourceUrl') !=
            'https://derivate.bnpparibas.com/product-details/'+isin+'/'
            or not str(result.get('source', '')).startswith('BNP Paribas ·')
            or result.get('productVerified') is not True
            or result.get('importActive') is not True
            or result.get('sourceDisabled') or result.get('sourceFailure')
            or result.get('quoteFailureCode') not in (None, 'STALE_OR_INVALID_SOURCE_TIME', 'MISSING_QUOTE_TIME')
            or m.get('status') != 1 or m.get('tradingHalted')
            or m.get('simpleTurbo') is not True
            or m.get('currency') != 'EUR' or m.get('underlying') != 'XAU/USD'
            or m.get('underlyingType') != 'SPOT'
            or m.get('direction') not in ('LONG', 'SHORT')
            or not all(positive(m.get(k)) for k in ('ratio', 'strike', 'ko'))):
        return None
    fields = result.get('comdirectFieldsBackup') or {}
    obs = fields.get('observations') or {}
    if (fields.get('isin') != isin or fields.get('inactive')
            or fields.get('state') not in ('active', 'conflict') or set(fields.get('conflicts') or []) - {'type'}
            or fields.get('source') != 'https://www.comdirect.de/inf/zertifikate/'+isin
            or obs.get('quanto', {}).get('value') is not False
            or obs.get('issuer', {}).get('value') != 'BNP Paribas'
            or any(obs.get(k, {}).get('value') != m[k]
                   for k in ('ratio', 'direction', 'currency', 'underlying'))):
        return None
    try:
        if not 0 <= (now-utc(fields['checkedAt'])).total_seconds() <= 86400:
            return None
        today = now.astimezone(ZoneInfo('Europe/Zurich')).strftime('%d.%m.%Y')
        for k in ('strike', 'ko'):
            term = result['conditions'][k]
            if (term.get('conditionVerified') is not True or term.get('value') != m[k]
                    or term.get('dateText') != today or term.get('conflict')):
                return None
    except (KeyError, ValueError, TypeError):
        return None
    local = now.astimezone(ZoneInfo('Europe/Zurich'))
    if local.weekday() >= 5 or not 8 <= local.hour < 22:
        return None
    close = datetime.combine(local.date(), clock_time(22), tzinfo=local.tzinfo)
    return dict(isin=isin, underlying='XAU/USD', direction=m['direction'],
                ratio=m['ratio'], strike=m['strike'], ko=m['ko'],
                classification='BNP_UNLIMITED', provider='BNP', verifiedSimpleTurbo=True,
                tradingEndAt=close.astimezone(timezone.utc).isoformat())


def model_for(result, now):
    origin = result.get('issuerModelSource') or {}
    if origin.get('isin') == result.get('isin'):
        result = dict(result, source=origin.get('source'), sourceUrl=origin.get('sourceUrl'))
    if str(result.get('source', '')).startswith('BNP Paribas ·'):
        return bnp_model(result, now)
    m = result.get('metadata') or {}
    if (not isinstance(result.get('isin'), str)
            or result.get('sourceUrl') !=
                'https://www.sg-zertifikate.de/product-details/'+result['isin'].lower()
            or result.get('productVerified') is not True
            or result.get('sourceDisabled') or result.get('sourceFailure')
            or result.get('quoteFailureCode')
            or result.get('importActive') is not True
            or m.get('status') != 1 or m.get('tradingHalted') is True
            or m.get('issuerExchangeCode') != 'CBDE'
            or m.get('currency') != 'EUR'
            or m.get('underlying') != 'XAU/USD'
            or m.get('underlyingType') != 'SPOT'
            or m.get('simpleNonQuantoTurbo') is not True
            or m.get('classificationId') not in (43, 45, 47)
            or m.get('direction') not in ('LONG','SHORT')
            or not all(positive(m.get(k)) for k in ('ratio','strike','ko'))):
        return None
    now_local = now.astimezone(ZoneInfo('Europe/Zurich'))
    if now_local.weekday() >= 5 or not 8 <= now_local.hour < 22:
        return None
    # Conservative read-only policy ceiling, NOT issuer-confirmed trading end.
    policy_close = datetime.combine(now_local.date(), clock_time(22), tzinfo=now_local.tzinfo)
    maturity = (result.get('conditions') or {}).get('maturity', {}).get('value')
    if isinstance(maturity, str) and maturity != 'Open End':
        try:
            expires = datetime.strptime(maturity, '%d.%m.%Y').date()
        except ValueError:
            return None
        if expires < now_local.date():
            return None
    return dict(isin=result['isin'], underlying='XAU/USD',
                direction=m['direction'], ratio=m['ratio'], strike=m['strike'],
                ko=m['ko'], classification=m['classificationId'],
                verifiedSimpleTurbo=True,
                tradingEndAt=policy_close.astimezone(timezone.utc).isoformat())


def observations(result):
    """Native research quotes; no executable/derived/other-currency sources."""
    chart=result.get('chartEvidence') or {}
    native=result.get('analysisQuote') or {}
    backup=result.get('secondaryQuote') or {}
    pool=[]
    bnp = str((result.get('issuerModelSource') or {}).get('source', result.get('source', ''))).startswith('BNP Paribas ·')
    if bnp and str(result.get('source', '')).startswith('BNP Paribas ·') and result.get('found') and result.get('currency') == 'EUR' and all(positive(result.get(k)) for k in ('bid','ask')) and result['ask'] >= result['bid']:
        pool.append(dict(result, priceKind='issuer-observation'))
    if (chart.get('currency') == 'EUR' and
            all(positive(chart.get(k)) for k in ('bid','ask')) and
            chart['ask'] >= chart['bid'] and isinstance(chart.get('pointAt'), str)):
        pool.append(dict(isin=result['isin'],source='SG · Live-Chart',
                         priceKind='issuer-chart', bid=chart['bid'],ask=chart['ask'],
                         bidAt=chart['pointAt'],askAt=chart['pointAt'],currency='EUR'))
    for row in (native,backup):
        if (row.get('isin') == result['isin']
                and row.get('priceKind') == 'market-observation'
                and row.get('currency') == 'EUR'
                and row.get('isExecutableQuote') is False
                and row.get('degiroExecutable') is False
                and row.get('delayed') is not True
                and row.get('estimated') is not True
                and row.get('source') == ('comdirect · BNP LiveTrading' if bnp else 'comdirect · SG LiveTrading')
                and row.get('venue') == ('LT BNP Paribas' if bnp else 'LT Societe Generale')
                and row.get('sourceUrl') ==
                    'https://www.comdirect.de/inf/zertifikate/'+result['isin']
                and all(positive(row.get(k)) for k in ('bid','ask'))
                and row['ask'] >= row['bid']):
            pool.append(row)
    return pool


def validation_key(model, side):
    # Separate from issuer/legacy and Future quality; one exact product identity.
    import product_validation_store
    return product_validation_store.key(model, side, family='hybrid')


def adapter_spot(source, now):
    s=source()
    # spot_data.current validates the original source at <=60 seconds.
    t=utc(s['at'])
    if not positive(s.get('price')) or not 0 <= (now-t).total_seconds() <= 60:
        raise ValueError('Gold-Spot nicht ausreichend aktuell')
    return dict(stale=False,data_state={'status':'fresh'},
                xau={'currency':'USD','unit':'troy_oz'},
                spot_usd_oz=s['price'],price_as_of=t.isoformat())


def adapter_fx(source, now):
    f=source()
    if (f.get('result') != 'success' or f.get('base') != 'USD'
            or f.get('source') != 'live' or f.get('market_session') != 'open'
            or (f.get('sources') or {}).get('EUR') != 'live'
            or not positive((f.get('rates') or {}).get('EUR'))):
        raise ValueError('USD/EUR-Echtzeitkurs fehlt')
    times=[utc(f['data_updated_at']),utc(f['effective_at']['EUR'])]
    if any(not 0 <= (now-t).total_seconds() <= 60 for t in times):
        raise ValueError('FX-Originalzeiten fehlen oder sind veraltet')
    return f


def apply(result, now=None, fetch_spot=None, fetch_fx=None):
    """Attach a provenance-labelled display-only model, never replace quotes."""
    now=now or datetime.now(timezone.utc)
    # A cached projection is an output, never an anchor or a reason to skip
    # recalculation. Drop it before validation so expired/invalid inputs cannot
    # leave yesterday's projection marked available. Keep caller data intact.
    if (result.get('calculatedProduct') or {}).get('anchorKind') == 'research-hybrid':
        result=dict(result)
        result.pop('calculatedProduct',None)
        result.pop('hybridModelState',None)
    model=model_for(result,now)
    if not model:
        return result
    # Keep the original quote in front, but warm its validated model anchor
    # before a future outage. This already applies to BNP and also covers SG.
    # Legacy fully qualified issuer estimate always has precedence.
    if (result.get('calculatedProduct') or {}).get('available'):
        return result
    if fetch_spot is None:
        from spot_data import current as fetch_spot
    if fetch_fx is None:
        from sg_quotes import market_input
        fetch_fx=lambda:market_input('fx')
    try:
        spot=adapter_spot(fetch_spot,now)
        fx=adapter_fx(fetch_fx,now)
        times=[utc(spot['price_as_of']),utc(fx['data_updated_at']),
               utc(fx['effective_at']['EUR'])]
        if (max(times)-min(times)).total_seconds()>15:
            raise ValueError('Gold-/FX-Eingänge nicht zeitgleich')
        gold,rate=spot['spot_usd_oz'],fx['rates']['EUR']
        d=1 if model['direction']=='LONG' else -1
        if d*(gold-model['ko'])<=0 or d*(gold-model['strike'])<=0:
            raise ValueError('KO-/Basispreis bereits erreicht')
        key=product_estimate.identity(model)
        candidate=None
        for row in observations(result):
            try:
                b=utc(row['bidAt']);a=utc(row['askAt'])
            except (KeyError,ValueError,TypeError):
                continue
            joined=times+[b,a]
            if (min((now-t).total_seconds() for t in joined)<0
                    or max((now-t).total_seconds() for t in joined)>MAX_QUOTE_AGE_SECONDS
                    or (max(joined)-min(joined)).total_seconds()>MAX_MODEL_SKEW_SECONDS
                    or (a-b).total_seconds()>30 or (b-a).total_seconds()>30):
                continue
            if candidate is None or min(a,b)>candidate['at']:
                candidate=dict(at=min(a,b), row=row,skew=(max(joined)-min(joined)).total_seconds())
        with _LOCK:
            previous=_ANCHORS.get(key)
            if (candidate and previous and candidate['at'] == utc(previous['referenceAt'])
                    and (candidate['row']['bid'] != previous['bid']
                         or candidate['row']['ask'] != previous['ask'])):
                _ANCHORS.pop(key,None)
                return result  # Same original source clock cannot have two prices.
            if candidate and (previous is None or candidate['at'] > utc(previous['referenceAt'])):
                new=dict(model,bid=float(candidate['row']['bid']),
                         ask=float(candidate['row']['ask']),
                         underlyingPriceUsd=gold,usdEur=rate,
                         referenceAt=candidate['at'].isoformat(),
                         referenceSkewSeconds=candidate['skew'],
                         researchSource=candidate['row']['source'],
                         researchKind=candidate['row']['priceKind'])
                _ANCHORS[key]=new
                if len(_ANCHORS)>256:
                    _ANCHORS.pop(next(iter(_ANCHORS)))
            anchor=_ANCHORS.get(key)
            anchor=dict(anchor) if anchor else None
        if not anchor:
            # A stale BNP quote with no previously dated, aligned reference
            # cannot be extrapolated. Explain the gap, rather than fabricate
            # a current issuer price or grant broker/Top-3 eligibility.
            if model.get('provider') == 'BNP' and result.get('eligible') is not True:
                out=dict(result)
                out['hybridModelState']='awaiting-original-reference'
                out['hybridEstimateReason']='Kein ausreichend zeitgleicher, bestätigter BNP-Originalkurs als Referenz'
                return out
            return result
        if result.get('eligible') is True:
            return result
        # Prospective-only forecast validation. The prediction must already have
        # been frozen in an earlier request before today's new quote arrives.
        # Never validate against the same source pair that calibrated the anchor.
        if candidate and previous and candidate['at'] > utc(previous['referenceAt']):
            for side in ('bid','ask'):
                estimate_quality.observe(validation_key(model,side),
                    float(candidate['row'][side]),
                    candidate['row'][side+'At'],now.isoformat())
        if previous and (candidate is None or candidate['at']>utc(previous['referenceAt'])):
            frozen=product_estimate.calculate(model,previous,spot,fx,now)
            if frozen.get('available'):
                prediction_time=utc(frozen['priceAt'])
                quote_is_same=candidate and abs((candidate['at']-prediction_time).total_seconds())<=5
                if not quote_is_same:
                    for side in ('bid','ask'):
                        estimate_quality.record(validation_key(model,side),
                            frozen[side+'Eur'],frozen['priceAt'],
                            previous['referenceAt'],now.isoformat())
        projected=product_estimate.calculate(model,anchor,spot,fx,now)
        if not projected['available']:
            if model.get('provider') == 'BNP' and result.get('eligible') is not True:
                out=dict(result)
                out['hybridModelState']='unavailable'
                out['hybridEstimateReason']=projected.get('reason', 'Berechnung derzeit nicht verlässlich')
                return out
            return result
        projected.update(anchorKind='research-hybrid',
                         source='Bob · '+('BNP' if model.get('provider') == 'BNP' else 'SG')+'/comdirect + Gold/FX',
                         referenceSource=anchor['researchSource'],
                         referenceClockGapSeconds=anchor['referenceSkewSeconds'],
                         referenceTimeReliability='original source times, <=30 s apart',
                         referencePriceKind=anchor['researchKind'],
                         validation=dict(
                             estimate_quality.quality(validation_key(model,'ask'),
                                max(1,(now-utc(anchor['referenceAt'])).total_seconds()),now),
                             source='prospective-sg-comdirect',
                             basis='Originaler späterer Emittentenkurs gegen zuvor eingefrorene Modellprognose',
                             persistence=product_validation_store.status(validation_key(model,'ask')),
                             affectsApproval=False),
                         note='Nur indikative Recherche-Kalibrierung mit beobachtetem '
                              'Emittenten-/comdirect-Preis und aktuellem Gold/FX. '
                              'Quellzeiten beim Kalibrieren bis 30 s auseinander; '
                              'bei starken Goldbewegungen verbleibt Modellrisiko. '
                              'Messfehler nur aus unabhängigen späteren Originalkursen; '
                              'kein tatsächlicher DEGIRO-Kurs, keine garantierte Genauigkeit.')
        out=dict(result)
        out['productModel']=model
        out['calculatedProduct']=projected
        out['hybridModelState']='research-only'
        return out
    except (KeyError,TypeError,ValueError,OverflowError,OSError):
        return result
