"""Bob Zukunft: causal, read-only strategy research on closed 1h reference candles.

Never orders, changes live signals, updates product rankings or promotes models.
The reference instrument is NOT a DEGIRO product. Costs are assumptions and
reported returns do not represent an executable product/account result.
"""
import math
import statistics
import time

VERSION = "zukunft-walkforward-v3-latest12"
HORIZON = 4
WARMUP = 210
TRAIN_END = 420
VALIDATION = 72
TEST = 72
COST_BPS_PER_SIDE = 8.0  # hypothetical fee + slippage, each side; NOT observed
STRATEGIES = ("baseline", "trend-strict", "trend-tight", "breakout", "breakout-confirmed", "mean-revert", "learned-linear")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def normalize(raw):
    """Reject malformed/mixed/duplicated histories, never invent candles."""
    if not isinstance(raw, list):
        raise ValueError("Kerzendaten fehlen")
    rows = []
    instruments = set()
    for item in raw:
        if not isinstance(item, dict) or item.get("isOpen") is not False:
            continue
        ts = item.get("openTime")
        prices = [item.get(k) for k in ("open", "high", "low", "close")]
        if type(ts) is not int or not all(finite(x) and x > 0 for x in prices):
            raise ValueError("Ungültige geschlossene Kerze oder Quellenzeit")
        o, hi, lo, c = prices
        if lo > min(o, c) or hi < max(o, c) or lo > hi:
            raise ValueError("Unmögliche OHLC-Kerze")
        instrument = str(item.get("instrument") or "UNVERIFIED")
        instruments.add(instrument)
        rows.append(dict(openTime=ts, open=o, high=hi, low=lo, close=c))
    if len(instruments) != 1 or "UNVERIFIED" in instruments:
        raise ValueError("Historie muss einem bestätigten Instrument zugeordnet sein")
    rows.sort(key=lambda x: x["openTime"])
    if any(rows[i]["openTime"] <= rows[i-1]["openTime"] for i in range(1, len(rows))):
        raise ValueError("Doppelte Kerzenzeit")
    if any(rows[i]["openTime"] - rows[i-1]["openTime"] < 3600000 for i in range(1, len(rows))):
        raise ValueError("Daten sind keine stündlichen Kerzen")
    return rows, next(iter(instruments))


def ema(values, period):
    out = []
    last = None
    k = 2 / (period + 1)
    for value in values:
        last = value if last is None else k * value + (1-k) * last
        out.append(last)
    return out


def features(bars):
    close = [x["close"] for x in bars]
    e20, e50, e200 = (ema(close, period) for period in (20, 50, 200))
    out = []
    for i, b in enumerate(bars):
        if i < WARMUP:
            out.append(None)
            continue
        prev = bars[i-14:i+1]
        gains = [max(0., prev[j]["close"]-prev[j-1]["close"]) for j in range(1,len(prev))]
        losses = [max(0., prev[j-1]["close"]-prev[j]["close"]) for j in range(1,len(prev))]
        g, l = sum(gains), sum(losses)
        rsi = 50. if g == l == 0 else (100. if l == 0 else 100-100/(1+g/l))
        tr = [max(bars[j]["high"]-bars[j]["low"],
                  abs(bars[j]["high"]-bars[j-1]["close"]),
                  abs(bars[j]["low"]-bars[j-1]["close"])) for j in range(i-13, i+1)]
        atr = max(1e-8, sum(tr)/len(tr))
        high20 = max(x["high"] for x in bars[i-20:i])
        low20 = min(x["low"] for x in bars[i-20:i])
        x = (max(-4., min(4., (close[i]-e20[i])/atr)),
             max(-4., min(4., (e20[i]-e50[i])/atr)),
             max(-4., min(4., (e50[i]-e200[i])/atr)),
             max(-2., min(2., (rsi-50.)/25.)),
             max(-4., min(4., (close[i]-close[i-5])/atr)))
        out.append(dict(e20=e20[i], e50=e50[i], e200=e200[i],
                        rsi=rsi, atr=atr, high20=high20, low20=low20, x=x))
    return out


def sigmoid(x):
    return 1. / (1. + math.exp(-max(-30., min(30., x))))


