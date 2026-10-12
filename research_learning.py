"""Bob's rolling, *research-only* learning loop.

Historical trials suggest shadow candidates. A candidate is frozen before later
closed candles are scored. Product execution costs, observed DEGIRO fills, and
live-rule promotion are deliberately out of scope: no price evidence is invented.
All state is embedded in the daily Postgres strategy report (restart-safe).
"""
import copy
import math

import strategy_lab

VERSION = "bob-rolling-shadow-v1"
MIN_FOLDS = 3
MIN_HISTORIC_TRADES = 30
MIN_FORWARD_SESSIONS = 20
MIN_FORWARD_TRADES = 30
# Logistic weights would need separately frozen coefficients to be prospective.
SHADOWABLE = ("trend-strict", "breakout", "mean-revert")


def _finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def _previous_cycle(previous):
    value = previous.get("learningCycle") if isinstance(previous, dict) else None
    return copy.deepcopy(value) if isinstance(value, dict) and value.get("version") == VERSION else {}


def _new_cycle():
    return dict(version=VERSION, status="collecting", proposal=None,
                rejectedStrategies=[], prospective=dict(sessions=0, trades=0,
                    baselineTrades=0, candidateIndex=1.0, baselineIndex=1.0,
                    lastEvaluatedBarAt=None), experiments=list(strategy_lab.STRATEGIES),
                liveRuleChanged=False, productNetValidated=False, automaticOrder=False,
                reason="Vereinfachte Referenzstudie; echte EUR-Produktkosten fehlen.")


def _choose(report, rejected):
    """Use research folds for *proposal discovery only*, never for live approval."""
    if report.get("status") != "evaluated":
        return None
    evidence = report.get("evidence") or {}
    if evidence.get("folds", 0) < MIN_FOLDS:
        return None
    base = (report.get("outOfSampleByStrategy") or {}).get("baseline") or {}
    if not _finite(base.get("meanFoldNetPct")):
        return None
    scored = []
    for strategy in SHADOWABLE:
        if strategy in rejected:
            continue
        m = (report.get("outOfSampleByStrategy") or {}).get(strategy) or {}
        vals = (m.get("trades"), m.get("meanFoldNetPct"),
                m.get("worstFoldNetPct"), m.get("maxFoldDrawdownPct"))
        if not all(_finite(v) for v in vals) or m["trades"] < MIN_HISTORIC_TRADES:
            continue
        if not (m["meanFoldNetPct"] > max(0, base["meanFoldNetPct"]) and
                m["worstFoldNetPct"] >= base.get("worstFoldNetPct", -math.inf) and
                m["maxFoldDrawdownPct"] <= base.get("maxFoldDrawdownPct", math.inf)):
            continue
        scored.append((m["meanFoldNetPct"] - base["meanFoldNetPct"], strategy))
    return max(scored)[1] if scored else None


def _forward(bars, previous_bar, candidate):
    """Score only positions whose signal and exit occur *after* the frozen cutoff.

    An unchanged or gapped feed adds no independent evidence. The baseline and
    candidate are scored on precisely the same future interval and cost model.
    """
    if candidate not in SHADOWABLE or not _finite(previous_bar):
        return None
    normalized, _ = strategy_lab.normalize(bars)
    if not normalized or normalized[-1]["openTime"] <= previous_bar:
        return None
    start = next((i for i, r in enumerate(normalized)
                  if r["openTime"] > previous_bar), len(normalized))
    if start < strategy_lab.WARMUP or start + strategy_lab.HORIZON >= len(normalized):
        return None
    f = strategy_lab.features(normalized)
    baseline = strategy_lab.score(normalized, f, "baseline", None, start,
                                  len(normalized), strategy_lab.COST_BPS_PER_SIDE)
    alternative = strategy_lab.score(normalized, f, candidate, None, start,
                                     len(normalized), strategy_lab.COST_BPS_PER_SIDE)
    return dict(baseline=baseline, candidate=alternative,
                lastBarAt=normalized[-1]["openTime"], newBars=len(normalized)-start)


