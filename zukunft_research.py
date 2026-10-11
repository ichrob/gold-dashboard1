"""BOB Zukunft: isolated, reproducible research with OBSERVED quotes only.

No networking, broker client, database writes, scheduling or execution endpoints.
One instrument and one LONG/SHORT knockout product per input series.
Signals are read at t-1, hypothetical fills use the product ask/bid at t.
Results are research estimates, never execution evidence or trading permission.
"""
import json
import math
import sys
from datetime import datetime, timezone

VERSION = "zukunft-observed-walkforward-v1"
STRATEGIES = ("baseline", "strict_trend", "breakout", "pullback")
THRESHOLDS = (65, 70, 75, 80)
DEFAULTS = dict(
    start_capital_eur=100.0, exposure_fraction=0.65,
    risk_fraction=0.01, stop_fraction=0.08,
    target_fraction=0.16, trailing_fraction=0.07,
    max_quote_age_seconds=90, max_gap_seconds=300,
    min_ko_distance_fraction=0.08,
    slippage_bps=20, fee_eur_per_side=0.0,
    financing_eur_per_day_per_unit=0.0,
    train_rows=180, test_rows=60, purge_rows=5,
    min_train_trades=2, min_oos_trades=30,
)


class EvidenceError(ValueError):
    pass


def _number(v, key, zero_ok=False):
    if type(v) not in (int, float) or not math.isfinite(v) or (v < 0 if zero_ok else v <= 0):
        raise EvidenceError("Invalid " + key)
    return float(v)


def _time(s):
    if not isinstance(s, str):
        raise EvidenceError("Timezone-aware observation timestamp required")
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("Invalid timestamp") from exc
    if d.tzinfo is None:
        raise EvidenceError("Timestamp lacks timezone")
    return d.astimezone(timezone.utc).timestamp()


def prepare(payload):
    """Reject synthetic/undocumented, reordered, future-dated or inconsistent evidence."""
    if not isinstance(payload, dict) or payload.get("schema") != "bob-zukunft-observed-v1":
        raise EvidenceError("Observed evidence schema required")
    if payload.get("synthetic") is not False or payload.get("realOrders") is not False:
        raise EvidenceError("Observed paper evidence must not claim actual execution")
    isin = payload.get("isin")
    side = payload.get("side")
    if not isinstance(isin, str) or len(isin) != 12 or side not in ("LONG", "SHORT"):
        raise EvidenceError("One confirmed ISIN and one side required")
    supplied = payload.get("costs")
    if not isinstance(supplied, dict) or set(supplied) != {
            "fee_eur_per_side", "slippage_bps", "financing_eur_per_day_per_unit"}:
        raise EvidenceError("Explicit cost assumptions required, including zero values")
    cfg = dict(DEFAULTS)
    cfg.update(supplied)
    params = payload.get("settings", {})
    if not isinstance(params, dict) or set(params) - set(DEFAULTS) or set(params) & set(supplied):
        raise EvidenceError("Unknown research setting or duplicate cost assumption")
    cfg.update(params)
    for key in ("start_capital_eur", "exposure_fraction", "risk_fraction", "stop_fraction",
                "target_fraction", "trailing_fraction", "max_quote_age_seconds",
                "max_gap_seconds", "min_ko_distance_fraction"):
        _number(cfg[key], key)
    for key in ("slippage_bps", "fee_eur_per_side", "financing_eur_per_day_per_unit"):
        _number(cfg[key], key, zero_ok=True)
    if not 0 < cfg["risk_fraction"] <= .05 or not 0 < cfg["exposure_fraction"] <= 1:
        raise EvidenceError("Risk or exposure outside research limits")
    if cfg["slippage_bps"] > 1000 or cfg["stop_fraction"] >= 1 or cfg["trailing_fraction"] >= 1:
        raise EvidenceError("Unsafe research parameters")
    for key in ("train_rows", "test_rows", "purge_rows", "min_train_trades", "min_oos_trades"):
        if type(cfg[key]) is not int or cfg[key] < (0 if key == "purge_rows" else 1):
            raise EvidenceError("Invalid window length")
    raw = payload.get("observations")
    if not isinstance(raw, list) or not raw:
        raise EvidenceError("No observed product quotes")
    rows = []
    last = None
    for item in raw:
        if not isinstance(item, dict):
            raise EvidenceError("Malformed observation")
        at = _time(item.get("at"))
        source_at = _time(item.get("source_at"))
        if last is not None and at <= last:
            raise EvidenceError("Observations must be strictly chronological; no duplicates")
        if source_at > at:
            raise EvidenceError("Future quote timestamp (lookahead)")
        last = at
        bid, ask = _number(item.get("bid_eur"), "bid_eur"), _number(item.get("ask_eur"), "ask_eur")
        underlying = _number(item.get("underlying_usd"), "underlying_usd")
        score = item.get("score")
        if bid > ask or type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 100:
            raise EvidenceError("Invalid spread or directional score")
        if item.get("bar_closed") is not True:
            raise EvidenceError("Signal must come from a closed candle")
        if item.get("approved") not in (True, False) or item.get("market_open") not in (True, False):
            raise EvidenceError("Explicit approval and market state required")
        if item.get("trend") not in ("LONG", "SHORT", "NEUTRAL"):
            raise EvidenceError("Trend missing")
        if "side" in item and item["side"] != side:
            raise EvidenceError("Observed product direction changed")
        if not isinstance(item.get("quote_source"), str) or not item["quote_source"].strip():
            raise EvidenceError("Quote provenance missing")
        ko = _number(item.get("ko_distance_fraction"), "ko_distance_fraction")
        rows.append(dict(at=at, source_at=source_at, bid=bid, ask=ask,
                         underlying=underlying, score=float(score), trend=item["trend"],
                         approved=item["approved"], market_open=item["market_open"],
                         quote_source=item["quote_source"], ko=ko))
    return isin, side, rows, cfg


