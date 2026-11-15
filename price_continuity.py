"""Display-only source/model continuity. Never modifies broker or release evidence."""
from datetime import datetime, timezone
import threading
import hybrid_product_price as h
import product_estimate

_LOCK = threading.Lock()
_PENDING = {}


def current_pair(row, isin, now):
    try:
        return (row.get('isin') == isin and row.get('currency') in ('EUR', 'CHF')
                and not row.get('delayed') and not row.get('estimated')
                and row.get('priceKind') not in ('calculated', 'calculated-turbo')
                and h.positive(row.get('bid')) and h.positive(row.get('ask'))
                and row['ask'] >= row['bid']
                and all(0 <= (now-h.utc(row[k])).total_seconds() <= 90
                        for k in ('bidAt', 'askAt')))
    except (KeyError, ValueError, TypeError):
        return False


def research_model(result, now):
    """Quote outages do not invalidate separately corroborated current terms.

    Only the display/simulation valuation uses this local copy. Quote evidence,
    issuer availability and all approval flags remain unchanged on the result.
    """
    model = h.model_for(result, now)
    if model:
        return model
    if result.get('quoteFailureCode') != 'SG_SOURCE_UNAVAILABLE':
        return None
    m = result.get('metadata') or {}
    fields = result.get('comdirectFieldsBackup') or {}
    obs = fields.get('observations') or {}
    isin = result.get('isin')
    if (m.get('simpleNonQuantoTurbo') is not True
            or fields.get('isin') != isin or fields.get('state') != 'active'
            or fields.get('inactive') or fields.get('conflicts') or fields.get('unresolvedConflicts')
            or fields.get('source') != 'https://www.comdirect.de/inf/zertifikate/'+str(isin)
            or obs.get('quanto', {}).get('value') is not False
            or obs.get('quanto', {}).get('conditionVerified') is not True
            or obs.get('issuer', {}).get('value') != 'Société Générale'
            or any(obs.get(k, {}).get('value') != m.get(k)
                   for k in ('ratio', 'direction', 'currency', 'underlying'))):
        return None
    try:
        from zoneinfo import ZoneInfo
        today = now.astimezone(ZoneInfo('Europe/Zurich')).strftime('%d.%m.%Y')
        if not 0 <= (now-h.utc(fields['checkedAt'])).total_seconds() <= 300:
            return None
        for key in ('ko', 'strike'):
            term = result['conditions'][key]
            if (term.get('conditionVerified') is not True or term.get('conflict')
                    or term.get('dateText') != today or term.get('value') != m.get(key)):
                return None
    except (KeyError, TypeError, ValueError):
        return None
    candidate = dict(result, sourceFailure=False, quoteFailureCode=None,
                     metadata=dict(m))
    return h.model_for(candidate, now)


def apply(result, now=None, fetch_spot=None, fetch_fx=None):
    now = now or datetime.now(timezone.utc)
    out = dict(result)
    state = dict(state='unavailable', label='Keine aktuelle Berechnungsgrundlage',
                 reason='Produktmodell oder aktuelle Gold-/FX-Daten nicht bestätigt.',
                 eligible=False, degiroExecutable=False)
    out['priceContinuity'] = state
    meta = result.get('metadata') or {}
    if (not result.get('productVerified') or meta.get('status') != 1
            or meta.get('tradingHalted') or result.get('sourceDisabled')):
        return out
    pool = [result, result.get('analysisQuote') or {}, result.get('secondaryQuote') or {}]
    original = max((r for r in pool if current_pair(r, result['isin'], now)
                    and r.get('currency') == meta.get('currency')
                    and not (r is result and result.get('sourceFailure'))),
                   key=lambda r:min(h.utc(r['bidAt']), h.utc(r['askAt'])), default=None)
    if original:
        state.update(state='original', label='Originalkurs aktuell',
                     source=original.get('source'), currency=original['currency'],
                     bid=original['bid'], ask=original['ask'],
                     at=min(h.utc(original['bidAt']), h.utc(original['askAt'])).isoformat(),
                     reason=None)
    model = research_model(result, now)
    if not model:
        return out
    key = product_estimate.identity(model)
    # A returning original can only be compared with a previously frozen model
    # at nearly the same source time; no later market move is called model error.
    if original:
        with _LOCK:
            previous = _PENDING.get(key)
        if previous and abs((h.utc(state['at'])-h.utc(previous['at'])).total_seconds()) <= 15:
            mid = (original['bid']+original['ask'])/2
            state['comparison'] = dict(modelPrice=previous['price'], originalMid=mid,
                differenceEur=mid-previous['price'], modelAt=previous['at'],
                originalAt=state['at'], basis='Modell gegen Original-Mittelkurs',
                affectsApproval=False)
        return out
    c = result.get('calculatedProduct') or {}
    try:
        if (c.get('available') and c.get('currency') == 'EUR'
                and all(0 <= (now-h.utc(c[k])).total_seconds() <= 60
                        for k in ('priceAt','goldAt','fxDataAt','fxEffectiveAt'))
                and h.positive(c.get('askEur')) and h.positive(c.get('bidEur'))):
            state.update(state='calculated', label='Berechneter Kurs aktuell',
                         kind='anchored', price=c['askEur'], bid=c['bidEur'], ask=c['askEur'],
                         leverage=c.get('indicativeLeverage'), currency='EUR',
                         at=c['priceAt'], goldAt=c['goldAt'], fxDataAt=c['fxDataAt'],
                         fxEffectiveAt=c['fxEffectiveAt'], source=c.get('source'), reason=None)
        else:
            if fetch_spot is None:
                from spot_data import current as fetch_spot
            if fetch_fx is None:
                from sg_quotes import market_input
                fetch_fx = lambda: market_input('fx')
            spot = h.adapter_spot(fetch_spot, now)
            fx = h.adapter_fx(fetch_fx, now)
            times = [h.utc(spot['price_as_of']), h.utc(fx['data_updated_at']),
                     h.utc(fx['effective_at']['EUR'])]
            if (max(times)-min(times)).total_seconds() > 15:
                raise ValueError('Gold-/FX-Quellenzeiten liegen mehr als 15 Sekunden auseinander.')
            gold, rate = spot['spot_usd_oz'], fx['rates']['EUR']
            direction = 1 if model['direction'] == 'LONG' else -1
            if direction*(gold-model['ko']) <= 0 or direction*(gold-model['strike']) <= 0:
                raise ValueError('KO- oder Basispreisschwelle erreicht.')
            price = direction*(gold-model['strike'])*model['ratio']*rate
            if not h.positive(price):
                raise ValueError('Kein positiver Modellwert.')
            state.update(state='calculated', label='Berechneter Kurs aktuell',
                         kind='intrinsic', price=price, leverage=gold*model['ratio']*rate/price,
                         currency='EUR', at=min(times).isoformat(), goldAt=times[0].isoformat(),
                         fxDataAt=times[1].isoformat(), fxEffectiveAt=times[2].isoformat(),
                         source='Bob · bestätigte Produktbedingungen + Gold/FX',
                         model=model, goldUsd=gold, usdEur=rate, reason=None,
                         note='Theoretischer innerer Wert ohne bestätigten Spread oder Aufgeld; '
                              'kein Geld-/Briefkurs und kein DEGIRO-Ausführungskurs.')
        with _LOCK:
            _PENDING[key] = dict(price=state['price'], at=state['at'])
            if len(_PENDING) > 256:
                _PENDING.pop(next(iter(_PENDING)))
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        state['reason'] = str(exc) if isinstance(exc, ValueError) else 'Berechnungsdaten nicht verfügbar.'
    return out
