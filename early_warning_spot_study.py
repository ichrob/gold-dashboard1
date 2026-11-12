"""Forward-only early-warning versus confirmed-main spot paper comparison.

Research only. Uses original XAU/USD observations passed by the existing paper
worker; no independent fetch, issuer quote, trading approval, or orders.
"""
import copy
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import paper_shadow_studies as shared

VERSION = "early-warning-spot-v1"
HORIZON_MS = 90 * 60000
CONFIRM_MS = 30 * 60000
GAP_MS = 90000
COST_PCT = 0.16  # Illustrative round trip on spot; NOT product or broker costs.
ZURICH = ZoneInfo("Europe/Zurich")


def init(conn):
    # Avoid redundant DDL/locks during rolling deploys on an existing DB.
    exists = conn.execute("SELECT to_regclass('bob_early_warning_spot_cases')").fetchone()
    if not exists or exists[0] is None:
        conn.execute("""CREATE TABLE IF NOT EXISTS bob_early_warning_spot_cases (
            id TEXT PRIMARY KEY, open BOOLEAN NOT NULL, payload JSONB NOT NULL)""")
    # No per-tick journal and no large indexes: one row per original warning.


def original(bundle, market, now):
    """Correlate the original spot with a genuinely CLOSED five-minute bar."""
    candles = (((bundle or {}).get("history") or {}).get("bars_by_tf") or {}).get("5m") or []
    candidates = [b for b in candles if isinstance(b, dict)
                  and b.get("instrument") == "XAU/USD"
                  and shared.number(b.get("openTime"))
                  and b.get("isOpen") is False
                  and b.get("providerIsOpen") is not True
                  and b.get("estimated") is not True
                  and b["openTime"] + 300000 <= now]
    if not candidates:
        return dict(verified=False, reasonCode="original-closed-5m-missing")
    bar = max(candidates, key=lambda b: b["openTime"])
    quality = shared.original_input(bundle, {**market, "analysisBarAt":bar["openTime"]}, now, "5m")
    quality["fiveMinuteCloseAt"] = bar["openTime"] + 300000
    return quality


def session_deadline(source_at):
    local = datetime.fromtimestamp(source_at / 1000, ZURICH)
    return min(source_at + HORIZON_MS, int(local.replace(hour=21, minute=58, second=0, microsecond=0).timestamp()*1000))


def new_case(market, quality):
    warning = market.get("earlyWarning") or {}
    direction = warning["direction"]
    source = quality["sourceAt"]
    price = quality["price"]
    atr = market.get("atr")
    if not shared.positive(atr):
        atr = (market.get("analysisSnapshot") or {}).get("at")
    sign = 1 if direction == "LONG" else -1
    deadline = session_deadline(source)
    return dict(id=f"{VERSION}:{int(warning['signalBarAt'])}:{direction}",
                version=VERSION, direction=direction, warningBarAt=warning["signalBarAt"],
                ruleVersion=market.get("ruleVersion"), sourceAt=source,
                firstObservedAt=source, checkedAt=source, deadlineAt=deadline,
                confirmedBeforeAt=min(source+CONFIRM_MS, deadline),
                frozenAtr=atr, realOrders=False, productReturnVerified=False,
                estimated=False, status="open",
                arms={"early":dict(status="open", entryAt=source, entryPrice=price,
                                   lastSourceAt=source, stop=price-sign*atr,
                                   target=price+sign*1.5*atr, peakPct=0., troughPct=0.),
                      "confirmed":dict(status="waiting", reason="main-signal-not-confirmed")})


def warning_eligible(market, quality, now):
    w = market.get("earlyWarning") or {}
    atr = market.get("atr")
    if not shared.positive(atr):
        atr = (market.get("analysisSnapshot") or {}).get("at")
    return bool(quality.get("verified") and w.get("version") == "early-warning-v2"
                and w.get("state") == "active" and w.get("available") is True
                and w.get("comparisonOnly") is True and w.get("affectsApproval") is False
                and w.get("extensionRisk") is not True and w.get("direction") in ("LONG", "SHORT")
                and shared.number(w.get("signalBarAt"))
                and w["signalBarAt"] == quality.get("fiveMinuteCloseAt")
                and shared.number(w.get("expiresAt")) and now < w["expiresAt"]
                and shared.positive(atr) and 0.0001 < atr/quality["price"] < 0.1
                and 0 <= now-quality["sourceAt"] <= 60000
                and session_deadline(quality["sourceAt"]) - quality["sourceAt"] >= 10*60000)


def close_arm(arm, source, price, sign, reason):
    gross = 100 * sign * (price/arm["entryPrice"] - 1)
    arm.update(status="closed", exitAt=source, exitPrice=price, exitReason=reason,
               modelSpotReturnPct=round(gross-COST_PCT, 6), costAssumptionPct=COST_PCT)