def _fresh(q, cfg):
    return (q["market_open"] and q["approved"]
            and 0 <= q["at"] - q["source_at"] <= cfg["max_quote_age_seconds"]
            and q["ko"] >= cfg["min_ko_distance_fraction"])


def _gap(a, b, cfg):
    return b["at"] - a["at"] > cfg["max_gap_seconds"]


def _entry_signal(rows, i, side, strategy, threshold, cfg, model=None):
    """At i, use t-1 closed-candle features only; quote at i is for pricing."""
    if i < 2 or _gap(rows[i-1], rows[i], cfg):
        return False
    prev, cur = rows[i-1], rows[i]
    if not (_fresh(prev, cfg) and _fresh(cur, cfg)):
        return False
    signed_score = prev["score"] if side == "LONG" else 100-prev["score"]
    if signed_score < threshold:
        return False
    if strategy == "strict_trend" and prev["trend"] != side:
        return False
    direction = 1 if side == "LONG" else -1
    if strategy == "breakout":
        if i < 12 or any(_gap(rows[k-1], rows[k], cfg) for k in range(i-11, i)):
            return False
        history = [r["underlying"] for r in rows[i-11:i-1]]
        if not (prev["underlying"] > max(history) if direction == 1
                else prev["underlying"] < min(history)):
            return False
    if strategy == "pullback":
        if i < 12 or any(_gap(rows[k-1], rows[k], cfg) for k in range(i-11, i)):
            return False
        old_avg = sum(r["underlying"] for r in rows[i-11:i-2]) / 9
        new_avg = sum(r["underlying"] for r in rows[i-10:i-1]) / 9
        prior = rows[i-2]["underlying"]
        if not (direction*(prior-old_avg) <= 0 and direction*(prev["underlying"]-new_avg) > 0):
            return False
    if model is not None:
        feat = _features(rows, i-1, side, cfg)
        if feat is None or _predict(model, feat) < .55:
            return False
    return True


