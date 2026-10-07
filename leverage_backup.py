"""Indicative SG gearing from independently dated inputs; never execution clearance."""
import copy
import logging
import json
import threading
from collections import OrderedDict

_COMPARISONS = OrderedDict()
_COMPARISON_LOCK = threading.Lock()
MAX_SKEW_SECONDS = 30  # Initial monitoring threshold, not a guarantee of accuracy.

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
    inputs_fresh = (max(ages) <= 90 and skew <= MAX_SKEW_SECONDS and basis.get('delayed') is not True
             and fx.get('source') == 'live' and fx.get('sources', {}).get('EUR') == 'live'
             and fx.get('market_session') == 'open')
    return dict(available=True,value=gold*rate*ratio/price, at=min(times).isoformat(), calculatedAt=now.isoformat(),
                fresh=inputs_fresh and not basis.get('estimated',False), inputsFresh=inputs_fresh, state='CFD-basierte Schätzung; Quellenalter und Zeitabstand separat prüfen' if basis.get('estimated') else 'aktuelle Eingangsdaten' if inputs_fresh else 'veraltete oder zeitlich abweichende Eingangsdaten',
                kind='calculated-gearing', label='Von Bob geschätzter Hebel auf Basis des Investing-CFD' if basis.get('estimated') else 'Von Bob berechneter Hebel',
                maxInputAgeSeconds=round(max(ages),1), skewSeconds=round(skew,1),
                inputs=dict(priceSide='ask',basisEstimated=bool(basis.get('estimated',False)),basisDelayed=bool(basis.get('delayed',False)),basisPriceUsd=gold,basisAt=times[1].isoformat(),basisSource=basis['source'],
                            contract=m.get('contract'),ratio=ratio,askEur=price,askAt=times[0].isoformat(),
                            priceSource=quote.get('source',result.get('source')),usdEur=rate,
                            currencyModelEvidence=m.get('currencyModelEvidence'),
                            fxDataAt=times[2].isoformat(),fxEffectiveAt=times[3].isoformat(),
                            fxSource='exchangerate.dev · USD/EUR',priceKind=quote.get('priceKind')),
                note='Rechnerische Näherung mit Delta ±1; kein bestätigter Emittentenhebel oder ausführbarer Kurs.')


def apply(result, now=None):
    supplied_now = now
    now = now or datetime.now(timezone.utc)
    m = result.get('metadata', {})
    if not result.get('productVerified') or m.get('status') != 1:
        return result
    if 'simpleNonQuantoTurbo' not in m:
        return result
    if not m.get('simpleNonQuantoTurbo'):
        return dict(result,leverageCalculation=dict(available=False,
            reason='Berechnungsmodell nicht bestätigt: SG-Angabe zur Währungsabsicherung oder zum einfachen Turbo-Modell fehlt'))
    out = copy.deepcopy(result)
    try:
        if m.get('underlyingType') == 'SPOT':
            from spot_data import current
            basis = current()
        else:
            from investing_card import fetch
            cfd = fetch()
            if cfd.get('kind') != 'cfd' or cfd.get('declaredContract') != m.get('contract') or not m.get('contract'):
                raise ValueError('Investing-CFD: Zuordnung zum Produkt-Future nicht bestätigt')
            basis = dict(price=cfd['price'], at=cfd['at'], source='Investing.com · angezeigter Gold-CFD',
                         contract=cfd['declaredContract'], underlyingType='FUTURE', estimated=True,
                         delayed=not cfd.get('realtimeCfd',False))
        from sg_quotes import market_input
        evidence = calculate(out,basis,market_input('fx'),supplied_now or datetime.now(timezone.utc))
        out['leverageCalculation'] = evidence
        old = out.get('leverageAt')
        out['leverageComparison'] = compare(out, evidence, supplied_now or datetime.now(timezone.utc))
        if old and out.get('leverage') and not out.get('leverageEstimated') and 0 <= (now-q.stamp(old)).total_seconds() <= 90:
            return out
        if old and out.get('leverage') and q.stamp(old) >= q.stamp(evidence['at']):
            return out
        out['providerLeverage'] = dict(value=out.get('leverage'),at=old,source=out.get('source'))
        out.update(leverage=evidence['value'],leverageAt=evidence['at'],leverageEstimated=True,
                   leverageSource='Bob · CFD-basierter geschätzter Hebel' if basis.get('estimated') else 'Bob · berechneter Hebel',eligible=False,fresh=False,
                   leverageNote=evidence['label']+' · '+evidence['state']+'. '+evidence['note'])
        if m.get('currencyModelEvidence'):
            out['leverageNote'] += ' Währungsumrechnung: nicht währungsgesichert laut Onvista-Produktbedingungen; USD/EUR berücksichtigt.'
        out['reason'] = 'Produktwerte übernommen; '+out['leverageNote']
    except (KeyError,TypeError,ValueError,OSError,AttributeError) as exc:
        out['leverageCalculation'] = dict(available=False,reason=str(exc) if isinstance(exc,ValueError) else 'Eingangsdaten nicht verfügbar')
    return out


def compare(result, evidence, now):
    """Compare only independent, fresh, aligned observations; log each pair once."""
    skipped = dict(comparable=False, reason='Kein zeitlich passender aktueller Anbieterhebel')
    try:
        provider = q.number(result['leverage'])
        at = q.stamp(result['leverageAt'])
        times = [q.stamp(evidence['inputs'][k]) for k in ('basisAt','askAt','fxDataAt','fxEffectiveAt')]
        if (provider <= 0 or result.get('leverageEstimated') or not evidence['fresh']
                or not 0 <= (now-at).total_seconds() <= 90
                or (max(times+[at])-min(times+[at])).total_seconds() > MAX_SKEW_SECONDS):
            return skipped
        difference = (evidence['value']/provider-1)*100
        row = dict(comparable=True, isin=result.get('isin'), providerValue=provider,
                   providerAt=at.isoformat(), providerSource=result.get('leverageSource') or result.get('source'),
                   calculatedValue=evidence['value'], calculatedAt=evidence['at'],
                   relativeDifferencePct=round(difference,4), warning=abs(difference)>5,
                   warningThresholdPct=5, priceSide='ask',
                   note='Abweichung ist kein Fehlernachweis; Anbieter-Kursbasis kann abweichen.',
                   inputs=evidence['inputs'])
        key = json.dumps(row,sort_keys=True)
        with _COMPARISON_LOCK:
            if key not in _COMPARISONS:
                _COMPARISONS[key] = True
                if len(_COMPARISONS)>2048:
                    _COMPARISONS.popitem(last=False)
                logging.getLogger(__name__).warning('BOB_LEVERAGE_COMPARISON %s',key)
        return row
    except (KeyError,ValueError,TypeError,AttributeError):
        return skipped
