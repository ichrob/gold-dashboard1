"""Indicative SG gearing from independently dated inputs; never execution clearance."""
import copy
import math
import logging
import json
import threading
from collections import OrderedDict

_COMPARISONS = OrderedDict()
_COMPARISON_LOCK = threading.Lock()
MAX_SKEW_SECONDS = 90  # User-selected tolerance for indicative analysis.
MAX_INPUT_AGE_SECONDS = 300  # Original clocks remain visible; not execution clearance.

from datetime import datetime, timezone
import product_quotes as q


def select_analysis_quote(result, now=None):
    """One dated price pair for both the product display and gearing inputs."""
    now = now or datetime.now(timezone.utc)
    quote = result if result.get('found') else result.get('analysisQuote') or {}
    backup = result.get('analysisQuote') or {}
    try:
        if (backup.get('priceKind') == 'market-observation'
                and backup.get('isin') == result.get('isin')
                and not backup.get('estimated') and not backup.get('delayed')
                and backup.get('currency') == (quote.get('currency') or (result.get('metadata') or {}).get('currency'))
                and 0 <= (now-q.stamp(backup['bidAt'])).total_seconds() <= 90
                and backup.get('currency') == 'EUR'
                and 0 < q.number(backup['bid']) <= q.number(backup['ask'])
                and 0 <= (now-q.stamp(backup['askAt'])).total_seconds() <= 90
                and (not quote.get('askAt') or not quote.get('bidAt') or
                     min(q.stamp(backup['askAt']),q.stamp(backup['bidAt'])) >
                     min(q.stamp(quote['askAt']),q.stamp(quote['bidAt'])))):
            quote = backup
    except (KeyError, TypeError, ValueError):
        pass
    chart = result.get('chartEvidence') or {}
    try:
        chart_at = q.stamp(chart['pointAt'])
        quote_at = q.stamp(quote['askAt']) if quote.get('askAt') else datetime.min.replace(tzinfo=timezone.utc)
        chart_bid, chart_ask = q.number(chart['bid']), q.number(chart['ask'])
        if (chart.get('currency') == 'EUR' and 0 < chart_bid <= chart_ask
                and math.isfinite(chart_ask)
                and 0 <= (now-chart_at).total_seconds() <= MAX_INPUT_AGE_SECONDS
                and chart_at > quote_at):
            quote = dict(bid=chart_bid, ask=chart_ask, price=chart_ask,
                         bidAt=chart['pointAt'], askAt=chart['pointAt'],
                         quoteAt=chart['pointAt'], currency='EUR',
                         source='SG · datierter Chartkurs'+(' · CHF in EUR umgerechnet' if result.get('currencyConversion') else ''),
                         priceKind='issuer-chart', isExecutableQuote=False)
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return quote


def calculate(result, basis, fx, now=None, quote_override=None):
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
    quote = quote_override if quote_override is not None else select_analysis_quote(result, now)
    currency = quote.get('currency')
    # Native CHF research is possible without silently turning the product
    # into EUR. Executable quote and product release stay independently gated.
    if (currency not in ('EUR', 'CHF') or fx.get('result') != 'success'
            or fx.get('base') != 'USD'):
        raise ValueError('Produkt- oder Wechselkurswährung nicht bestätigt')
    price, gold, ratio, rate = (q.number(v) for v in
                               (quote['ask'], basis['price'], m['ratio'], fx['rates'][currency]))
    if min(price, gold, ratio, rate) <= 0:
        raise ValueError('Positive Berechnungswerte fehlen')
    times = [q.stamp(v) for v in (quote['askAt'], basis['at'], fx['data_updated_at'], fx['effective_at'][currency])]
    ages = [(now-t).total_seconds() for t in times]
    if min(ages) < 0 or max(ages) > 1800:
        raise ValueError('Eingangsdaten zukünftig oder älter als 30 Minuten')
    skew = (max(times)-min(times)).total_seconds()
    inputs_fresh = (max(ages) <= MAX_INPUT_AGE_SECONDS and skew <= MAX_SKEW_SECONDS and basis.get('delayed') is not True
             and fx.get('source') == 'live' and fx.get('sources', {}).get(currency) == 'live'
             and fx.get('market_session') == 'open')
    return dict(available=True,value=gold*rate*ratio/price, at=min(times).isoformat(), calculatedAt=now.isoformat(),
                fresh=inputs_fresh and not basis.get('estimated',False), inputsFresh=inputs_fresh, state='CFD-basierte Schätzung; Quellenalter und Zeitabstand separat prüfen' if basis.get('estimated') else 'aktuelle Eingangsdaten' if inputs_fresh else 'veraltete oder zeitlich abweichende Eingangsdaten',
                kind='calculated-gearing', label='Von Bob geschätzter Hebel auf Basis des Investing-CFD' if basis.get('estimated') else 'Von Bob berechneter Hebel',
                maxInputAgeSeconds=round(max(ages),1), skewSeconds=round(skew,1),
                maxAllowedInputAgeSeconds=MAX_INPUT_AGE_SECONDS, maxAllowedSkewSeconds=MAX_SKEW_SECONDS,
                inputs=dict(priceSide='ask',basisEstimated=bool(basis.get('estimated',False)),basisDelayed=bool(basis.get('delayed',False)),basisPriceUsd=gold,basisAt=times[1].isoformat(),basisSource=basis['source'],
                            contract=m.get('contract'),ratio=ratio,askEur=price if currency=='EUR' else None,
                            askNative=price,quoteCurrency=currency,askAt=times[0].isoformat(),
                            priceSource=quote.get('source',result.get('source')),usdEur=rate,
                            currencyModelEvidence=m.get('currencyModelEvidence'),
                            fxDataAt=times[2].isoformat(),fxEffectiveAt=times[3].isoformat(),
                            fxSource=fx.get('provider','exchangerate.dev · USD/'+currency),priceKind=quote.get('priceKind')),
                note='Rechnerische Näherung mit Delta ±1; kein bestätigter Emittentenhebel oder ausführbarer Kurs.')



