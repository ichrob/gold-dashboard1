"""Prospective rapid-entry / leveraged-spot research. Paper only; never broker orders.

Independent of Bob's main EMA/MACD/MTF entry approval. Original closed 1m
XAU/USD bars and fresh spot observation are mandatory for entries. This is
NOT a DEGIRO turbo price model: no verified KO, bid/ask, financing, currency
or fill proof; leverage multipliers are labelled counterfactual proxies.
"""
import copy
import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import intraday_timing_study as candles

VERSION = "rapid-leverage-20261110-v1"
MINUTE = 60000
SETUPS = ("breakout", "impulse", "pullback", "news-impulse")
LEVERS = (3, 5, 8, 10, 15, 20, 30)
INITIAL_EUR = 1000.0
MAX_EXPOSURE = .65
RISK_FRACTION = .01
# Explicit assumptions, NOT observed DEGIRO costs.
ROUND_TRIP_VARIABLE_COST = .006
ROUND_TRIP_FIXED_EUR = 2.0
MAX_MINUTES = 300
MAX_TRADES_PER_SETUP = 100
NOTE = ("Prospektive Forschungs-Schattenkonten, keine Orders und keine Freigabe. "
        "Hebel sind mathematische Spot-Proxys, KEINE historischen Turbo-Kurse. "
        "0,6 % variable Gesamtkosten plus 2 EUR pro virtuellem Trade sind "
        "bloße Szenarioannahmen; echte Geld-/Briefkurse, KO-Barrieren, "
        "Währungsumrechnung, Slippage und Ausführungen fehlen. "
        "Stops wirken nur beim nächsten tatsächlich beobachteten Kurs, "
        "nicht garantiert am errechneten Stop-Preis. "
        "Keine automatisch nachgewiesene beste Hebelstufe.")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def positive(value):
    return finite(value) and value > 0


def local_session(now):
    dt = datetime.fromtimestamp(now / 1000, ZoneInfo("Europe/Zurich"))
    return dt.weekday() < 5 and (8 <= dt.hour < 21 or (dt.hour == 21 and dt.minute < 45))


def calendar_events():
    """Read official calendar only; no guess at actual surprise or reaction."""
    import economic_calendar
    view = economic_calendar.snapshot()
    result = []
    for ev in view.get("events", []):
        if ev.get("importance") != "hoch" or ev.get("dateOnly") or ev.get("sourceFresh") is not True:
            continue
        try:
            at = datetime.fromisoformat(ev["at"])
            if at.tzinfo is not None:
                result.append(dict(at=int(at.timestamp() * 1000), title=str(ev.get("title") or "")[:80],
                                   source=str(ev.get("source") or "")[:20]))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return result


def atr5(bars):
    ranges = []
    for prev, b in zip(bars[-15:-1], bars[-14:]):
        ranges.append(max(b["high"] - b["low"], abs(b["high"] - prev["close"]),
                          abs(b["low"] - prev["close"])))
    return sum(ranges) / len(ranges) if len(ranges) == 14 else None


