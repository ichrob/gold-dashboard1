"""Display-only selection of verified historical candles during market pauses.

This module never changes source candles, signal evaluation or trade admission.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import math

_ZURICH = ZoneInfo("Europe/Zurich")


def historical_chart(bars, *, closed_session=False, limit=1000):
    """Return display copies of closed, source-dated bars.

    Keep the entire available Friday/session history during a closure; do not
    generate bars for Saturday or Sunday. Session filtering must happen at the
    verified source boundary, not by weekday (Sunday evening can trade).
    """
    if not isinstance(bars, list) or not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("Invalid chart arguments")
    selected = []
    previous = -1
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        ts = bar.get("openTime")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts <= previous:
            continue
        previous = ts
        if bar.get("estimated") or bar.get("synthetic") or bar.get("isOpen") or bar.get("providerIsOpen"):
            continue
        values = [bar.get(k) for k in ("open", "high", "low", "close")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
            continue
        o, h, low, close = values
        if low > min(o, close) or h < max(o, close):
            continue
        selected.append(dict(bar))
    result = selected[-limit:]
    last = result[-1] if result else None
    return {
        "bars": result,
        "historical": bool(closed_session),
        "lastConfirmedAt": last["openTime"] if last else None,
        "lastConfirmedClose": last["close"] if last else None,
        "status": "market-closed-last-confirmed" if closed_session and last else
                  "no-confirmed-candles" if not last else "confirmed-history",
    }


def candle_tap_details(bar):
    """Exact source candle open time and close, for mobile tap/tooltip display."""
    ts = bar["openTime"]
    close = bar["close"]
    if (isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts)
            or isinstance(close, bool) or not isinstance(close, (int, float))
            or not math.isfinite(close) or close <= 0):
        raise ValueError("Invalid candle")
    return {
        "openTime": ts,
        "timeZurich": datetime.fromtimestamp(ts / 1000, timezone.utc).astimezone(_ZURICH).isoformat(),
        "close": close,
        "source": bar.get("source"),
        "instrument": bar.get("instrument"),
    }
