"""Independent, read-only self-critique for Bob's frozen paper research.

Scores *paired, later observed reference-market* outcomes only. Never updates
signals, strategy parameters, product rankings, order buttons or broker state.
No fabricated probabilities, trade fills or product-specific EUR profits.
"""
import math

MIN_SESSIONS = 20
MIN_TRADES_EACH = 30


def _number(x, *, strictly_positive=False):
    return (type(x) in (float, int) and math.isfinite(x) and
            (x > 0 if strictly_positive else x >= 0))


def _valid_side(side):
    return (isinstance(side, dict) and
            type(side.get("trades")) is int and side["trades"] >= 0 and
            _number(side.get("index"), strictly_positive=True) and
            _number(side.get("maxDrawdownPct")) and side["maxDrawdownPct"] <= 100)


def review(cycle):
    """Return explanatory evidence and cautions; result is never permission."""
    base = dict(mode="RESEARCH_ONLY", referenceOnly=True,
                liveRuleChanged=False, automaticOrder=False,
                productNetValidated=False, actionable=False,
                status="insufficient", confidence="unrated",
                reason="Noch keine verlässliche unabhängige Vorwärtsprüfung.",
                comparedScenarios={}, recentWindows=None)

    if not isinstance(cycle, dict):
        return base
    p = cycle.get("prospective")
    if not isinstance(p, dict):
        return base
    sessions, trades, baseline_trades = (p.get("sessions"),
                                         p.get("trades"), p.get("baselineTrades"))
    if any(type(x) is not int or x < 0 for x in (sessions, trades, baseline_trades)):
        return {**base, "reason": "Ungültige Stichprobenzähler; Bewertung gesperrt."}
    if (cycle.get('status') == 'collecting' and cycle.get('proposal') is None
            and sessions == trades == baseline_trades == 0):
        return {**base, 'sessions':0, 'reason':'Noch kein Kandidat mit hinreichendem historischem Vorteil. Der gepaarte Vorwärts-Kostenvergleich wartet auf einen eingefrorenen Kandidaten; keine Ergebnisse erfunden.'}
    scenarios = p.get("costScenarios")
    if not isinstance(scenarios, dict) or set(scenarios) != {"standard", "stress"}:
        return {**base, "sessions": sessions, "reason": "Gepaarter Standard- und Kostenstresstest fehlt."}
    compared = {}
    for name in ("standard", "stress"):
        scenario = scenarios[name]
        if (not isinstance(scenario, dict) or
                not _valid_side(scenario.get("candidate")) or
                not _valid_side(scenario.get("baseline")) or
                not _number(scenario.get("costBpsPerSide"))):
            return {**base, "reason": "Kostenvergleich enthält unvollständige oder fehlerhafte Werte."}
        a, b = scenario["candidate"], scenario["baseline"]
        if a["trades"] > trades or b["trades"] > baseline_trades:
            return {**base, "reason": "Stichproben widersprechen den kumulierten Ergebnissen."}
        compared[name] = dict(
            candidateTrades=a["trades"], baselineTrades=b["trades"],
            candidateNetIndex=round(a["index"], 6),
            baselineNetIndex=round(b["index"], 6),
            relativeDifferencePct=round(100 * (a["index"] / b["index"] - 1), 3),
            candidateMaxDrawdownPct=round(a["maxDrawdownPct"], 3),
            baselineMaxDrawdownPct=round(b["maxDrawdownPct"], 3),
            advantage=(a["index"] > max(1., b["index"]) and
                       a["maxDrawdownPct"] <= b["maxDrawdownPct"])
        )
    recent = p.get("recentComparisons")
    last_ten = None
    if isinstance(recent, list) and len(recent) >= 10:
        tail = recent[-10:]
        # Positive/negative returns are both valid. Reject impossible evidence.
        valid = all(isinstance(r, dict) and
                    type(r.get("lastBarAt")) is int and
                    type(r.get("candidateNetReturnPct")) in (int, float) and
                    type(r.get("baselineNetReturnPct")) in (int, float) and
                    math.isfinite(r["candidateNetReturnPct"]) and
                    math.isfinite(r["baselineNetReturnPct"]) and
                    -100 <= r["candidateNetReturnPct"] <= 10000 and
                    -100 <= r["baselineNetReturnPct"] <= 10000
                    for r in tail)
        times = [r["lastBarAt"] for r in tail] if valid else []
        if valid and times == sorted(set(times)):
            wins = sum(r["candidateNetReturnPct"] > r["baselineNetReturnPct"] for r in tail)
            last_ten = dict(comparedIntervals=10, outperformingIntervals=wins,
                            underperformingOrEqualIntervals=10-wins,
                            note="Nur zehn abgegrenzte Vorwärts-Testfenster; keine Vorhersagegenauigkeit.")
    sufficient = (sessions >= MIN_SESSIONS and trades >= MIN_TRADES_EACH and
                  baseline_trades >= MIN_TRADES_EACH and
                  all(compared[s]["candidateTrades"] >= MIN_TRADES_EACH and
                      compared[s]["baselineTrades"] >= MIN_TRADES_EACH
                      for s in compared))
    robustness = all(v["advantage"] for v in compared.values())
    if not sufficient:
        status = "collecting"
        reason = "Zu wenige unabhängige Sitzungen oder abgeschlossene Vergleichs-Trades."
    elif robustness:
        status = "reference-promising"
        reason = "Vorteil in Standard- und Stresskosten belegt; Produktkosten und Live-Übertragbarkeit ungeprüft."
    else:
        status = "reference-unreliable"
        reason = "Kein robuster Vorteil in beiden Kostenannahmen; Strategie kritisch prüfen."
    if last_ten is not None and last_ten["underperformingOrEqualIntervals"] >= 7:
        status = "recently-unreliable"
        reason = "Mindestens sieben der letzten zehn gepaarten Testfenster ohne Vorteil; Vorsicht."
    return {**base, "status": status, "reason": reason,
            "confidence": "reference-only" if sufficient else "unrated",
            "sessions": sessions, "trades": trades,
            "baselineTrades": baseline_trades,
            "comparedScenarios": compared, "recentWindows": last_ten}