def candidate_signals(rows, now, events=()):
    """Uses already closed five-minute bars, with no later-price knowledge."""
    bars = candles.aggregate(rows, 5, now)
    if len(bars) < 20 or not 0 <= now - bars[-1]["closeTime"] <= 90000:
        return {name: dict(direction=None, reason="fresh-closed-5m-missing") for name in SETUPS}
    b, prev, third = bars[-1], bars[-2], bars[-3]
    atr = atr5(bars)
    if not positive(atr):
        return {name: dict(direction=None, reason="atr-unavailable") for name in SETUPS}
    sign = 1 if b["close"] > b["open"] else -1 if b["close"] < b["open"] else 0
    body = abs(b["close"] - b["open"])
    last_change = b["close"] - prev["close"]
    previous_high = max(x["high"] for x in bars[-7:-1])
    previous_low = min(x["low"] for x in bars[-7:-1])
    breakout = ("LONG" if b["close"] > previous_high + .1 * atr and sign > 0 and body >= .25 * atr
                else "SHORT" if b["close"] < previous_low - .1 * atr and sign < 0 and body >= .25 * atr
                else None)
    strong = abs(last_change) >= .8 * atr and body >= .5 * atr
    impulse = ("LONG" if strong and sign > 0 and b["high"] - b["close"] <= .25 * (b["high"] - b["low"])
               else "SHORT" if strong and sign < 0 and b["close"] - b["low"] <= .25 * (b["high"] - b["low"])
               else None)
    # Prior momentum, a bounded counter-bar, then a resumed closed-bar move.
    prior_sign = 1 if third["close"] > third["open"] else -1
    retrace = abs(prev["close"] - third["close"])
    pullback = ("LONG" if prior_sign > 0 and third["close"]-third["open"] >= .5*atr
                and prev["close"] < prev["open"] and prev["close"] < third["close"]
                and .15 * atr <= retrace <= .9 * atr and sign > 0
                and b["close"] > prev["high"] and body >= .25 * atr
                else "SHORT" if prior_sign < 0 and third["open"]-third["close"] >= .5*atr
                and prev["close"] > prev["open"] and prev["close"] > third["close"]
                and .15 * atr <= retrace <= .9 * atr and sign < 0
                and b["close"] < prev["low"] and body >= .25 * atr
                else None)
    event = next((e for e in events if finite(e.get("at"))
                  and 0 <= b["closeTime"] - e["at"] <= 15 * MINUTE), None)
    sides = dict(breakout=breakout, impulse=impulse, pullback=pullback,
                 **{"news-impulse": impulse if event else None})
    out = {}
    for name, side in sides.items():
        out[name] = dict(direction=side, reason=None if side else (
            "no-verified-scheduled-release" if name == "news-impulse" and not event else "no-setup"),
            atr=atr, closedAt=b["closeTime"], barAt=b["openTime"],
            recentHigh=max(x["high"] for x in bars[-4:]),
            recentLow=min(x["low"] for x in bars[-4:]),
            event=copy.deepcopy(event) if name == "news-impulse" else None,
            estimated=False)
    return out


def seed(now):
    return dict(version=VERSION, startedAt=int(now), checkedAt=None,
                status="collecting", sampleType="original-spot-only",
                arms={name: dict(position=None, started=0, closed=0, inconclusive=0,
                                 lastSignal=None, lastReason=None, blockCounts={},
                                 levers={str(lev): dict(equityEur=INITIAL_EUR, peakEur=INITIAL_EUR,
                                                       netEur=0.0, completed=0, wins=0,
                                                       maxDrawdownPct=0.0, excluded=0)
                                         for lev in LEVERS}) for name in SETUPS},
                recent=[], originalEvidenceComplete=False)


def open_position(name, signal, price, now, arm):
    sign = 1 if signal["direction"] == "LONG" else -1
    entry = price["price"]
    structure = (signal["recentLow"] - .2 * signal["atr"] if sign > 0
                 else signal["recentHigh"] + .2 * signal["atr"])
    structure_risk = sign * (entry - structure)
    risk = max(.8 * signal["atr"], min(3.0 * signal["atr"], structure_risk))
    if not positive(risk) or risk / entry > .05:
        return None, "stop-distance-invalid"
    return dict(id=f"{VERSION}:{name}:{signal['closedAt']}", setup=name, direction=signal["direction"],
                signal=copy.deepcopy(signal), entryAt=now, entrySourceAt=price["at"],
                lastObservedAt=now, lastSourceAt=price["at"], entry=entry,
                initialStop=entry-sign*risk, stop=entry-sign*risk,
                target=entry+sign*2*risk, risk=risk, atr=signal["atr"], bestPrice=entry,
                maxAdversePct=0., maxFavorablePct=0., status="open",
                costAssumptions=dict(variable=ROUND_TRIP_VARIABLE_COST, fixedEur=ROUND_TRIP_FIXED_EUR),
                resultScope="spot-leverage-proxy-not-DEGIRO-product", realOrders=False,
                productReturnVerified=False), None


