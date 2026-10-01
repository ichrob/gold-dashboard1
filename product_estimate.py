"""Anchored, non-executable price estimates for verified simple SG spot turbos.

Bid/ask premiums are held constant in EUR; unit delta is an approximation.
No options/quanto model, no guessed ratios, and no generated execution quotes.
"""
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from future_estimate import stamp, number

_anchors = {}
_lock = threading.Lock()
MAX_ANCHOR_AGE = 1800
MAX_INPUT_AGE = 60
MAX_ANCHOR_SKEW = 5


def identity(model):
    return tuple(model[k] for k in ('isin','underlying','direction','ratio','strike','ko','classification'))


def validate_model(model):
    if (model['verifiedSimpleTurbo'] is not True or model['underlying'] != 'XAU/USD'
            or model['classification'] not in (43,45,47)
            or model['direction'] not in ('LONG','SHORT')):
        raise ValueError('Kein bestätigtes einfaches Gold-Turbo-Modell')
    for key in ('ratio','strike','ko'):
        number(model[key])
    return identity(model)


def remember(result, model, now):
    key = validate_model(model)
    if result.get('eligible') is not True or result.get('fresh') is not True:
        return
    times = [stamp(result[k]) for k in ('bidAt','askAt','spotAt','fxAt','fxDataAt','fxEffectiveAt')]
    if (max(times)-min(times)).total_seconds() > MAX_ANCHOR_SKEW:
        return
    if any(not 0 <= (now-t).total_seconds() <= MAX_INPUT_AGE for t in times):
        return
    anchor = dict(model, bid=number(result['bid']), ask=number(result['ask']),
                  underlyingPriceUsd=number(result['leverageInputs']['spotUsd']),
                  usdEur=number(result['leverageInputs']['usdEur']),
                  referenceAt=min(times).isoformat(),
                  referenceSkewSeconds=(max(times)-min(times)).total_seconds())
    with _lock:
        previous = _anchors.get(key)
        if previous and stamp(previous['referenceAt']) >= min(times):
            return
        if len(_anchors) >= 256:
            _anchors.pop(next(iter(_anchors)))
        _anchors[key] = anchor


def calculate(model, anchor, spot, fx, now=None):
    now = now or datetime.now(timezone.utc)
    out = dict(available=False, label='Berechneter Produktkurs', kind='calculated-turbo',
               currency='EUR', eligible=False, isDegiroQuote=False,
               formula='P₀ + Richtung × Bezugsverhältnis × [(Gold − Basispreis) × FX − (Gold₀ − Basispreis) × FX₀]',
               note='Näherung mit Delta ±1 und unverändertem Aufgeld sowie Spread in EUR. '
                    'Emittentenpreis und DEGIRO-Ausführung können abweichen.')
    try:
        key = validate_model(model)
        if not anchor or identity(anchor) != key:
            raise ValueError('Zeitlich passender bestätigter Produkt-Referenzkurs fehlt')
        ref_at = stamp(anchor['referenceAt'])
        ref_age = (now-ref_at).total_seconds()
        if not 0 <= ref_age <= MAX_ANCHOR_AGE:
            raise ValueError('Produkt-Referenzkurs älter als 30 Minuten')
        if (spot['stale'] is not False or spot['data_state']['status'] != 'fresh'
                or spot['xau']['currency'] != 'USD' or spot['xau']['unit'] != 'troy_oz'
                or fx['result'] != 'success' or fx['base'] != 'USD' or fx['source'] != 'live'
                or fx['sources']['EUR'] != 'live' or fx['market_session'] != 'open'):
            raise ValueError('Aktuelle Gold- und FX-Daten fehlen')
        times = [stamp(spot['price_as_of']), stamp(fx['data_updated_at']), stamp(fx['effective_at']['EUR'])]
        if any(not 0 <= (now-t).total_seconds() <= MAX_INPUT_AGE for t in times):
            raise ValueError('Gold- oder Wechselkurs veraltet')
        if (max(times)-min(times)).total_seconds() > 15:
            raise ValueError('Gold- und Wechselkurs zeitlich zu weit auseinander')
        local = now.astimezone(ZoneInfo('Europe/Berlin'))
        if local.weekday() >= 5 or not 8 <= local.hour < 22 or now > stamp(model['tradingEndAt']):
            raise ValueError('SG-Handelszeit beendet')
        gold, rate = number(spot['spot_usd_oz']), number(fx['rates']['EUR'])
        old_gold, old_rate = number(anchor['underlyingPriceUsd']), number(anchor['usdEur'])
        direction = 1 if model['direction'] == 'LONG' else -1
        ko, strike, ratio = number(model['ko']), number(model['strike']), number(model['ratio'])
        if direction*(gold-ko) <= 0 or direction*(gold-strike) <= 0:
            raise ValueError('Goldpreis an oder jenseits der KO-/Finanzierungsschwelle')
        change = direction*ratio*((gold-strike)*rate-(old_gold-strike)*old_rate)
        bid, ask = number(anchor['bid'])+change, number(anchor['ask'])+change
        number(bid);number(ask)
        if ask < bid:
            raise ValueError('Ungültiger berechneter Spread')
        out.update(available=True, bidEur=round(bid,4), askEur=round(ask,4), priceEur=round(ask,4),
                   referenceBidEur=anchor['bid'],referenceAskEur=anchor['ask'],
                   referenceAt=ref_at.isoformat(),referenceAgeSeconds=round(ref_age,1),
                   referenceSkewSeconds=anchor['referenceSkewSeconds'],
                   priceAt=min(times).isoformat(),calculatedAt=now.isoformat(),
                   goldAt=times[0].isoformat(),fxDataAt=times[1].isoformat(),fxEffectiveAt=times[2].isoformat(),
                   goldUsd=gold,usdEur=rate,ratio=ratio,direction=model['direction'],strikeUsd=strike,
                   referenceGoldUsd=old_gold,referenceUsdEur=old_rate,
                   indicativeLeverage=gold*rate*ratio/ask,
                   indicativeKoDistancePct=abs(gold-ko)/gold*100)
    except (KeyError,ValueError,TypeError,OverflowError) as exc:
        out['reason'] = str(exc) if isinstance(exc,ValueError) else 'Pflichtdaten für das Produktmodell fehlen'
    return out


def current(model, spot, fx, now=None):
    with _lock:
        anchor = _anchors.get(identity(model))
    return calculate(model, anchor, spot, fx, now)