def _features(rows, i, side, cfg):
    if i < 4 or any(_gap(rows[k-1], rows[k], cfg) for k in range(i-3, i+1)):
        return None
    q = rows[i]
    if not _fresh(q, cfg):
        return None
    direction = 1 if side == "LONG" else -1
    score = (q["score"] if side == "LONG" else 100-q["score"]) / 100
    momentum = direction*(q["underlying"]/rows[i-3]["underlying"]-1)
    trend = 1.0 if q["trend"] == side else 0.0
    return [1.0, 2*score-1, max(-1.0, min(1.0, 50*momentum)), trend]


def _predict(weights, features):
    z = max(-25, min(25, sum(a*b for a,b in zip(weights, features))))
    return 1.0/(1.0+math.exp(-z))


def fit_shadow(rows, side, train_start, train_end, cfg, horizon=5):
    """Fit on train-only labels; purge all examples whose future reaches the boundary."""
    examples = []
    for i in range(max(train_start+4, 4), train_end-horizon-1):
        f = _features(rows, i, side, cfg)
        entry, exit_row = rows[i+1], rows[i+horizon]
        if f is None or not _fresh(entry, cfg) or not _fresh(exit_row, cfg):
            continue
        if any(_gap(rows[k-1], rows[k], cfg) for k in range(i+1, i+horizon+1)):
            continue
        hypothetical_cost = entry["ask"]*(1+cfg["slippage_bps"]/10000)
        exit_value = exit_row["bid"]*(1-cfg["slippage_bps"]/10000)
        estimated_net = exit_value-hypothetical_cost-2*cfg["fee_eur_per_side"]
        y = 1.0 if estimated_net > 0 else 0.0
        examples.append((f, y))
    if len(examples) < 30 or len(set(y for _,y in examples)) < 2:
        return None, len(examples)
    w = [0.0]*4
    for _ in range(160):
        grad = [0.0]*4
        for f, y in examples:
            e = _predict(w, f)-y
            for k in range(4):
                grad[k] += e*f[k]
        for k in range(4):
            w[k] -= 0.4*(grad[k]/len(examples) + (0 if k == 0 else .05*w[k]))
    return w, len(examples)


def replay(rows, side, cfg, strategy, threshold, start, stop, model=None):
    """Fixed-budget one-instrument paper replay: ask entry, bid exit, no fabricated fills."""
    position = None
    profit = 0.0
    peak = 0.0
    max_dd = 0.0
    trades = []
    uncertain = []
    for i in range(start, stop):
        now = rows[i]
        closed_this_row = False
        if i and _gap(rows[i-1], now, cfg) and position is not None:
            uncertain.append("Unobserved price gap with open paper position")
            position = None   # never invent an exit
        if position is not None:
            if not _fresh(now, cfg):
                uncertain.append("Missing/stale executable bid with open paper position")
                position = None
            else:
                sell = now["bid"]*(1-cfg["slippage_bps"]/10000)
                reason = ("stop" if now["bid"] <= position["stop"] else
                          "target" if now["bid"] >= position["target"] else None)
                if reason:
                    held_days = (now["at"]-position["at"])/86400
                    funding = held_days*cfg["financing_eur_per_day_per_unit"]*position["qty"]
                    net = position["qty"]*(sell-position["buy"])-2*cfg["fee_eur_per_side"]-funding
                    profit += net
                    peak = max(peak, profit)
                    max_dd = max(max_dd, peak-profit)
                    trades.append(dict(entry_at=position["at"], exit_at=now["at"],
                                       qty=position["qty"], net_eur=round(net, 6),
                                       reason=reason))
                    position = None
                    closed_this_row = True
                else:
                    position["stop"] = max(position["stop"], now["bid"]*(1-cfg["trailing_fraction"]))
        if position is None and not closed_this_row and i > start and _entry_signal(rows, i, side, strategy, threshold, cfg, model):
            buy = now["ask"]*(1+cfg["slippage_bps"]/10000)
            risk_eur = buy*cfg["stop_fraction"]
            qty = int(min(cfg["start_capital_eur"]*cfg["exposure_fraction"]/buy,
                          cfg["start_capital_eur"]*cfg["risk_fraction"]/risk_eur))
            if qty > 0 and qty*buy+cfg["fee_eur_per_side"] <= cfg["start_capital_eur"]:
                position = dict(at=now["at"], buy=buy, qty=qty,
                                stop=buy*(1-cfg["stop_fraction"]),
                                target=buy*(1+cfg["target_fraction"]))
    if position is not None:
        uncertain.append("Open position at test boundary; no hypothetical exit recorded")
    return dict(trades=len(trades), wins=sum(t["net_eur"] > 0 for t in trades),
                net_eur=round(profit, 4), max_drawdown_eur=round(max_dd, 4),
                complete=not uncertain, uncertain=uncertain[:10],
                ledger=trades)


