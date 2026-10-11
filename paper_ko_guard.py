"""Fail-closed knock-out guard for observed EUR paper positions.

Only a currently dated, issuer-verified XAU/USD spot barrier can be
compared with Bob's spot gold feed. This is not an executable stop order,
a prediction of an issuer event or a substitute for an observed bid.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import math

ZURICH = ZoneInfo('Europe/Zurich')


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def terminal(quote, isin):
    """Issuer/official product-terminal evidence, not a crossed-price guess."""
    if not isinstance(quote, dict) or quote.get('isin') != isin:
        return None
    if quote.get('productVerified') is not True:
        return None
    evidence = quote.get('terminalEvidence') or {}
    if isinstance(evidence, dict) and evidence.get('status') == 'knocked_out':
        return 'knockout-confirmed'
    meta = quote.get('metadata') or {}
    if meta.get('status') == 2:
        return 'product-terminated'  # May be expiry, cancellation or knock-out.
    return None


def assess(choice, quote, market, now):
    """Return trusted KO distance and its protective threshold, or a blocker.

    Issuer's dated KO condition must belong to the exact EUR product and to
    today's Swiss calendar date. Undated observations and screenshots are not
    silently promoted into intraday stop evidence. Future contracts cannot
    use the XAU/USD spot quote as their KO reference.
    """
    if not isinstance(choice, dict) or not isinstance(quote, dict):
        return None, 'KO-Produktdaten fehlen'
    isin = choice.get('isin')
    if not isin or quote.get('isin') != isin:
        return None, 'KO-Produktidentität nicht bestätigt'
    if terminal(quote, isin):
        return None, 'Produkt laut Anbieter beendet oder ausgeknockt'
    meta = quote.get('metadata') or {}
    if (choice.get('scope') != 'XAU/USD' or
            meta.get('underlyingType') != 'SPOT' or
            meta.get('underlying') != 'XAU/USD'):
        return None, 'KO-Basiswert passt nicht zum aktuellen Gold-Spotkurs'
    side = choice.get('direction')
    if side not in ('LONG', 'SHORT') or (
            quote.get('direction') or meta.get('direction')) != side:
        return None, 'KO-Produktrichtung nicht sicher bestätigt'
    if quote.get('productVerified') is not True:
        return None, 'KO-Emittentennachweis fehlt'
    if meta.get('status') != 1 or meta.get('tradingHalted') is True:
        return None, 'Produktstatus nicht sicher aktiv'
    cond = (quote.get('conditions') or {}).get('ko') or {}
    value = cond.get('value')
    date = cond.get('dateText')
    if (not positive(value) or cond.get('conditionVerified') is not True
            or cond.get('validityUnconfirmed') is True
            or not isinstance(cond.get('source'), str) or not cond['source']
            or date != datetime.fromtimestamp(now / 1000, ZURICH).strftime('%d.%m.%Y')):
        return None, 'KO-Barriere ohne gültigen heutigen Emittenten-Datenstand'
    price = market.get('price')
    if not positive(price) or (market.get('plan') or {}).get('unit') != 'USD/oz':
        return None, 'Gold-Spot-Referenz nicht bestätigt'
    # A mismatching spot feed is never used for futures.
    sign = 1 if side == 'LONG' else -1
    distance = sign * (price - value) / price
    atr = market.get('atr')
    atr_buffer = 1.5 * atr / price if positive(atr) else 0
    threshold = max(.015, atr_buffer)
    return dict(isin=isin, side=side, barrierUsd=value, spotUsd=price,
                distancePct=round(distance * 100, 4),
                protectiveDistancePct=round(threshold * 100, 4),
                danger=distance <= threshold,
                crossed=distance <= 0,
                observedAt=now, source=cond['source'], termsDate=date), None


def entry_reason(choice, quote, market, now):
    """Require extra room at entry so the guard doesn't trigger immediately."""
    if (choice.get('direction') != market.get('direction') or
            (market.get('plan') or {}).get('direction') != choice.get('direction')):
        return 'KO-Markt- und Produktrichtung stimmen nicht überein', None
    snapshot, reason = assess(choice, quote, market, now)
    if reason:
        return reason, None
    buffer = snapshot['protectiveDistancePct'] / 100
    distance = snapshot['distancePct'] / 100
    if distance <= buffer + .005:
        return 'KO-Abstand bei Einstieg zu gering (Schutzpuffer plus Reserve)', snapshot
    return None, snapshot