def fit_linear(bars, f, end):
    """Regularised logistic filter. Labels from TRAIN ONLY, with purge."""
    xs, ys = [], []
    for i in range(WARMUP, end-HORIZON, HORIZON):
        if not contiguous(bars, i, i+HORIZON):
            continue
        entry = bars[i+1]["open"]
        label = 1. if bars[i+HORIZON]["close"] > entry else 0.
        xs.append((1.,) + f[i]["x"])
        ys.append(label)
    if len(xs) < 35 or min(sum(ys), len(ys)-sum(ys)) < 8:
        return None
    weights = [0.] * 6
    for _ in range(90):
        gradient = [0.] * 6
        for x, y in zip(xs, ys):
            error = sigmoid(sum(a*b for a,b in zip(x,weights))) - y
            for j in range(6):
                gradient[j] += error*x[j]
        for j in range(6):
            weights[j] -= .1 * (gradient[j] / len(xs) + (.04*weights[j] if j else 0))
    return weights


def direction(name, i, bars, f, weights):
    x = f[i]
    if not x:
        return 0
    c = bars[i]["close"]
    if name == "baseline":
        if c > x["e200"] and x["e20"] > x["e50"] and 50 < x["rsi"] < 75:
            return 1
        if c < x["e200"] and x["e20"] < x["e50"] and 25 < x["rsi"] < 50:
            return -1
    elif name == "trend-strict":
        if c > x["e20"] > x["e50"] > x["e200"] and 52 < x["rsi"] < 70 and x["x"][4] > .4:
            return 1
        if c < x["e20"] < x["e50"] < x["e200"] and 30 < x["rsi"] < 48 and x["x"][4] < -.4:
            return -1
    elif name == "trend-tight":
        if c > x["e20"] > x["e50"] > x["e200"] and 55 < x["rsi"] < 68 and x["x"][4] > .8:
            return 1
        if c < x["e20"] < x["e50"] < x["e200"] and 32 < x["rsi"] < 45 and x["x"][4] < -.8:
            return -1
    elif name == "breakout":
        if c > x["high20"] and x["e20"] > x["e50"]:
            return 1
        if c < x["low20"] and x["e20"] < x["e50"]:
            return -1
    elif name == "breakout-confirmed":
        # Strict hypothesis: breakout plus stronger RSI and EMA confirmation.
        if c > x["high20"] and x["e20"] > x["e50"] > x["e200"] and x["rsi"] > 55:
            return 1
        if c < x["low20"] and x["e20"] < x["e50"] < x["e200"] and x["rsi"] < 45:
            return -1
    elif name == "mean-revert":
        if x["rsi"] < 30 and c > x["e200"]:
            return 1
        if x["rsi"] > 70 and c < x["e200"]:
            return -1
    elif name == "learned-linear" and weights is not None:
        p = sigmoid(weights[0] + sum(a*b for a,b in zip(weights[1:],x["x"])))
        return 1 if p >= .60 else -1 if p <= .40 else 0
    return 0


def contiguous(bars, start, end):
    return all(bars[j]["openTime"]-bars[j-1]["openTime"] == 3600000
               for j in range(start+1, end+1))


def score(bars, f, name, weights, start, end, cost_bps):
    """Enter on next OPEN; exit at future CLOSE; never overlap positions."""
    trades, skipped, equity, peak, drawdown = [], 0, 1., 1., 0.
    floor = 1.
    i = max(WARMUP, start)
    while i + HORIZON < end:
        side = direction(name, i, bars, f, weights)
        if not side:
            i += 1
            continue
        if not contiguous(bars, i, i+HORIZON):
            skipped += 1
            i += HORIZON
            continue
        entry = bars[i+1]["open"]
        exit_price = bars[i+HORIZON]["close"]
        pnl_pct = side * (exit_price/entry-1) * 100 - 2*cost_bps/100.
        pnl_pct = max(-99., pnl_pct)
        trades.append(pnl_pct)
        equity *= 1 + pnl_pct/100
        floor = min(floor, equity)
        peak = max(peak, equity)
        drawdown = max(drawdown, 100*(1-equity/peak))
        i += HORIZON
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    return dict(trades=len(trades), skippedGap=skipped,
                minEquityIndex=floor,maxEquityIndex=peak,
                winRatePct=round(100*len(wins)/len(trades), 3) if trades else None,
                avgNetPct=round(sum(trades)/len(trades), 4) if trades else None,
                netReturnPct=round(100*(equity-1), 4),
                maxDrawdownPct=round(drawdown, 4),
                profitFactor=round(sum(wins)/-sum(losses), 4) if losses else None,
                grossWinsPct=round(sum(wins),4), grossLossesPct=round(sum(losses),4))