# A bounded historical reference is useful after the last market close, but it
# must never satisfy the live 90-second leverage clock or executable-price gate.
HISTORICAL_REFERENCE_MAX_AGE_SECONDS = 4 * 24 * 3600


def historical_reference(result, now=None):
    """Previously issuer-confirmed or reproducibly calculated leverage.

    Never call live feeds, manufacture timestamps, or change result['leverage'].
    Weekend snapshots are research-only even if their original input was fresh.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(result, dict) or result.get('productVerified') is not True:
        return None
    meta = result.get('metadata') or {}
    isin = result.get('isin')
    if (meta.get('status') != 1 or not isinstance(isin, str)
            or not q.valid_isin(isin)):
        return None

    def when(raw):
        try:
            at = q.stamp(raw)
            return at if 0 <= (now-at).total_seconds() <= HISTORICAL_REFERENCE_MAX_AGE_SECONDS else None
        except (ValueError, TypeError, KeyError, OverflowError):
            return None

    def positive(raw):
        try:
            value = q.number(raw)
            return value if math.isfinite(value) and value > 0 else None
        except (ValueError, TypeError):
            return None

    original = positive(result.get('leverage'))
    original_at = when(result.get('leverageAt'))
    if original and original_at and result.get('leverageEstimated') is not True:
        return dict(value=original, at=original_at.isoformat(), source=str(result.get('source') or 'Emittent')[:80],
                    kind='historical-issuer-leverage', label='Letzter Originalhebel',
                    current=False, researchOnly=True, tradeApproved=False,
                    note='Ursprünglicher Emittentenzeitpunkt; kein aktueller Hebel oder DEGIRO-Handelskurs.')

    # A prior weekend calculation is accepted only with all immutable inputs
    # and their ORIGINAL clocks. A fabricated leverageCalculation without a
    # verified simple non-quanto turbo model cannot become even a reference.
    calculation = result.get('leverageCalculation') or {}
    inputs = calculation.get('inputs') or {}
    if (meta.get('simpleNonQuantoTurbo') is not True
            or not calculation.get('available') or calculation.get('fresh') is not True
            or inputs.get('basisEstimated') or inputs.get('basisDelayed')
            or inputs.get('quoteCurrency') not in ('EUR', 'CHF')
            or inputs.get('quoteCurrency') != meta.get('currency')
            or inputs.get('priceKind') in ('calculated', 'model', 'estimated')
            or meta.get('underlyingType') not in ('SPOT', 'FUTURE')):
        return None
    try:
        original_times = [q.stamp(inputs[name]) for name in ('askAt', 'basisAt', 'fxDataAt', 'fxEffectiveAt')]
        if not all(when(t.isoformat()) for t in original_times):
            return None
        if (max(original_times)-min(original_times)).total_seconds() > MAX_SKEW_SECONDS:
            return None
        reference_at = min(original_times)
        if q.stamp(calculation['at']) != reference_at:
            return None
        if q.stamp(calculation['calculatedAt']) < max(original_times) or q.stamp(calculation['calculatedAt']) > now:
            return None
        ask, gold, fx, ratio, value = [positive(v) for v in
            (inputs['askNative'], inputs['basisPriceUsd'], inputs['usdEur'],
             inputs['ratio'], calculation['value'])]
        if None in (ask, gold, fx, ratio, value) or ratio != meta.get('ratio'):
            return None
        if not math.isclose(value, gold*fx*ratio/ask, rel_tol=1e-9):
            return None
        if meta.get('underlyingType') == 'FUTURE' and (not meta.get('contract') or
                inputs.get('contract') != meta['contract']):
            return None
        return dict(value=value, at=reference_at.isoformat(), source=str(inputs.get('priceSource') or 'Bob · Berechnung')[:80],
                    kind='historical-calculated-gearing', label='Historisch berechneter Hebel',
                    current=False, researchOnly=True, tradeApproved=False,
                    note='Rechnerischer Referenzhebel aus denselben früheren Produkt-, Gold- und FX-Zeitpunkten; nicht aktuell.')
    except (KeyError, ValueError, TypeError, OverflowError):
        return None

def reconcile_model(result, now):
    """Use explicit same-product comdirect contract proof for an unknown model."""
    out = copy.deepcopy(result)
    m = out.get('metadata') or {}
    if m.pop('comdirectModelFallback', False):
        m.update(simpleNonQuantoTurbo=False, quantoState='unknown')
        m.pop('currencyModelEvidence', None)
    if (not out.get('productVerified') or m.get('status') != 1
            or m.get('simpleTurbo') is not True or m.get('quantoState') != 'unknown'
            or m.get('underlyingType') != 'SPOT'):
        return out
    report = out.get('comdirectFieldsBackup') or {}
    obs = report.get('observations') or {}
    isin = out.get('isin')
    source = 'https://www.comdirect.de/inf/zertifikate/'+str(isin)
    required = dict(quanto=False, direction=m.get('direction'), currency=m.get('currency'),
                    underlying='XAU/USD', ratio=m.get('ratio'), type='Knock-out Turbo')
    # KO/strike conflicts do not affect the non-quanto gearing formula. Keep
    # those independent barriers blocked, but accept same-product model fields
    # when every formula-relevant observation below is explicitly verified.
    conflicts = set(report.get('conflicts') or [])
    model_conflicts = conflicts & set(required)
    acceptable_state = report.get('state') == 'active' or (
        report.get('state') == 'conflict' and conflicts and not model_conflicts)
    if (not isinstance(isin, str) or not q.valid_isin(isin) or report.get('isin') != isin
            or not acceptable_state or model_conflicts
            or report.get('inactive') or report.get('source') != source):
        return out
    if m.get('underlying') != 'XAU/USD' or not m.get('ratio'):
        return out
    for key, value in required.items():
        item = obs.get(key) or {}
        if (item.get('value') != value or (key == 'quanto' and item.get('value') is not False)
                or item.get('conditionVerified') is not True or item.get('source') != source
                or any(item.get(k) for k in ('conflict', 'revoked', 'ocrCorrection'))):
            return out
        try:
            if not 0 <= (now-q.stamp(item['reviewedAt'])).total_seconds() <= 8*3600:
                return out
        except (KeyError, TypeError, ValueError):
            return out
    condition = (out.get('conditions') or {}).get('quanto') or {}
    if condition.get('value') is not False or any(condition.get(k) for k in ('conflict','revoked')):
        return out
    m.update(simpleNonQuantoTurbo=True, quantoState='non-quanto', comdirectModelFallback=True,
             currencyModelEvidence=dict(source=source, reviewedAt=obs['quanto']['reviewedAt'],
                                        value=False, isin=isin))
    return out


def current_evidence(result, now=None):
    """Validate calculated gearing as a dated value, never a broker quote."""
    now = now or datetime.now(timezone.utc)
    result = reconcile_model(result, now)
    try:
        c = result['leverageCalculation']; i = c['inputs']; m = result['metadata']
        if (not result.get('productVerified') or m.get('status') != 1
                or not m.get('simpleNonQuantoTurbo') or not c.get('available')
                or not c.get('fresh') or i.get('basisEstimated') or i.get('basisDelayed')):
            return None
        times = [q.stamp(i[k]) for k in ('askAt','basisAt','fxDataAt','fxEffectiveAt')]
        if any(not 0 <= (now-t).total_seconds() <= MAX_INPUT_AGE_SECONDS for t in times):
            return None
        if (max(times)-min(times)).total_seconds() > MAX_SKEW_SECONDS:
            return None
        gold, rate, ratio, ask, value = [q.number(v) for v in
            (i['basisPriceUsd'], i['usdEur'], i['ratio'], i['askNative'], c['value'])]
        if min(gold, rate, ratio, ask, value) <= 0 or i['quoteCurrency'] not in ('EUR','CHF'):
            return None
        if ratio != m.get('ratio') or not math.isclose(value,gold*rate*ratio/ask,rel_tol=1e-9):
            return None
        if q.stamp(c['at']) != min(times):
            return None
        return dict(value=value, at=min(times).isoformat(), current=True,
                    kind='calculated-gearing', label='Berechneter Hebel · Zeitnachweis bestätigt')
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def apply(result, now=None):
    supplied_now = now
    now = now or datetime.now(timezone.utc)
    result = reconcile_model(result, now)
    m = result.get('metadata', {})
    if not result.get('productVerified') or m.get('status') != 1:
        return result
    if 'simpleNonQuantoTurbo' not in m:
        return result
    if not m.get('simpleNonQuantoTurbo'):
        # Distinguish a proven Quanto from an absent issuer field. An
        # undated provider reference cannot substitute for model proof.
        if m.get('quantoState') == 'quanto':
            reason = 'Quanto-Produkt: einfaches Nicht-Quanto-Hebelmodell nicht anwendbar'
        elif m.get('simpleTurbo') is False:
            reason = 'SG-Produkttyp nicht als einfaches Turbo-Modell bestätigt'
        else:
            reason = ('SG hat das Quanto-Merkmal nicht eindeutig bestätigt; '
                      'ein automatischer Hebel aus Spot/FX wäre nur eine ungesicherte Annahme')
        return dict(result, leverageCalculation=dict(
            available=False, reason=reason, modelConfirmed=False))
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
        native = out.get('nativeChartEvidence') or {}
        from swissquote_quotes import current_pair
        native_quote = current_pair(out, supplied_now or datetime.now(timezone.utc))
        if (not out.get('chartEvidence') and native.get('currency') == 'CHF'
                and native_quote is None
                and q.number(native.get('bid', 0)) > 0
                and q.number(native.get('ask', 0)) >= q.number(native['bid'])
                and native.get('pointAt')):
            native_quote = dict(bid=native['bid'], ask=native['ask'],
                bidAt=native['pointAt'], askAt=native['pointAt'], currency='CHF',
                source='SG · datierte CHF-Chartbeobachtung',
                priceKind='issuer-chart', isExecutableQuote=False)
        evidence = calculate(out,basis,market_input('fx'),
                             supplied_now or datetime.now(timezone.utc),
                             quote_override=native_quote)
        out['leverageCalculation'] = evidence
        old = out.get('leverageAt')
        out['leverageComparison'] = compare(out, evidence, supplied_now or datetime.now(timezone.utc))
        prefer_analysis = out.get('backupActive') and evidence['fresh']
        if old and out.get('leverage') and not out.get('leverageEstimated') and 0 <= (now-q.stamp(old)).total_seconds() <= 90:
            return out
        if not prefer_analysis and old and out.get('leverage') and q.stamp(old) >= q.stamp(evidence['at']):
            return out
        out['providerLeverage'] = dict(value=out.get('leverage'),at=old,source=out.get('source'))
        out.update(leverage=evidence['value'],leverageAt=evidence['at'],leverageEstimated=True,
                   leverageSource='Bob · CFD-basierter geschätzter Hebel' if basis.get('estimated') else 'Bob · berechneter Hebel',eligible=False,fresh=False,
                   leverageNote=evidence['label']+' · '+evidence['state']+'. '+evidence['note'])
        if m.get('currencyModelEvidence'):
            out['leverageNote'] += ' Währungsumrechnung: nicht währungsgesichert laut nachgewiesenen Produktbedingungen; datierter Wechselkurs berücksichtigt.'
        if evidence['inputs'].get('quoteCurrency') == 'CHF':
            out['leverageNote'] += ' Berechnung in CHF (USD/CHF); keine EUR-Handelsquotierung.'
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
                or (max(times+[at])-min(times+[at])).total_seconds() > 30):
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
                logger = logging.getLogger(__name__)
                if row['warning']:
                    logger.warning('BOB_LEVERAGE_COMPARISON %s', key)
                else:
                    logger.info('BOB_LEVERAGE_COMPARISON %s', key)
        return row
    except (KeyError,ValueError,TypeError,AttributeError):
        return skipped