def progress(state, market, quality, now):
    """Advance ONLY on later genuine observations, never on an inferred fill."""
    s = copy.deepcopy(state)
    if s["status"] != "open":
        return s
    early = s["arms"]["early"]
    confirmed = s["arms"]["confirmed"]
    observed = quality.get("verified") is True and shared.number(quality.get("sourceAt"))
    source = quality.get("sourceAt") if observed else None
    if observed and source < s["sourceAt"]:
        observed = False
    # Missing original samples cannot be replaced by later interpolated quotes.
    if not observed:
        if now-s.get("lastCheckedSourceAt", s["sourceAt"]) > GAP_MS:
            for arm in (early, confirmed):
                if arm["status"] in ("open", "waiting"):
                    arm.update(status="inconclusive", reason="original-input-unverified")
            s["status"] = "inconclusive"
        s["checkedAt"] = now
        return s
    if source > s.get("lastCheckedSourceAt", s["sourceAt"]) and source - s.get("lastCheckedSourceAt", s["sourceAt"]) > GAP_MS:
        for arm in (early, confirmed):
            if arm["status"] in ("open", "waiting"):
                arm.update(status="inconclusive", reason="original-spot-gap-over-90s")
        s.update(status="inconclusive", checkedAt=now)
        return s
    if source <= s.get("lastCheckedSourceAt", s["sourceAt"]):
        s["checkedAt"] = now
        return s
    sign = 1 if s["direction"] == "LONG" else -1
    price = quality["price"]
    # Main confirmation must occur *after* the warning; never look ahead.
    if confirmed["status"] == "waiting":
        if (source < s["confirmedBeforeAt"] and source < s["deadlineAt"]
                and market.get("direction") == s["direction"]
                and market.get("ready") is True and market.get("priceFresh") is True):
            atr = s["frozenAtr"]
            confirmed.update(status="open", entryAt=source, entryPrice=price,
                             lastSourceAt=source, stop=price-sign*atr,
                             target=price+sign*1.5*atr, peakPct=0., troughPct=0.,
                             reason="later-confirmed-main")
            s["mainConfirmedAt"] = source
        elif source >= s["confirmedBeforeAt"]:
            confirmed.update(status="no-entry", reason="no-main-confirmation-in-window")
    for arm in (early, confirmed):
        if arm["status"] != "open" or source <= arm["entryAt"]:
            continue
        if source-arm["lastSourceAt"] > GAP_MS:
            arm.update(status="inconclusive", reason="original-spot-gap-over-90s")
            continue
        arm["lastSourceAt"] = source
        pct = 100*sign*(price/arm["entryPrice"]-1)
        arm["peakPct"] = max(arm["peakPct"], pct)
        arm["troughPct"] = min(arm["troughPct"], pct)
        reason = ("observed-stop" if sign*(price-arm["stop"]) <= 0 else
                  "observed-target" if sign*(price-arm["target"]) >= 0 else
                  "opposite-main" if market.get("direction") in ("LONG", "SHORT") and market["direction"] != s["direction"] else
                  "observed-session-or-horizon-end" if source >= s["deadlineAt"] else None)
        if reason:
            close_arm(arm, source, price, sign, reason)
    if source >= s["deadlineAt"] and confirmed["status"] == "waiting":
        confirmed.update(status="no-entry", reason="no-main-confirmation-in-window")
    s.update(lastCheckedSourceAt=source, checkedAt=now)
    if all(a["status"] in ("closed", "no-entry", "inconclusive") for a in (early, confirmed)):
        s["status"] = ("complete" if early["status"] == "closed" and
                       confirmed["status"] in ("closed", "no-entry") else "inconclusive")
        if early["status"] == "closed" and confirmed["status"] == "closed":
            s["pairedSpotDifferencePct"] = round(early["modelSpotReturnPct"]-confirmed["modelSpotReturnPct"], 6)
    return s


def tick(conn, bundle, market, now):
    # One query for at most two open cases, no per-cycle event inserts.
    rows = conn.execute("SELECT id,payload FROM bob_early_warning_spot_cases WHERE open=TRUE ORDER BY id LIMIT 2 FOR UPDATE").fetchall()
    q = original(bundle, market, now)
    for key, case in rows:
        updated = progress(case, market, q, now)
        if updated != case:
            conn.execute("UPDATE bob_early_warning_spot_cases SET open=%s,payload=%s::jsonb WHERE id=%s",
                         (updated["status"] == "open", json.dumps(updated, allow_nan=False), key))
    if len(rows) >= 2 or not warning_eligible(market, q, now):
        return
    candidate = new_case(market, q)
    if any(x["id"] == candidate["id"] for _,x in rows):
        return
    conn.execute("INSERT INTO bob_early_warning_spot_cases VALUES (%s,TRUE,%s::jsonb) ON CONFLICT DO NOTHING",
                 (candidate["id"], json.dumps(candidate, allow_nan=False)))


def report(conn):
    # A bounded diagnostic preview, not an exhaustive profit or win-rate claim.
    rows = conn.execute("SELECT payload FROM bob_early_warning_spot_cases ORDER BY id DESC LIMIT 100").fetchall()
    samples = [x[0] for x in rows]
    paired = [x["pairedSpotDifferencePct"] for x in samples if shared.number(x.get("pairedSpotDifferencePct"))]
    return dict(version=VERSION, status="collecting" if samples else "waiting-first-original-warning",
                casesSampled=len(samples), previewTruncated=len(samples)==100,
                open=sum(x["status"]=="open" for x in samples),
                complete=sum(x["status"]=="complete" for x in samples),
                inconclusive=sum(x["status"]=="inconclusive" for x in samples),
                mainNeverConfirmed=sum(x["arms"]["confirmed"]["status"]=="no-entry" for x in samples),
                pairedCompleted=len(paired), pairedSpotDifferencePctSum=round(sum(paired),6),
                checkedAt=max((x.get("checkedAt",0) for x in samples),default=None),
                readOnly=True, realOrders=False, productReturnVerified=False,
                automaticPolicyChanges=False, strategyWinnerConfirmed=False,
                spotRoundTripCostAssumptionPct=COST_PCT,
                note="Original spot-only hypothetical stop/target; observed exits not guaranteed fills. No product quotes, KO, broker fees or real profit. Old warnings are not backfilled.")