def comparison(position, arm, exit_price):
    """Same entry, stop, exit clock for every leverage. Risk-adjust capital."""
    sign = 1 if position["direction"] == "LONG" else -1
    move = sign * (exit_price / position["entry"] - 1)
    risk_pct = position["risk"] / position["entry"]
    results = {}
    for lev in LEVERS:
        slot = arm["levers"][str(lev)]
        equity = slot["equityEur"]
        # Fixed 1% initial equity loss budget under ideal stop execution;
        # this is not a loss guarantee for a gapping or KO product.
        allocated = min(equity * MAX_EXPOSURE,
                        max(0., equity * RISK_FRACTION / (lev * risk_pct)))
        # Even the spot-leverage proxy becomes nonsensical below -100% value.
        if not positive(allocated) or 1 + lev * move <= 0:
            slot["excluded"] += 1
            results[str(lev)] = dict(status="unpriced-or-wipeout-possible",
                                     netEur=None, productReturnVerified=False)
            continue
        gross = allocated * lev * move
        costs = allocated * ROUND_TRIP_VARIABLE_COST + ROUND_TRIP_FIXED_EUR
        net = gross - costs
        slot["equityEur"] = max(0., equity + net)
        slot["peakEur"] = max(slot["peakEur"], slot["equityEur"])
        slot["maxDrawdownPct"] = max(slot["maxDrawdownPct"],
            100 * (slot["peakEur"]-slot["equityEur"]) / slot["peakEur"])
        slot["netEur"] += net
        slot["completed"] += 1
        slot["wins"] += int(net > 0)
        results[str(lev)] = dict(status="modeled-only", investedEur=round(allocated, 2),
                                grossEur=round(gross, 2), assumedCostsEur=round(costs, 2),
                                netEur=round(net, 2), fixedRiskFraction=RISK_FRACTION,
                                resultScope="leveraged-spot-proxy", productReturnVerified=False,
                                koBarrierVerified=False, fillVerified=False)
    return results


