"""Research-only Gold-API XAU spot currency parity; never a tradable FX quote."""
import math
from datetime import datetime, timezone

ORIGIN = "https://api.gold-api.com/"
URLS = {c: ORIGIN + "price/XAU/" + c for c in ("USD", "EUR", "CHF")}
MAX_AGE_SECONDS = 60
MAX_SKEW_SECONDS = 5

def _point(payload, currency, now):
    if not isinstance(payload, dict) or payload.get("symbol") != "XAU" or payload.get("currency") != currency:
        raise ValueError("Wrong original symbol/currency")
    value = payload.get("price")
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid spot price")
    original = payload.get("updatedAt")
    if not isinstance(original, str):
        raise ValueError("Missing original clock")
    try:
        at = datetime.fromisoformat(original.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Bad original clock") from exc
    if at.tzinfo is None:
        raise ValueError("Missing source timezone")
    at = at.astimezone(timezone.utc)
    if not 0 <= (now - at).total_seconds() <= MAX_AGE_SECONDS:
        raise ValueError("Source clock stale or future")
    return float(value), at

def derive(quotes, *, now=None):
    """Only a shadow model; the output deliberately lacks a live FX feed schema."""
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None or not isinstance(quotes, dict) or set(quotes) != set(URLS):
        raise ValueError("All three quotes and a timezone-aware clock are required")
    points = {c: _point(quotes[c], c, now) for c in URLS}
    timestamps = [point[1] for point in points.values()]
    skew = (max(timestamps) - min(timestamps)).total_seconds()
    if skew > MAX_SKEW_SECONDS:
        raise ValueError("Original quote timestamps do not align")
    usd, eur, chf = [points[c][0] for c in ("USD", "EUR", "CHF")]
    return {
        "kind": "gold-api-implied-fx-shadow",
        "researchOnly": True,
        "notForExecution": True,
        "notForProductQuotes": True,
        "notForLiveSignals": True,
        "source": "Gold-API.com · XAU currency parity (inferred, not FX)",
        "sourceAt": min(timestamps).isoformat(),
        "observedAt": now.astimezone(timezone.utc).isoformat(),
        "sourceSkewSeconds": skew,
        "usdToEurIndicative": eur / usd,
        "usdToChfIndicative": chf / usd,
        "chfToEurIndicative": eur / chf,
        "eurToChfIndicative": chf / eur,
    }

def fetch_once(*, fetch=None, now=None):
    """Explicit one-shot public read only: three HTTPS GETs; no cron or retry."""
    if fetch is None:
        from product_quotes import issuer_json
        fetch = issuer_json
    quotes = {c: fetch(url, ORIGIN, timeout=4) for c, url in URLS.items()}
    return derive(quotes, now=now)

def compare_to_live_fx(shadow, live, *, now=None):
    """Measure research-only percentage disagreement with another current source."""
    from fx_data import age
    now = datetime.now(timezone.utc) if now is None else now
    if (shadow.get("kind") != "gold-api-implied-fx-shadow"
            or shadow.get("researchOnly") is not True or shadow.get("notForExecution") is not True
            or live.get("source") != "live" or live.get("market_session") != "open"
            or any(live.get("sources", {}).get(c) != "live" for c in ("EUR", "CHF"))
            or age(live, now) > MAX_AGE_SECONDS):
        raise ValueError("Current independent FX source not validated")
    source_at = datetime.fromisoformat(shadow["sourceAt"])
    if source_at.tzinfo is None or not 0 <= (now-source_at).total_seconds() <= MAX_AGE_SECONDS:
        raise ValueError("Research shadow expired")
    for key in ("usdToEurIndicative", "usdToChfIndicative"):
        value = shadow.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid shadow reference")
    return {
        "kind": "gold-implied-fx-difference",
        "researchOnly": True,
        "notForExecution": True,
        "eurDifferencePct": 100 * (shadow["usdToEurIndicative"] / float(live["rates"]["EUR"]) - 1),
        "chfDifferencePct": 100 * (shadow["usdToChfIndicative"] / float(live["rates"]["CHF"]) - 1),
    }