def compare(payload):
    isin, side, rows, cfg = prepare(payload)
    train_len, test_len, purge = cfg["train_rows"], cfg["test_rows"], cfg["purge_rows"]
    folds = []
    start = train_len + purge
    while start + test_len <= len(rows):
        train_end = start-purge
        train_start = max(0, train_end-train_len)
        variants = {}
        weights, nlabels = fit_shadow(rows, side, train_start, train_end, cfg)
        for name in STRATEGIES:
            # Tuning sees training rows only. Never select thresholds by OOS returns.
            choices = []
            for threshold in THRESHOLDS:
                trial = replay(rows, side, cfg, name, threshold, train_start, train_end)
                if trial["complete"] and trial["trades"] >= cfg["min_train_trades"]:
                    choices.append((trial["net_eur"], -trial["max_drawdown_eur"], threshold))
            if not choices:
                variants[name] = dict(status="insufficient_training")
                continue
            _, _, threshold = max(choices)
            oos = replay(rows, side, cfg, name, threshold, start, start+test_len)
            variants[name] = dict(status="evaluated" if oos["complete"] else "unresolved_quotes",
                                  threshold=threshold, **oos)
        if weights is None:
            variants["ml_shadow"] = dict(status="insufficient_training", training_labels=nlabels)
        else:
            # Research-only gate: ML never controls Bob's orders or deployed strategy.
            oos = replay(rows, side, cfg, "baseline", 70, start, start+test_len, model=weights)
            variants["ml_shadow"] = dict(status="evaluated" if oos["complete"] else "unresolved_quotes",
                                         training_labels=nlabels, threshold=70, **oos)
        folds.append(dict(train=[rows[train_start]["at"], rows[train_end-1]["at"]],
                          test=[rows[start]["at"], rows[start+test_len-1]["at"]],
                          purged_rows=purge, variants=variants))
        start += test_len  # no overlapping test periods
    totals = {}
    for name in STRATEGIES + ("ml_shadow",):
        valid = [f["variants"][name] for f in folds if f["variants"][name]["status"] == "evaluated"]
        total_trades = sum(v["trades"] for v in valid)
        totals[name] = dict(folds=len(valid), trades=total_trades,
                            net_eur=round(sum(v["net_eur"] for v in valid), 4),
                            qualifying=bool(len(valid) >= 3 and total_trades >= cfg["min_oos_trades"]),
                            unresolved_folds=len(folds)-len(valid))
    return dict(version=VERSION, mode="RESEARCH_ONLY", realOrders=False,
                isin=isin, side=side, observations=len(rows), folds=folds,
                totals=totals, cost_assumptions={key:cfg[key] for key in
                ("fee_eur_per_side", "slippage_bps", "financing_eur_per_day_per_unit")},
                verdict="No automatic strategy promotion; await independent evidence",
                qualified_for_live_trading=False)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python zukunft_research.py observed.json report.json", file=sys.stderr)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as handle:
            result = compare(json.load(handle))
        with open(argv[1], "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError) as exc:
        print("Research refused: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
