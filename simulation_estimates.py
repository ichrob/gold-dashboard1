"""Causal, bounded input models for paper comparisons only.

Carry-forward is an assumption, not an observed price or an OHLC range.
No provider fetch, live-bundle mutation, broker quote or trading permission.
"""
import copy
from datetime import datetime
from zoneinfo import ZoneInfo
from paper_shadow_studies import number, positive

VERSION = 'paper-gap-carry-v1'
MAX_PRICE_AGE = 180000
MAX_CANDLE_GAP = 2
MAX_WORKER_GAP = 300000
STEPS = {'5m': 300000, '15m': 900000}


def same_session(a, b):
    if not number(a) or not number(b) or a > b:
        return False
    left, right = (datetime.fromtimestamp(t/1000, ZoneInfo('Europe/Zurich')) for t in (a, b))
    return left.date() == right.date() and left.weekday() < 5 and 8 <= left.hour < 22 and 8 <= right.hour < 22


def candle(bundle, timeframe, target, now):
    step = STEPS[timeframe]
    if not number(target) or target % step or not 0 <= now-(target+step) <= step:
        return None
    bars = (((bundle or {}).get('history') or {}).get('bars_by_tf') or {}).get(timeframe) or []
    # An explicitly provider-open bar is not a missing closed candle.
    if any(isinstance(b, dict) and b.get('openTime') == target and
           (b.get('isOpen') is True or b.get('providerIsOpen') is True) for b in bars):
        return None
    anchors = [b for b in bars if isinstance(b, dict) and number(b.get('openTime'))
        and b.get('instrument') == 'XAU/USD' and b.get('isOpen') is False
        and b.get('providerIsOpen') is not True and b.get('estimated') is not True
        and positive(b.get('close')) and 0 < target-b['openTime'] <= MAX_CANDLE_GAP*step
        and (target-b['openTime']) % step == 0 and same_session(b['openTime']+step, target+step)]
    if not anchors:
        return None
    anchor = max(anchors, key=lambda b: b['openTime'])
    price = anchor['close']
    return dict(openTime=target, open=price, high=price, low=price, close=price,
        instrument='XAU/USD', isOpen=False, estimated=True, dataMode='estimated',
        method='previous-original-close-carry', modelVersion=VERSION,
        anchorAt=anchor['openTime']+step, anchorPrice=price, anchorSource=anchor.get('source'), calculatedAt=now,
        effectiveAt=target+step, observedRangeKnown=False, simulationOnly=True)


def input_quality(original, bundle, market, now, timeframe, previous=None):
    """Never turn verified on for a model; callers use simulationUsable."""
    q = copy.deepcopy(original)
    q.update(simulationUsable=bool(q.get('verified')), estimated=False,
             dataMode='original' if q.get('verified') else 'unavailable', modelVersion=VERSION)
    if q['verified']:
        return q
    from paper_simulation import stamp
    spots = (bundle or {}).get('spots') or {}
    source_at = stamp(spots.get('spot_price_as_of'))
    source_price = spots.get('xaus')
    original_spot = (spots.get('is_genuine_xauusd_spot') is True and spots.get('xaus_is_spot') is True
        and positive(source_price) and number(source_at) and 0 <= now-source_at <= 60000
        and positive(market.get('price')) and abs(market['price']-source_price) <= .001
        and number(market.get('dataAt')) and abs(market['dataAt']-source_at) <= 2000
        and market.get('ready') is True and market.get('priceFresh') is True)
    modeled_candle = candle(bundle, timeframe, q.get('analysisBarAt'), now) if not q.get('closedSignalBarMatched') else None
    if original_spot and modeled_candle:
        q.update(simulationUsable=True, estimated=True, dataMode='estimated-candle',
                 reason='simulation-missing-candle-carried', estimatedCandle=modeled_candle,
                 originalSourceAt=source_at, calculatedAt=now)
        return q
    # A last observed input can carry an existing scenario briefly. Do not
    # recursively anchor another estimate or open new cases from this path.
    previous = previous or {}
    at = previous.get('sourceAt')
    if (previous.get('verified') is True and positive(previous.get('price'))
            and number(at) and 0 < now-at <= MAX_PRICE_AGE and same_session(at, now)
            and (source_at is None or (number(source_at) and now-source_at > 60000))):
        q.update(simulationUsable=True, verified=False, estimated=True, dataMode='estimated-price',
                 sourceAt=now, originalSourceAt=at, price=previous['price'],
                 analysisBarAt=previous.get('analysisBarAt'), calculatedAt=now,
                 reason='simulation-last-original-price-carried', method='last-original-price-carry',
                 newEntryAllowed=False)
    return q
