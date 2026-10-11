"""Distinct 800 EUR trend-following PAPER exit policy; no order execution.

Compared with Bob's existing partial-target policy this holds the whole virtual
position through confirmed trend continuation, records extension milestones,
and trails stops only toward profit.  No synthetic fills are generated.
"""
import math

VERSION='paper-long-trend-v1'
MAX_EXTENSION_EVENTS=8


def positive(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def step(case,market,price,trade,event,realize):
    """Called only after fresh Gold quote, gap/initial stop and max-time checks.

    event(kind, **kwargs) appends a non-execution lifecycle audit event;
    realize(kind,weight) books a model exit via shared current product-quote
    handling (or explicitly defers when the product quote is unavailable).
    """
    direction=trade['dir']
    long=direction=='LONG'
    risk=case['plan'].get('entry',0)-case['plan'].get('stop',0) if long else (
        case['plan'].get('stop',0)-case['plan'].get('entry',0))
    if not positive(risk):
        # No trusted initial risk: never invent a new protective stop.
        event('trend-risk-unavailable',reason='Einstiegsrisiko unbekannt')
        return
    old_water=case.get('trendHighWater') if long else case.get('trendLowWater')
    if not positive(old_water):
        old_water=trade['entry']
    water=max(old_water,price) if long else min(old_water,price)
    case['trendHighWater' if long else 'trendLowWater']=water

    favorable=(water-trade['entry']) if long else (trade['entry']-water)
    if favorable>=risk:
        atr=market.get('atr')
        trail_distance=max(.75*risk,1.5*atr if positive(atr) else 1.25*risk)
        candidate=water-trail_distance if long else water+trail_distance
        previous=trade['stop']
        # Never relax a stop, even following a reversal or missing ATR.
        if long and candidate>previous and candidate<price:
            trade['stop']=candidate
            event('trend-stop-raised',old=previous,new=candidate,gold=price,
                  reason='Folgetrend: Stop nachgezogen, nicht gelockert')
        elif not long and candidate<previous and candidate>price:
            trade['stop']=candidate
            event('trend-stop-lowered',old=previous,new=candidate,gold=price,
                  reason='Folgetrend: Short-Stop nachgezogen, nicht gelockert')

    target=trade.get('target')
    if positive(target):
        extensions=case.get('trendExtensions',0)
        if ((long and price>=target) or (not long and price<=target)) and extensions<MAX_EXTENSION_EVENTS:
            old_target=target
            trade['target']=target+(2*risk if long else -2*risk)
            case['trendExtensions']=extensions+1
            event('trend-target-continued',old=old_target,new=trade['target'],
                  gold=price,reason='Zielmarke überschritten · Position gehalten, kein fiktiver Verkauf')

    trend=market.get('trendContext') or {}
    trend_intact=(market.get('ready') is True and trend.get('available') is True
                  and trend.get('intact') is True and trend.get('direction')==direction)
    opposite=(market.get('ready') is True and
              market.get('direction') in ('LONG','SHORT') and
              market['direction']!=direction and not trend_intact)
    bar=market.get('analysisBarAt')
    if opposite and positive(bar):
        if bar!=case.get('trendReversalLastBar'):
            previous_bar=case.get('trendReversalLastBar')
            case['trendReversalBars']=(case.get('trendReversalBars',0)+1 if (
                positive(previous_bar) and bar>previous_bar) else 1)
            case['trendReversalLastBar']=bar
            event('trend-reversal-check',gold=price,
                  confirmations=case['trendReversalBars'],
                  reason='Bestätigtes Gegenrichtungssignal; zweite unabhängige Kerze benötigt')
            if case['trendReversalBars']>=2:
                realize('trend-confirmed-reversal',case['remaining'])
                return
    else:
        case['trendReversalBars']=0
        case['trendReversalLastBar']=None