def run(raw, cost_bps=COST_BPS_PER_SIDE):
    """Expanding-train, purged validation, untouched out-of-sample windows."""
    if not finite(cost_bps) or cost_bps < 0 or cost_bps > 100:
        raise ValueError("Unplausible Testkosten")
    bars, instrument = normalize(raw)
    result = dict(version=VERSION, mode="RESEARCH_ONLY", brokerConnected=False,
                  orderExecutionEnabled=False, affectsLiveSignals=False,
                  historicalInstrument=instrument, barInterval="1h",
                  closedBars=len(bars), costBpsPerSide=cost_bps, horizonBars=HORIZON,
                  strategies=list(STRATEGIES), folds=[], approved=False,
                  description="Historische Referenzkerzen; keine DEGIRO-Produktkurse. "
                  "Kosten sind Annahmen, kein nachgewiesener Nettogewinn. "
                  "Die Baseline ist ein vereinfachtes Forschungssignal, nicht Bobs vollständige Live-Logik.")
    if bars:
        result["rangeMs"] = [bars[0]["openTime"], bars[-1]["openTime"]]
    if len(bars) < TRAIN_END+HORIZON+VALIDATION+HORIZON+TEST:
        result.update(status="insufficient", note="Zu wenig geschlossene 1h-Kerzen für getrennte Prüfperioden.")
        return result
    f = features(bars)
    totals = {k: [] for k in STRATEGIES}
    oos = []
    available = range(TRAIN_END, len(bars)-HORIZON-VALIDATION-HORIZON-TEST+1, TEST)
    selected = available[-12:]
    result['foldSelection'] = dict(policy='latest-12-complete-chronological',
        available=len(available),selected=len(selected),omittedEarlier=len(available)-len(selected),
        latestTestEndMs=None,sourceLastBarMs=bars[-1]['openTime'])
    for train_end in selected:
        val_start = train_end+HORIZON
        val_end = val_start+VALIDATION
        test_start = val_end+HORIZON
        test_end = test_start+TEST
        weights = fit_linear(bars, f, train_end)
        v = {name: score(bars,f,name,weights,val_start,val_end,cost_bps) for name in STRATEGIES}
        eligible = [name for name in STRATEGIES
                    if v[name]["trades"] >= 3 and v[name]["netReturnPct"] > 0]
        winner = max(eligible, key=lambda k: (v[k]["netReturnPct"]-v[k]["maxDrawdownPct"], -STRATEGIES.index(k))) if eligible else "baseline"
        # No test data is used for model fitting or strategy choice.
        t = {name: score(bars,f,name,weights,test_start,test_end,cost_bps) for name in STRATEGIES}
        for name in STRATEGIES:
            totals[name].append(t[name])
        oos.append((winner, t[winner], t["baseline"]))
        result["folds"].append(dict(trainEndMs=bars[train_end-1]["openTime"],
            validationStartMs=bars[val_start]["openTime"],
            testStartMs=bars[test_start]["openTime"],
            testEndMs=bars[test_end-1]["openTime"],
            selectedOnValidation=winner, validation=v, outOfSample=t,
            learningFittedOnTrain=weights is not None, selectionUsesTest=False))
    result['foldSelection']['latestTestEndMs'] = result['folds'][-1]['testEndMs']
    def aggregate(rows):
        return dict(trades=sum(z["trades"] for z in rows),
                    meanFoldNetPct=round(statistics.mean(z["netReturnPct"] for z in rows),4),
                    worstFoldNetPct=min(z["netReturnPct"] for z in rows),
                    maxFoldDrawdownPct=max(z["maxDrawdownPct"] for z in rows))
    result["outOfSampleByStrategy"] = {name:aggregate(rows) for name,rows in totals.items()}
    result["validationSelected"] = aggregate([row[1] for row in oos])
    result["samePeriodBaseline"] = aggregate([row[2] for row in oos])
    result["status"] = "evaluated"
    result["evidence"] = dict(folds=len(oos), selectedTrades=result["validationSelected"]["trades"],
        sufficientForResearch=len(oos)>=3 and result["validationSelected"]["trades"]>=30,
        statisticallyConfirmed=False, productNetValidated=False, liveForwardValidated=False)
    result["note"] = ("Keine automatische Regelübernahme. Historische Referenz- statt Geld/Brief-Produktkurse; "
       "kein Echtgeld- oder Broker-Test. Modelle auf Training angepasst, Auswahl auf Validierung, "
       "Ergebnis auf späterem Testfenster. Keine Aussage über zukünftige Gewinne.")
    return result
