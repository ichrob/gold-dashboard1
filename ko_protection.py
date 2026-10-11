"""Shared, quote-independent KO distance policy for Bob's Spot-Gold monitoring.

The output is a risk assessment, never proof of a fill or a KO event.
Never compare an XAU/USD spot observation with an unverified Future barrier.
"""
import math


def positive(value):
    return type(value) in (float, int) and math.isfinite(value) and value > 0


def assess(gold, barrier, direction, atr=None, underlying='XAU/USD'):
    """Classify proximity to a verified barrier, conservatively for both sides.

    Thresholds match Bob's existing minimum entry buffers: 1% and 1.5 ATR.
    The advance warning is 2% or 2 ATR. Missing volatility is not guessed.
    """
    unknown = dict(level='unknown', distanceUsd=None, distancePct=None,
                   atrMultiple=None, protectiveStopGold=None)
    if underlying != 'XAU/USD' or direction not in ('LONG', 'SHORT'):
        return {**unknown, 'reason': 'Basiswert oder Richtung nicht vergleichbar'}
    if not positive(gold) or not positive(barrier):
        return {**unknown, 'reason': 'Aktueller Basiswert oder belegte KO-Barriere fehlt'}
    sign = 1 if direction == 'LONG' else -1
    distance = sign * (gold - barrier)
    pct = 100 * distance / gold
    multiple = distance / atr if positive(atr) else None
    critical_buffer = max(gold * .015, 1.5 * atr if positive(atr) else 0)
    warning_buffer = max(gold * .02, 2 * atr if positive(atr) else 0)
    level = ('crossed' if distance <= 0 else
             'critical' if distance <= critical_buffer else
             'warning' if distance <= warning_buffer else 'safe')
    stop = barrier + sign * critical_buffer
    return dict(level=level, distanceUsd=round(distance, 6),
                distancePct=round(pct, 4),
                atrMultiple=round(multiple, 3) if multiple is not None else None,
                protectiveStopGold=round(stop, 6),
                reason=('KO-Barriere an oder jenseits des aktuellen Goldpreises' if level == 'crossed'
                        else 'Kritischer KO-Abstand' if level == 'critical'
                        else 'KO-Abstand nähert sich der Schutzgrenze' if level == 'warning'
                        else 'KO-Abstand oberhalb der Warngrenzen'))
