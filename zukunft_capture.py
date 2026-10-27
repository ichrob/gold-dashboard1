"""Bounded, observed-only research samples for Bobs Zukunft (never broker orders).

Reads the EXISTING four-paper experiment's quotes and market decision and
records one timestamped snapshot per instrument per five-minute bucket.
Missing or unverified KO/quote information remains visible as a blocker.
"""
import hashlib
import json
import math
from datetime import datetime, timezone

import paper_ko_guard
import zukunft_research
from paper_simulation import fresh_quote, stamp

SCHEMA = "zukunft-research-capture-v1"
MAX_OBSERVATIONS = 1500


def _positive(x):
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_zukunft_observations (
       id TEXT PRIMARY KEY, isin TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
       payload JSONB NOT NULL)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS bob_zukunft_observation_times
                    ON bob_zukunft_observations (isin,observed_at DESC)""")


def record(conn, market, selection, quotes, now):
    if (not isinstance(market, dict) or market.get("ready") is not True
            or market.get("priceFresh") is not True
            or not _positive(market.get("price"))
            or not _positive(market.get("analysisBarAt"))
            or market["analysisBarAt"] > now
            or (market.get("plan") or {}).get("unit") != "USD/oz"
            or market.get("direction") not in ("LONG", "SHORT")):
        return 0
    score = market.get("score")
    if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
        return 0
    chosen = selection.get("choices") if isinstance(selection, dict) else None
    if not isinstance(chosen, list):
        return 0
    trend = market.get("trendContext") or {}
    trend_direction = trend.get("direction") if trend.get("available") else "NEUTRAL"
    if trend_direction not in ("LONG", "SHORT"):
        trend_direction = "NEUTRAL"
    observed = 0
    for choice in chosen[:3]:
        if (not isinstance(choice, dict) or choice.get("indicative") is True
                or choice.get("estimated") is True or choice.get("scope") != "XAU/USD"
                or choice.get("direction") != market["direction"]
                or not isinstance(choice.get("isin"), str) or len(choice["isin"]) != 12):
            continue
        isin = choice["isin"]
        raw = quotes.get(isin) if isinstance(quotes, dict) else None
        valid = fresh_quote(raw, now, isin)
        if not valid:
            continue
        guard, guard_error = paper_ko_guard.assess(choice, raw, market, now)
        verified = (choice.get("approval") == "Bob-Pflichtprüfung bestanden"
                    and choice.get("koGuardRequired") is True
                    and guard_error is None and isinstance(guard, dict)
                    and _positive(guard.get("distancePct")))
        bid_at = stamp(valid.get("bidAt") or valid.get("quoteAt"))
        ask_at = stamp(valid.get("askAt") or valid.get("quoteAt"))
        if not (_positive(bid_at) and _positive(ask_at)):
            continue
        at_iso = datetime.fromtimestamp(now/1000, timezone.utc).isoformat()
        source_iso = datetime.fromtimestamp(min(bid_at,ask_at)/1000, timezone.utc).isoformat()
        item = dict(at=at_iso, source_at=source_iso, side=choice["direction"], bid_eur=valid["bid"],
                    ask_eur=valid["ask"], underlying_usd=market["price"],
                    score=score, trend=trend_direction, approved=bool(verified),
                    market_open=True, bar_closed=True,
                    quote_source=valid["source"],
                    ko_distance_fraction=(guard["distancePct"]/100 if verified else None),
                    ko_status=("verified" if verified else str(guard_error or "not-approved")),
                    analysis_bar_at=market["analysisBarAt"], scope="XAU/USD",
                    source_type="observed_product_bid_ask")
        bucket = int(now//300000)
        key = hashlib.sha256((isin+":"+str(bucket)).encode()).hexdigest()
        conn.execute("""INSERT INTO bob_zukunft_observations(id,isin,observed_at,payload)
             VALUES(%s,%s,to_timestamp(%s),%s::jsonb)
             ON CONFLICT(id) DO UPDATE SET observed_at=EXCLUDED.observed_at,
                 payload=EXCLUDED.payload""",
                 (key,isin,now/1000,json.dumps(item,allow_nan=False)))
        observed += 1
    return observed


def report(conn, request=None):
    """Authenticated audit/read endpoint. No prices, results or success fabricated."""
    request = request if isinstance(request, dict) else {}
    chosen = request.get("isin")
    if chosen is not None and (not isinstance(chosen, str) or len(chosen) != 12):
        raise ValueError("ISIN invalid")
    summary = conn.execute("""SELECT isin,COUNT(*),MAX(observed_at),
                      COUNT(*) FILTER (WHERE payload->>'ko_status'='verified')
                      FROM bob_zukunft_observations
                      GROUP BY isin ORDER BY MAX(observed_at) DESC LIMIT 10""").fetchall()
    instruments = [dict(isin=r[0], observations=r[1],
                        lastObservedAt=r[2].isoformat(), verifiedKoSamples=r[3])
                   for r in summary]
    if not chosen and instruments:
        chosen = instruments[0]["isin"]
    result = dict(ok=True, mode="zukunft-observed-research", realOrders=False,
                  brokerConnected=False, status="no_observed_data" if not chosen else "insufficient",
                  instruments=instruments, chosenIsin=chosen,
                  note="Nur belegte Quotes, hypothetische Orders, modellierte statt nachgewiesene Nettokosten; keine Strategiefreigabe.")
    if not chosen:
        return result
    rows = conn.execute("""SELECT payload FROM (
         SELECT payload,observed_at FROM bob_zukunft_observations
         WHERE isin=%s ORDER BY observed_at DESC LIMIT %s
         ) AS recent ORDER BY observed_at ASC""",(chosen,MAX_OBSERVATIONS)).fetchall()
    observations = [r[0] for r in rows]
    result["samples"] = len(observations)
    result["verifiedSamples"] = sum(q.get("ko_status") == "verified" for q in observations)
    result["incompleteSamples"] = len(observations)-result["verifiedSamples"]
    if len(observations) < 245:
        result["reason"] = "Zu wenige chronologische Beobachtungen für ersten Train-/Testlauf"
        return result
    if result["incompleteSamples"]:
        result["status"] = "blocked"
        result["reason"] = "KO-Identität/Zeitbezug für einen Teil der Quotes nicht bestätigt"
        return result
    costs = dict(fee_eur_per_side=1.0, slippage_bps=20.0,
                 financing_eur_per_day_per_unit=0.0)
    # All observed rows must agree on the EXACT product direction.
    sides = {item.get("side") for item in observations}
    if len(sides) != 1 or next(iter(sides)) not in ("LONG", "SHORT"):
        result["status"] = "blocked"
        result["reason"] = "Produkt hat keinen einheitlich nachgewiesenen Long-/Short-Typ"
        return result
    payload = dict(schema="bob-zukunft-observed-v1", synthetic=False, realOrders=False,
                   isin=chosen, side=next(iter(sides)), costs=costs,
                   observations=observations)
    try:
        comparison = zukunft_research.compare(payload)
    except (ValueError, TypeError) as exc:
        result["status"] = "blocked"
        result["reason"] = str(exc)[:240]
        return result
    result["status"] = "research_only"
    result["costAssumptions"] = costs
    result["totalFolds"] = len(comparison["folds"])
    result["strategies"] = comparison["totals"]
    result["reason"] = "Modellierte, unabhängige Testfenster. Keine tatsächlichen Orderfills."
    return result
