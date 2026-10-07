"""Indicative SG gearing from independently dated inputs; never execution clearance."""
import copy
from datetime import datetime, timezone
import product_quotes as q


def calculate(result, basis, fx, now=None):
    now = now or datetime.now(timezone.utc)
    m = result['metadata']
    if not result.get('productVerified') or m.get('status') != 1 or not m.get('simpleNonQuantoTurbo'):
        raise ValueError('Einfaches Turbo-Modell ohne Quanto nicht bestätigt')
    kind = m.get('underlyingType')
    if kind == 'SPOT':
        if basis.get('underlying') != 'XAU/USD':
            raise ValueError('Passender Gold-Spotkurs fehlt')
    elif kind == 'FUTURE':
        if not m.get('contract') or basis.get('contract') != m['contract'] or basis.get('underlyingType') != 'FUTURE':
            raise ValueError('Passender Future-Kontrakt fehlt')
    else:
        raise ValueError('Basiswert nicht unterstützt')
    quote = result if result.get('found') else result.get('analysisQuote') or {}
    if quote.get('currency') != 'EUR' or fx.get('result') != 'success' or fx.get('base') != 'USD':
        raise ValueError('Produkt- oder Wechselkurswährung nicht bestätigt')
    price, gold, ratio, rate = (q.number(v) for v in (quote['ask'], basis['price'], m['ratio'], fx['rates']['EUR']))
    if min(price, gold, ratio, rate) <= 0:
        raise ValueError('Positive Berechnungswerte fehlen')
    times = [q.stamp(v) for v in (quote['askAt'], basis['at'], fx['data_updated_at'], fx['effective_at']['EUR'])]
    ages = [(now-t).total_seconds() for t in times]
    if min(ages) < 0 or max(ages) > 1800:
        raise ValueError('Eingangsdaten zukünftig oder älter als 30 Minuten')
    skew = (max(times)-min(times)).total_seconds()
    fresh = (max(ages) <= 90 and skew <= 90 and basis.get('delayed') is not True
             and fx.get('source') == 'live' and fx.get('sources', {}).get('EUR') == 'live'
             and fx.get('market_session') == 'open')
    return dict(available=True,value=gold*rate*ratio/price, at=min(times).isoformat(), calculatedAt=now.isoformat(),
                fresh=fresh, state='aktuelle Eingangsdaten' if fresh else 'veraltete oder zeitlich abweichende Eingangsdaten',
                kind='calculated-gearing', label='Von Bob berechneter Hebel',
                maxInputAgeSeconds=round(max(ages),1), skewSeconds=round(skew,1),
                inputs=dict(basisPriceUsd=gold,basisAt=times[1].isoformat(),basisSource=basis['source'],
                            contract=m.get('contract'),ratio=ratio,askEur=price,askAt=times[0].isoformat(),
                            priceSource=quote.get('source',result.get('source')),usdEur=rate,
                            fxDataAt=times[2].isoformat(),fxEffectiveAt=times[3].isoformat(),
                            fxSource='exchangerate.dev · USD/EUR',priceKind=quote.get('priceKind')),
                note='Rechnerische Näherung mit Delta ±1; kein bestätigter Emittentenhebel oder ausführbarer Kurs.')


def apply(result, now=None):
    supplied_now = now
    now = now or datetime.now(timezone.utc)
    m = result.get('metadata', {})
    if not result.get('productVerified') or m.get('status') != 1 or not m.get('simpleNonQuantoTurbo'):
        return result
    try:
        if result.get('leverage') and 0 <= (now-q.stamp(result['leverageAt'])).total_seconds() <= 90:
            return result
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    out = copy.deepcopy(result)
    try:
        if m.get('underlyingType') == 'SPOT':
            from spot_data import current
            basis = current()
        else:
            from future_analysis import fetch_reference
            ref = fetch_reference()
            basis = dict(price=ref['underlyingPriceUsd'], at=ref['underlyingAt'], source=ref['source'],
                         contract=ref['contract'], underlyingType='FUTURE',delayed=not ref['isExchangeRealtime'])
        from sg_quotes import market_input
        evidence = calculate(out,basis,market_input('fx'),supplied_now or datetime.now(timezone.utc))
        out['leverageCalculation'] = evidence
        old = out.get('leverageAt')
        if old and out.get('leverage') and q.stamp(old) >= q.stamp(evidence['at']):
            return out
        out['providerLeverage'] = dict(value=out.get('leverage'),at=old,source=out.get('source'))
        out.update(leverage=evidence['value'],leverageAt=evidence['at'],leverageEstimated=True,
                   leverageSource='Bob · berechneter Hebel',eligible=False,fresh=False,
                   leverageNote=evidence['label']+' · '+evidence['state']+'. '+evidence['note'])
        out['reason'] = 'Produktwerte übernommen; '+out['leverageNote']
    except (KeyError,TypeError,ValueError,OSError,AttributeError) as exc:
        out['leverageCalculation'] = dict(available=False,reason=str(exc) if isinstance(exc,ValueError) else 'Eingangsdaten nicht verfügbar')
    return out
