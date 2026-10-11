"""Reproducible PAPER-ONLY order simulation for Bob.

Synthetic or historical product quotes are processed in timestamp order.
No networking, brokers, credentials, live order endpoints or background jobs.
All prices are EUR product prices, not XAU/USD spot prices.
"""
from datetime import datetime, timezone
from math import floor, isfinite

DEFAULTS = {
    "starting_eur": 100.0,
    "risk_fraction": 0.01,
    "daily_loss_fraction": 0.03,
    "stop_fraction": 0.08,
    "target_fraction": 0.15,
    "trailing_fraction": 0.07,
    "slippage_fraction": 0.002,
    "fee_eur_per_order": 0.0,
    "max_spread_fraction": 0.05,
    "min_ko_distance_fraction": 0.08,
    "max_quote_age_seconds": 90,
}


def positive(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def quote_time(raw):
    if not isinstance(raw, str):
        raise ValueError("Quellenzeit fehlt")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Ungültige Quellenzeit") from exc
    if dt.tzinfo is None:
        raise ValueError("Quellenzeit benötigt Zeitzone")
    return dt.astimezone(timezone.utc)


def accepted_signal(setup):
    """Never infer permission to enter from a product price alone."""
    side = setup.get("side")
    score = setup.get("score")
    if side not in ("LONG", "SHORT") or type(score) not in (int, float) or not isfinite(score):
        return "Marktsignal fehlt"
    if (side == "LONG" and score < 70) or (side == "SHORT" and score > 30):
        return "Signal nicht bestätigt"
    if setup.get("approved_product") is not True:
        return "Produkt nicht freigegeben"
    distance = setup.get("ko_distance_fraction")
    if not positive(distance) or distance < DEFAULTS["min_ko_distance_fraction"]:
        return "KO-Abstand nicht ausreichend"
    if not setup.get("isin") or len(str(setup["isin"])) != 12:
        return "ISIN fehlt"
    return None


def simulate(quotes, setup, config=None):
    """Execute one simulated entry and exit, without pretending to run live.

    Quotes: [{at: ISO-8601 with TZ, bid: float EUR, ask: float EUR,
              age_seconds: nonnegative number}]. Bid is liquidation price;
    ask is entry price. Quotes must be in strict chronological order.
    Stops use executable bids; gap-through stops fill at the worse available
    quote. Trailing stop is updated *after* checking the existing stop.
    This is tick replay, not intrabar/candle fills.
    """
    cfg = dict(DEFAULTS)
    if config:
        if set(config) - set(DEFAULTS):
            raise ValueError("Unbekannte Konfiguration")
        cfg.update(config)
    if not all(positive(cfg[k]) for k in (
        "starting_eur", "risk_fraction", "daily_loss_fraction",
        "stop_fraction", "target_fraction", "trailing_fraction",
        "max_quote_age_seconds", "max_spread_fraction",
        "min_ko_distance_fraction"
    )):
        raise ValueError("Ungültige Risikoeinstellung")
    if not 0 < cfg["risk_fraction"] <= 0.05 or not 0 < cfg["daily_loss_fraction"] <= 0.2:
        raise ValueError("Risikolimit zu hoch")
    if not 0 < cfg["stop_fraction"] < 1 or not 0 < cfg["target_fraction"] < 5:
        raise ValueError("Unzulässige Stop-/Zielwerte")
    if not 0 < cfg["trailing_fraction"] < 1:
        raise ValueError("Unzulässiger Trailing-Abstand")
    if type(cfg["slippage_fraction"]) not in (float, int) or not 0 <= cfg["slippage_fraction"] <= 0.1:
        raise ValueError("Ungültige Slippage")
    if type(cfg["fee_eur_per_order"]) not in (int, float) or not isfinite(cfg["fee_eur_per_order"]) or cfg["fee_eur_per_order"] < 0:
        raise ValueError("Ungültige Gebühr")
    cash = float(cfg["starting_eur"])
    initial = cash
    peak = cash
    max_drawdown = 0.0
    position = None
    events = []
    last_dt = None
    signal_error = accepted_signal(setup)
    equity_curve = []
    locked = False
    for i, q in enumerate(quotes):
        stamp = quote_time(q.get("at"))
        if last_dt is not None and stamp <= last_dt:
            raise ValueError("Quote-Zeiten nicht streng aufsteigend")
        last_dt = stamp
        bid, ask, age = q.get("bid"), q.get("ask"), q.get("age_seconds")
        if not positive(bid) or not positive(ask) or bid > ask:
            raise ValueError("Geld-/Briefkurs fehlt oder ist ungültig")
        if type(age) not in (int, float) or not isfinite(age) or age < 0:
            raise ValueError("Kursalter fehlt")
        fresh = age <= cfg["max_quote_age_seconds"]
        spread = (ask-bid) / ((ask+bid)/2)
        executable_sell = max(0.0, bid * (1-cfg["slippage_fraction"]))
        if position is None and not locked:
            reason = signal_error
            if not fresh:
                reason = "Kurs veraltet"
            elif spread > cfg["max_spread_fraction"]:
                reason = "Spread zu hoch"
            if reason:
                events.append({"event": "BLOCKED", "at": q["at"], "reason": reason})
                locked = True  # no late entry on a stale original signal
            else:
                entry_price = ask * (1+cfg["slippage_fraction"])
                initial_stop = entry_price * (1-cfg["stop_fraction"])
                target = entry_price * (1+cfg["target_fraction"])
                estimated_stop_fill = max(0.0, initial_stop*(1-cfg["slippage_fraction"]))
                unit_risk = entry_price-estimated_stop_fill
                fee = cfg["fee_eur_per_order"]
                qty = min(floor((cash-fee)/entry_price), floor((initial*cfg["risk_fraction"]-2*fee)/unit_risk))
                if qty <= 0:
                    events.append({"event": "BLOCKED", "at": q["at"], "reason": "Risikobudget reicht nicht"})
                    locked = True
                else:
                    cash -= qty*entry_price+fee
                    position = {"quantity": qty, "entry": entry_price, "stop": initial_stop,
                                "target": target, "peak_bid": bid, "opened_at": q["at"],
                                "side": setup["side"], "isin": setup["isin"],
                                "costs_eur": fee + qty*(entry_price-ask),
                                "initial_risk_eur": round(qty*unit_risk + 2*fee, 6)}
                    events.append({"event": "BUY_PAPER", "at": q["at"], "isin": setup["isin"],
                                   "quantity": qty, "price_eur": round(entry_price, 6),
                                   "stop_eur": round(initial_stop, 6),
                                   "target_eur": round(target, 6)})
        elif position is not None:
            # If the feed goes stale, we cannot assume an executable exit.
            # Report uncertainty, keep the position and never manufacture a fill.
            if not fresh:
                events.append({"event": "STALE_FEED", "at": q["at"], "reason": "Kein verlässlicher Ausführungskurs"})
            else:
                reason = "STOP" if bid <= position["stop"] else ("TARGET" if bid >= position["target"] else None)
                if reason:
                    pnl = position["quantity"]*(executable_sell-position["entry"])-2*cfg["fee_eur_per_order"]
                    cash += position["quantity"]*executable_sell-cfg["fee_eur_per_order"]
                    events.append({"event": "SELL_PAPER", "at": q["at"], "reason": reason,
                                   "quantity": position["quantity"], "price_eur": round(executable_sell, 6),
                                   "pnl_eur": round(pnl, 4)})
                    position = None
                    locked = True
                else:
                    position["peak_bid"] = max(position["peak_bid"], bid)
                    new_stop = position["peak_bid"]*(1-cfg["trailing_fraction"])
                    if new_stop > position["stop"]:
                        position["stop"] = new_stop
                        events.append({"event": "TRAIL_PAPER", "at": q["at"], "stop_eur": round(new_stop, 6)})
        equity = cash + (position["quantity"]*executable_sell-cfg["fee_eur_per_order"] if position else 0)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak-equity)/peak if peak else 0)
        if equity <= initial*(1-cfg["daily_loss_fraction"]):
            locked = True
        equity_curve.append({"at": q["at"], "equity_eur": round(equity, 4), "quote_fresh": fresh})
    equity = equity_curve[-1]["equity_eur"] if equity_curve else cash
    return {"mode": "PAPER_ONLY", "synthetic": True, "live_order_capable": False,
            "initial_eur": initial, "equity_eur": equity,
            "realized_eur": round(cash-initial + (position["quantity"]*position["entry"] if position else 0), 4),
            "max_drawdown_fraction": round(max_drawdown, 6),
            "position": position, "locked": locked, "events": events,
            "equity_curve": equity_curve, "quotes_processed": len(quotes)}


def demonstration(scenario="target"):
    """Fixed synthetic scenarios for regression tests, never live outcomes."""
    paths = {
        "target": [(0.99, 1.01, 5), (1.04, 1.06, 5),
                   (1.11, 1.13, 5), (1.18, 1.20, 5)],
        "stop_gap": [(0.99, 1.01, 5), (0.81, 0.83, 5)],
        "stale": [(0.99, 1.01, 125), (1.08, 1.10, 5)],
        "trailing": [(0.99, 1.01, 5), (1.08, 1.10, 5),
                     (1.07, 1.09, 5), (0.98, 1.00, 5)],
    }
    if scenario not in paths:
        raise ValueError("Unbekanntes Testszenario")
    quotes = [
        dict(at=f"2026-10-09T08:{i:02d}:00Z", bid=bid, ask=ask,
             age_seconds=age)
        for i, (bid, ask, age) in enumerate(paths[scenario])
    ]
    result = simulate(quotes, {"isin": "DE0000000000", "side": "LONG",
                               "score": 82, "approved_product": True,
                               "ko_distance_fraction": 0.15})
    result["scenario"] = scenario
    result["notice"] = "Künstliche Beispieldaten. Keine Marktprognose, kein echter Trade."
    return result
