"""Bob's rolling, *research-only* learning loop.

Historical trials suggest shadow candidates. A candidate is frozen before later
closed candles are scored. Product execution costs, observed DEGIRO fills, and
live-rule promotion are deliberately out of scope: no price evidence is invented.
All state is embedded in the daily Postgres strategy report (restart-safe).
"""
import copy
import math

import strategy_lab
import research_self_review

VERSION = "bob-rolling-shadow-v3-latest12"
MIN_FOLDS = 3
MIN_HISTORIC_TRADES = 30
MIN_FORWARD_SESSIONS = 20
MIN_FORWARD_TRADES = 30
# Logistic weights would need separately frozen coefficients to be prospective.
SHADOWABLE = ("trend-strict", "trend-tight", "breakout", "breakout-confirmed", "mean-revert")


def _finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def _previous_cycle(previous):
    value = previous.get("learningCycle") if isinstance(previous, dict) else None
    return copy.deepcopy(value) if isinstance(value, dict) and value.get("version") == VERSION else {}


def _new_cycle():
    return dict(version=VERSION, status="collecting", proposal=None,
                rejectedStrategies=[], completedStrategies=[], completed=[], prospective=dict(sessions=0, trades=0,
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


def _forward(bars, previous_bar, candidate, protocol=None):
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
    protocol = protocol or frozen_protocol()
    if protocol != frozen_protocol():
        return None
    f = strategy_lab.features(normalized)
    scenarios = {}
    for name,cost in protocol['costBpsPerSide'].items():
        scenarios[name] = dict(costBpsPerSide=cost,
            baseline=strategy_lab.score(normalized,f,'baseline',None,start,len(normalized),cost),
            candidate=strategy_lab.score(normalized,f,candidate,None,start,len(normalized),cost))
    return dict(**scenarios['standard'], scenarios=scenarios,
                lastBarAt=normalized[-1]['openTime'],newBars=len(normalized)-start)


def frozen_protocol():
    return dict(version='paired-reference-cost-v1',engineVersion=strategy_lab.VERSION,
        horizonBars=strategy_lab.HORIZON,baseline='baseline',
        costBpsPerSide=dict(standard=strategy_lab.COST_BPS_PER_SIDE,
                            stress=3*strategy_lab.COST_BPS_PER_SIDE),
        minSessions=MIN_FORWARD_SESSIONS,minTradesEach=MIN_FORWARD_TRADES,
        costKind='assumed-reference-fee-and-slippage',productNetValidated=False)


def accumulate_scenarios(progress, observation):
    for name, scores in observation['scenarios'].items():
        group = progress.setdefault('costScenarios',{}).setdefault(name,dict(costBpsPerSide=scores['costBpsPerSide']))
        for side in ('candidate','baseline'):
            stats = group.setdefault(side,dict(index=1.,peak=1.,maxDrawdownPct=0.,trades=0))
            score = scores[side]
            before = stats['index']
            stats['maxDrawdownPct'] = max(stats['maxDrawdownPct'],score['maxDrawdownPct'],
                100*(1-before*score['minEquityIndex']/stats['peak']))
            stats['peak'] = max(stats['peak'],before*score['maxEquityIndex'])
            stats['index'] = before*(1+score['netReturnPct']/100)
            stats['trades'] += score['trades']


def robust_advantage(progress):
    groups = progress.get('costScenarios') or {}
    return set(groups)=={'standard','stress'} and all(
        g['candidate']['trades']>=MIN_FORWARD_TRADES and g['baseline']['trades']>=MIN_FORWARD_TRADES
        and g['candidate']['index']>max(1.,g['baseline']['index'])
        and g['candidate']['maxDrawdownPct']<=g['baseline']['maxDrawdownPct']
        for g in groups.values())


def enrich(report, bars, previous=None, *, day):
    """Append transparent suggestions and frozen prospective outcomes to a report.

    This cannot change production market signals, product selection or broker
    state. Nothing is promoted from hypothetical spot performance.
    """
    result = copy.deepcopy(report)
    old = _previous_cycle(previous)
    state = old or _new_cycle()
    if not old and isinstance(previous,dict) and previous.get('learningCycle'):
        prior = previous['learningCycle']
        state['previousProtocolArchive'] = dict(version=prior.get('version'),
            proposal=prior.get('proposal'),prospective=prior.get('prospective'),
            note='Vorheriges Protokoll archiviert; zählt nicht zum neuen Kostenvergleich.')
    state["experiments"] = list(strategy_lab.STRATEGIES)
    state["day"] = day
    state["liveRuleChanged"] = False
    state["productNetValidated"] = False
    state["automaticOrder"] = False
    current_end = (result.get("rangeMs") or [None, None])[-1]
    previous_end = state.get("prospective", {}).get("lastEvaluatedBarAt")
    if previous_end is None:
        previous_end = (previous.get("rangeMs") or [None, None])[-1] if isinstance(previous, dict) else None
    new_observation_accepted = False
    proposal = state.get("proposal")
    if proposal and proposal.get("state") == "shadow":
        if (previous and previous.get("historicalInstrument") and
                previous["historicalInstrument"] != result.get("historicalInstrument")):
            state["status"] = "blocked"
            state["reason"] = "Referenzinstrument gewechselt; kein historischer Vergleich erlaubt."
        elif proposal.get("protocol") != frozen_protocol():
            state["status"] = "blocked"
            state["reason"] = "Testprotokoll verändert; bisherige und neue Ergebnisse werden nicht vermischt."
        elif result.get("status") == "evaluated":
            observation = _forward(bars, previous_end, proposal.get("strategy"), proposal.get("protocol"))
            if observation:
                new_observation_accepted = True
                p = state["prospective"]
                accumulate_scenarios(p, observation)
                a = observation["candidate"]
                b = observation["baseline"]
                if a["trades"] or b["trades"]:
                    if proposal.get("lastIndependentDay") != day:
                        p["sessions"] += 1
                    p["trades"] += a["trades"]
                    p["baselineTrades"] += b["trades"]
                    p["candidateIndex"] = round(p["candidateIndex"] * (1+a["netReturnPct"]/100), 10)
                    p["baselineIndex"] = round(p["baselineIndex"] * (1+b["netReturnPct"]/100), 10)
                p["lastEvaluatedBarAt"] = observation["lastBarAt"]
                p["lastObservation"] = dict(day=day, newBars=observation["newBars"],
                    candidate=a, baseline=b)
                # Compare truly subsequent, non-overlapping reference windows.
                # Same-day morning/evening snapshots can add new windows but
                # duplicates/retries at the same closed bar never double-count.
                if a["trades"] > 0 and b["trades"] > 0:
                    recent = p.setdefault("recentComparisons", [])
                    if (not recent or recent[-1].get("lastBarAt") != observation["lastBarAt"]):
                        recent.append(dict(lastBarAt=observation["lastBarAt"], day=day,
                            candidateNetReturnPct=a["netReturnPct"],
                            baselineNetReturnPct=b["netReturnPct"]))
                        p["recentComparisons"] = recent[-10:]
                proposal["lastIndependentDay"] = day
            if (state["prospective"]["sessions"] >= MIN_FORWARD_SESSIONS and
                    state["prospective"]["trades"] >= MIN_FORWARD_TRADES and
                    state["prospective"]["baselineTrades"] >= MIN_FORWARD_TRADES):
                p = state["prospective"]
                if robust_advantage(p):
                    proposal["state"] = "paper-required"
                    state["status"] = "paper-required"
                    state["reason"] = ("Historische und spätere Referenztests positiv. "
                       "Unabhängige DEGIRO-EUR-Produkt- und Kostenprüfungen fehlen: keine Live-Übernahme.")
                else:
                    proposal["state"] = "rejected"
                    state["rejectedStrategies"] = (state.get("rejectedStrategies", [])
                                                  + [proposal["strategy"]])[-len(SHADOWABLE):]
                    state["status"] = "rejected"
                    state["reason"] = "Kein robuster Vorteil bei Standard-/Stresskosten und Drawdown; Kandidat abgelehnt."
            else:
                state["status"] = "shadow"
                state["reason"] = "Eingefrorener Kandidat wird auf späteren, geschlossenen Kerzen geprüft."
    # Completed candidates remain in the audit log; later trading days can
    # research another candidate instead of getting stuck after one trial.
    finished = state.get("proposal") or {}
    if finished.get("state") in ("paper-required", "rejected"):
        signature = (finished.get("strategy"), finished.get("proposedOn"))
        if not any((x.get("strategy"), x.get("proposedOn")) == signature
                   for x in state.get("completed", [])):
            state.setdefault("completed", []).append(dict(
                strategy=finished.get("strategy"), proposedOn=finished.get("proposedOn"),
                finishedOn=day, result=finished.get("state"),
                prospective=copy.deepcopy(state.get("prospective", {}))))
            state["completed"] = state["completed"][-12:]
        if finished.get("state") == "paper-required":
            seen = state.setdefault("completedStrategies", [])
            if finished.get("strategy") not in seen:
                seen.append(finished["strategy"])
    if not state.get("proposal") or state["proposal"].get("state") in ("rejected", "paper-required"):
        excluded = state.get("rejectedStrategies", []) + state.get("completedStrategies", [])
        candidate = _choose(result, excluded)
        if candidate:
            state["proposal"] = dict(strategy=candidate, state="shadow",
                 proposedOn=day, frozenAtBar=current_end, mode="SHADOW_ONLY",protocol=frozen_protocol(),
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
    state["newIndependentEvidence"] = new_observation_accepted
    # Read-only critique. This is NOT an alternate live market signal.
    state["selfReview"] = research_self_review.review(state)
    result["learningCycle"] = state
    return result


def maintenance(previous, day):
    """Audit the prior archive without treating a closed market as fresh learning."""
    prior = previous if isinstance(previous, dict) else {}
    cycle = _previous_cycle(prior) or _new_cycle()
    archive_verified = (prior.get("mode") == "RESEARCH_ONLY" and
                        prior.get("version") == strategy_lab.VERSION and
                        prior.get("approved") is False and
                        prior.get("orderExecutionEnabled") is False and
                        prior.get("affectsLiveSignals") is False and
                        isinstance(prior.get("rangeMs"), list) and
                        len(prior["rangeMs"]) == 2 and
                        _finite(prior["rangeMs"][1]) and
                        isinstance(prior.get("closedBars"), int) and prior["closedBars"] > 0)
    cycle.update(day=day,
                 status="weekend-maintenance" if archive_verified else "archive-missing",
                 newIndependentEvidence=False,
                 liveRuleChanged=False, productNetValidated=False, automaticOrder=False,
                 reason=("Wochenend-Archiv vorhanden und Sperrstatus überprüft."
                         if archive_verified else
                         "Kein ausreichend belegtes vorheriges Archiv; Forschung bleibt gesperrt.") +
                        " Keine neuen Kurse, Trades oder Freigaben behauptet.")
    cycle["selfReview"] = research_self_review.review(cycle)
    return dict(version=strategy_lab.VERSION, mode="RESEARCH_ONLY",
        status="maintenance", approved=False, orderExecutionEnabled=False,
        affectsLiveSignals=False, brokerConnected=False,
        historicalInstrument=prior.get("historicalInstrument"),
        closedBars=prior.get("closedBars", 0), rangeMs=prior.get("rangeMs") or [None, None],
        folds=[], noNewEvidence=True, archiveVerified=archive_verified, learningCycle=cycle,
        note="Archiv- und Sicherheitsprüfung am geschlossenen Markt; kein zusätzlicher Backtest.")