def advance(original, bundle, now, events=()):
    state = copy.deepcopy(original)
    if state["checkedAt"] is not None and now <= state["checkedAt"]:
        return state, []
    state["checkedAt"] = now
    rows, error = candles.minute_history(bundle, now, modeled=False)
    price = candles.source(bundle, now, modeled=False)
    signals = candidate_signals(rows, now, events) if rows else {
        name: dict(direction=None, reason=error or "minute-history-missing") for name in SETUPS}
    completed = []
    for name in SETUPS:
        arm = state["arms"][name]
        p = arm["position"]
        sig = signals[name]
        if p:
            # A missing quote or a large observation gap cannot create an ideal stop fill.
            if not price["available"] and now - p["lastObservedAt"] > 90000:
                p.update(status="inconclusive", exitReason="spot-unavailable",
                         closedAt=now, results=None)
            elif price["available"] and (now-p["lastObservedAt"] > 90000 or
                                         price["at"]-p["lastSourceAt"] > 90000):
                p.update(status="inconclusive", exitReason="observation-gap",
                         closedAt=now, results=None)
            elif price["available"] and price["at"] > p["lastSourceAt"]:
                observed = price["price"]
                sign = 1 if p["direction"] == "LONG" else -1
                movement = sign * (observed-p["entry"])
                p["maxAdversePct"] = max(p["maxAdversePct"], -100*movement/p["entry"])
                p["maxFavorablePct"] = max(p["maxFavorablePct"], 100*movement/p["entry"])
                held = price["at"]-p["entrySourceAt"]
                why = ("stop-observed" if sign*(observed-p["stop"])<=0 else
                       "target-observed" if sign*(observed-p["target"])>=0 else
                       "session-end" if not local_session(now) else
                       "time-limit" if held>=MAX_MINUTES*MINUTE else
                       "no-progress" if held>=30*MINUTE and movement < .25*p["risk"] else None)
                p["lastSourceAt"], p["lastObservedAt"] = price["at"], now
                if why:
                    p.update(status="closed", exitReason=why, closedAt=now,
                             exitSourceAt=price["at"], exitPrice=observed)
                    p["results"] = comparison(p, arm, observed)
                else:
                    if sign*(observed-p["bestPrice"])>0:
                        p["bestPrice"] = observed
                    proposed = p["initialStop"]
                    if sign*(p["bestPrice"]-p["entry"])>=p["risk"]:
                        proposed = p["entry"]
                    if sign*(p["bestPrice"]-p["entry"])>=1.5*p["risk"]:
                        proposed = p["bestPrice"]-sign*p["atr"]
                    if sign*(proposed-p["stop"])>0:
                        p["stop"] = proposed
            if p["status"] != "open":
                arm["closed" if p["status"]=="closed" else "inconclusive"] += 1
                completed.append(p)
                state["recent"] = (state["recent"] + [dict(id=p["id"], setup=name,
                    status=p["status"], exitReason=p.get("exitReason"), closedAt=now,
                    direction=p["direction"], results=p.get("results"))])[-12:]
                arm["position"] = None
            continue  # Never close and reopen on one observation.
        key = f"{sig.get('closedAt')}:{sig.get('direction')}"
        arm["lastReason"] = sig.get("reason")
        if sig.get("reason"):
            if key != arm.get("lastCheckedSignal"):
                why = sig["reason"]
                arm["blockCounts"][why] = arm["blockCounts"].get(why, 0)+1
        arm["lastCheckedSignal"] = key
        if (sig.get("direction") not in ("LONG", "SHORT") or
                not price["available"] or not rows or not local_session(now)
                or now - sig["closedAt"] > 90000 or price["at"] < sig["closedAt"] or
                arm["started"] >= MAX_TRADES_PER_SETUP or key == arm["lastSignal"]):
            continue
        position, why = open_position(name, sig, price, now, arm)
        if not position:
            arm["lastReason"] = why
            continue
        arm["lastSignal"] = key
        arm["started"] += 1
        arm["position"] = position
        arm["lastReason"] = None
    return state, completed


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_rapid_leverage_state
        (id TEXT PRIMARY KEY, payload JSONB NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_rapid_leverage_cases
        (id TEXT PRIMARY KEY, setup TEXT NOT NULL, payload JSONB NOT NULL)""")


def tick(conn, bundle, now):
    row = conn.execute("SELECT payload FROM bob_rapid_leverage_state WHERE id=%s FOR UPDATE",
                       (VERSION,)).fetchone()
    original = row[0] if row else seed(now)
    # Calendar failure never becomes an invented calendar/news signal.
    try:
        events = calendar_events()
    except Exception:
        events = []
    state, completed = advance(original, bundle, now, events)
    for case in completed:
        conn.execute("""INSERT INTO bob_rapid_leverage_cases VALUES(%s,%s,%s::jsonb)
            ON CONFLICT DO NOTHING""", (case["id"],case["setup"],json.dumps(case,allow_nan=False)))
    conn.execute("""INSERT INTO bob_rapid_leverage_state VALUES(%s,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload""",
        (VERSION,json.dumps(state,allow_nan=False)))


def report(conn):
    row = conn.execute("SELECT payload FROM bob_rapid_leverage_state WHERE id=%s",
                       (VERSION,)).fetchone()
    if not row:
        return dict(version=VERSION, status="awaiting-first-worker-check",
                    realOrders=False, strategyWinnerConfirmed=False, note=NOTE)
    s = row[0]
    arms = []
    for name, a in s["arms"].items():
        arms.append(dict(setup=name, started=a["started"], closed=a["closed"],
                         inconclusive=a["inconclusive"], open=bool(a.get("position")),
                         latestBlockReason=a["lastReason"], blockCounts=a["blockCounts"],
                         levers=[dict(leverage=int(lev), **slot,
                                      modeledReturnPct=round(100*(slot["equityEur"]/INITIAL_EUR-1),3))
                                 for lev,slot in a["levers"].items()]))
    return dict(version=VERSION, startedAt=s["startedAt"], checkedAt=s["checkedAt"],
                status=s["status"], setups=arms, recent=s["recent"],
                comparisonMode="same-observed-entry-stop-exit; risk-budgeted-spot-proxy",
                riskFraction=RISK_FRACTION, maxExposure=MAX_EXPOSURE,
                realOrders=False, originalDataOnly=True, productReturnVerified=False,
                strategyWinnerConfirmed=False, liveRulesChanged=False, note=NOTE)