def enrich(report, bars, previous=None, *, day):
    """Append transparent suggestions and frozen prospective outcomes to a report.

    This cannot change production market signals, product selection or broker
    state. Nothing is promoted from hypothetical spot performance.
    """
    result = copy.deepcopy(report)
    old = _previous_cycle(previous)
    state = old or _new_cycle()
    state["experiments"] = list(strategy_lab.STRATEGIES)
    state["day"] = day
    state["liveRuleChanged"] = False
    state["productNetValidated"] = False
    state["automaticOrder"] = False
    current_end = (result.get("rangeMs") or [None, None])[-1]
    previous_end = state.get("prospective", {}).get("lastEvaluatedBarAt")
    if previous_end is None:
        previous_end = (previous.get("rangeMs") or [None, None])[-1] if isinstance(previous, dict) else None
    proposal = state.get("proposal")
    if proposal and proposal.get("state") == "shadow":
        if (previous and previous.get("historicalInstrument") and
                previous["historicalInstrument"] != result.get("historicalInstrument")):
            state["status"] = "blocked"
            state["reason"] = "Referenzinstrument gewechselt; kein historischer Vergleich erlaubt."
        elif result.get("status") == "evaluated":
            observation = _forward(bars, previous_end, proposal.get("strategy"))
            if observation:
                p = state["prospective"]
                a = observation["candidate"]
                b = observation["baseline"]
                if a["trades"] or b["trades"]:
                    p["sessions"] += 1
                    p["trades"] += a["trades"]
                    p["baselineTrades"] += b["trades"]
                    p["candidateIndex"] = round(p["candidateIndex"] * (1+a["netReturnPct"]/100), 10)
                    p["baselineIndex"] = round(p["baselineIndex"] * (1+b["netReturnPct"]/100), 10)
                p["lastEvaluatedBarAt"] = observation["lastBarAt"]
                p["lastObservation"] = dict(day=day, newBars=observation["newBars"],
                    candidate=a, baseline=b)
                proposal["lastIndependentDay"] = day
            if (state["prospective"]["sessions"] >= MIN_FORWARD_SESSIONS and
                    state["prospective"]["trades"] >= MIN_FORWARD_TRADES):
                p = state["prospective"]
                if p["candidateIndex"] > 1.0 and p["candidateIndex"] > p["baselineIndex"]:
                    proposal["state"] = "paper-required"
                    state["status"] = "paper-required"
                    state["reason"] = ("Historische und spätere Referenztests positiv. "
                       "Unabhängige DEGIRO-EUR-Produkt- und Kostenprüfungen fehlen: keine Live-Übernahme.")
                else:
                    proposal["state"] = "rejected"
                    state["rejectedStrategies"] = (state.get("rejectedStrategies", [])
                                                  + [proposal["strategy"]])[-len(SHADOWABLE):]
                    state["status"] = "rejected"
                    state["reason"] = "Prospektiver Vergleich nicht besser als Referenz; Kandidat abgelehnt."
            else:
                state["status"] = "shadow"
                state["reason"] = "Eingefrorener Kandidat wird auf späteren, geschlossenen Kerzen geprüft."
    if not state.get("proposal") or state["proposal"].get("state") == "rejected":
        candidate = _choose(result, state.get("rejectedStrategies", []))
        if candidate:
            state["proposal"] = dict(strategy=candidate, state="shadow",
                 proposedOn=day, frozenAtBar=current_end, mode="SHADOW_ONLY",
                 source="historical-out-of-sample-discovery",
                 note="Nur neue spätere Kerzen zählen für die unabhängige Prüfung.")
            state["prospective"] = dict(sessions=0, trades=0, baselineTrades=0,
                candidateIndex=1.0, baselineIndex=1.0, lastEvaluatedBarAt=current_end)
            state["status"] = "shadow"
            state["reason"] = "Neuer Kandidat vorgeschlagen; noch keine prospektive Bestätigung."
        elif (state.get("proposal") or {}).get("state") != "rejected":
            state["status"] = "collecting"
            state["reason"] = "Noch kein Kandidat mit hinreichendem historischem Vorteil."
    state["lastResearchBarAt"] = current_end
    state["newIndependentEvidence"] = bool(
        state.get("prospective", {}).get("lastObservation", {}).get("day") == day)
    result["learningCycle"] = state
    return result


def maintenance(previous, day):
    """Audit the prior archive without treating a closed market as fresh learning."""
    prior = previous if isinstance(previous, dict) else {}
    cycle = _previous_cycle(prior) or _new_cycle()
    cycle.update(day=day, status="weekend-maintenance", newIndependentEvidence=False,
                 liveRuleChanged=False, productNetValidated=False, automaticOrder=False,
                 reason="Wochenend-Archiv geprüft. Keine neuen Kurse, Trades oder Freigaben behauptet.")
    return dict(version=strategy_lab.VERSION, mode="RESEARCH_ONLY",
        status="maintenance", approved=False, orderExecutionEnabled=False,
        affectsLiveSignals=False, brokerConnected=False,
        historicalInstrument=prior.get("historicalInstrument"),
        closedBars=prior.get("closedBars", 0), rangeMs=prior.get("rangeMs") or [None, None],
        folds=[], noNewEvidence=True, learningCycle=cycle,
        note="Archiv- und Sicherheitsprüfung am geschlossenen Markt; kein zusätzlicher Backtest.")
