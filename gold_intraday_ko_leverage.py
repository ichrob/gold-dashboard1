"""Independent prospective KO-backed leverage comparison, PAPER ONLY.

Reuses the strict issuer EUR quote, dated XAU/USD KO and calculated/provider
leverage proof from gold_ko_distance_cohorts. Never creates an order, a DEGIRO
execution quote, an estimated product fill or a retrospectively selected trade.
Two independent arms (balanced vs highest safe leverage) per KO distance band.
The former original three-band cohort and all regular simulations remain intact.
"""
import copy
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import gold_ko_distance_cohorts as cohorts

VERSION = "gold-intraday-ko-leverage-20261120-v1"
POLICIES = ("balanced", "high-safe")
MAX_LEVERAGE = 30.0   # Research cap, not a recommendation.
KO_MAX_LOSS_FRACTION = .03  # Full stake and entry fees may be lost at KO.
STOP_RISK_FRACTION = cohorts.RISK_BUDGET
MAX_HOLD_MINUTES = 300
MIN_KO_STOP_GAP_PCT = .005
MIN_KO_GUARD_SURPLUS_PCT = .5
TARGET_COST_BUFFER_EUR = 0.0
NOTE = (
    "Zwei getrennte Original-Emittenten-Papiergruppen pro KO-Abstandsklasse: "
    "ausgewogener Hebel gegen hoechsten belegten sicheren Hebel bis 30. "
    "Groesserer Hebel nur bei belegtem KO-Abstand hinter dem Gold-Stop, "
    "frischen EUR-Geld/Brief- und Emittentenbedingungen, realer Stueckzahl "
    "und maximal 1 Prozent kalkuliertem Stop-Risiko sowie maximal 3 Prozent "
    "eingesetztem Kapital bei moeglichem Totalverlust durch KO. "
    "Stop-Nachziehen wird nie gelockert; Ausstieg bei Stop, Ziel, "
    "Gegenrichtung oder bis spaetestens 5 Stunden/Handelsschluss. "
    "Nicht beobachtete Geldkurse bleiben UNBEKANNT; keine Handelsausfuehrung, "
    "keine belegte Produktnettorendite und keine Gewinngarantie."
)


def _safe(item, market, cash):
    """Check issuer KO *beyond* planned stop and a realizable whole-unit stake."""
    if not isinstance(item, dict) or not isinstance(market, dict):
        return False
    guard = item.get("guard") or {}
    plan = market.get("plan") or {}
    spot = market.get("price")
    atr = market.get("atr")
    if (market.get("direction") not in ("LONG", "SHORT")
            or not all(cohorts.positive(v) for v in
                       (spot, plan.get("entry"), plan.get("stop"),
                        plan.get("target"), guard.get("barrierUsd"),
                        item.get("leverage"), cash))
            or item["leverage"] > MAX_LEVERAGE
            or not cohorts.number(guard.get("distancePct"))
            or not cohorts.number(guard.get("protectiveDistancePct"))
            or guard["distancePct"] <
                 guard["protectiveDistancePct"]+MIN_KO_GUARD_SURPLUS_PCT):
        return False
    sign = 1 if market["direction"] == "LONG" else -1
    if (not 0 <= abs(plan["entry"]-spot) <= .01
            or sign*(spot-plan["stop"]) <= 0
            or sign*(plan["target"]-spot) <= 0
            or sign*(plan["stop"]-guard["barrierUsd"]) <=
                max(MIN_KO_STOP_GAP_PCT*spot, .5*atr if cohorts.positive(atr) else 0)):
        return False
    q = item.get("quote") or {}
    ask, bid = q.get("ask"), q.get("bid")
    if not (cohorts.positive(ask) and cohorts.positive(bid) and bid <= ask):
        return False
    # Risk sized on the modeled stop but exposure capped AGAIN to bound the
    # actual worst-case full-premium KO loss. This remains a modeling assumption:
    # KO gaps and execution quality can still produce larger trading losses.
    loss_fraction = item["leverage"] * abs(spot-plan["stop"]) / spot
    if not cohorts.positive(loss_fraction):
        return False
    budget = min(cash*cohorts.MAX_EXPOSURE,
                 cash*STOP_RISK_FRACTION/loss_fraction,
                 cash*KO_MAX_LOSS_FRACTION)
    units = math.floor((budget-cohorts.FEE_EUR)/
                       (ask*(1+cohorts.SLIPPAGE)))
    if not 1 <= units <= 100000:
        return False
    debit = units*ask*(1+cohorts.SLIPPAGE)+cohorts.FEE_EUR
    if debit > cash*KO_MAX_LOSS_FRACTION:
        return False
    # The target must at least cover ACTUAL observed spread, fees and assumed
    # slippage in the model, not just show a large leveraged spot percentage.
    theoretical_bid = bid+ask*item["leverage"]*sign*(
        plan["target"]-spot)/spot
    proceeds = units*theoretical_bid*(1-cohorts.SLIPPAGE)-cohorts.FEE_EUR
    return proceeds-debit > TARGET_COST_BUFFER_EUR


def _choices(selection, quotes, market, now, arm, policy):
    import stop_target_audit
    if (not isinstance(selection, dict)
            or (market.get("entryTimingGate") or {}).get("allowed") is not True
            or market.get("ready") is not True
            or market.get("priceFresh") is not True
            or market.get("direction") not in ("LONG", "SHORT")
            or not stop_target_audit.valid_plan(market.get("plan"))):
        return {"choices":[]}, 0
    seen = set()
    found = {band:[] for band in cohorts.BANDS}
    # Research candidates retain *more* of the validated selection list than
    # the UI top-3. No arbitrary external ISINs are searched or added.
    candidates = list(selection.get("researchCandidates") or []) + list(
        selection.get("choices") or [])
    for candidate in candidates[:24]:
        if not isinstance(candidate, dict):
            continue
        isin = candidate.get("isin")
        if not isinstance(isin, str) or isin in seen:
            continue
        seen.add(isin)
        proof = cohorts._proof(candidate,(quotes or {}).get(isin) or {},market,now)
        if not proof or proof["band"] not in found:
            continue
        cash = (arm["arms"][proof["band"]].get("cashEur")
                if isinstance(arm.get("arms"),dict)
                else cohorts.CAPITAL)
        if _safe(proof,market,cash):
            found[proof["band"]].append(proof)
    chosen = []
    for band in cohorts.BANDS:
        entries = found[band]
        if entries:
            if policy == "high-safe":
                ranked = sorted(entries,key=lambda x:(-x["leverage"],
                    -x["guard"]["distancePct"],x["choice"]["isin"]))
            else:
                ranked = sorted(entries,key=lambda x:(
                    abs(x["leverage"]-5.0),-x["guard"]["distancePct"],
                    x["choice"]["isin"]))
            chosen.append(ranked[0]["choice"])
    return {"choices":chosen}, sum(map(len,found.values()))


def seed(now):
    return dict(version=VERSION,startedAt=now,checkedAt=None,realOrders=False,
        opportunities=0,lastOpportunityKey=None,eligibleOriginalProducts=0,
        policies={name:cohorts.seed(now) for name in POLICIES},
        selectionEvidence={name:dict(eligible=0,selected=0)
                           for name in POLICIES})


def advance(old,market,selection,quotes,now):
    if not cohorts.number(now) or (cohorts.number(old.get("checkedAt"))
                                   and now<=old["checkedAt"]):
        return copy.deepcopy(old)
    result=copy.deepcopy(old)
    result["checkedAt"]=now
    if (isinstance(market, dict)
            and market.get("ready") is True
            and market.get("direction") in ("LONG","SHORT")
            and (market.get("entryTimingGate") or {}).get("allowed") is True):
        key=str((market.get("ruleVersion"),market.get("analysisBarAt"),
                 market.get("direction")))
        if cohorts.number(market.get("analysisBarAt")) and key!=result.get("lastOpportunityKey"):
            result["opportunities"]+=1
            result["lastOpportunityKey"]=key
    for policy in POLICIES:
        account=result["policies"][policy]
        chosen,eligible=_choices(selection,quotes,market,now,account,policy)
        result["selectionEvidence"][policy]=dict(
            eligible=eligible,selected=len(chosen["choices"]))
        result["eligibleOriginalProducts"]+=eligible
        # Original golden cohorts stay untouched. New policies have their own
        # independently seeded 3 x EUR 1000 paper ledgers, never broker funds.
        result["policies"][policy]=cohorts.advance(
            account,market,chosen,quotes,now,
            ko_loss_cap=KO_MAX_LOSS_FRACTION,
            hold_minutes=MAX_HOLD_MINUTES,
            trail=True)
    return result


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_intraday_ko_leverage
        (id TEXT PRIMARY KEY,payload JSONB NOT NULL)""")


def tick(conn,market,selection,quotes,now):
    row=conn.execute("SELECT payload FROM bob_intraday_ko_leverage WHERE id=%s FOR UPDATE",
                     (VERSION,)).fetchone()
    state=advance(row[0] if row else seed(now),market,selection,quotes,now)
    conn.execute("""INSERT INTO bob_intraday_ko_leverage(id,payload)
        VALUES(%s,%s::jsonb) ON CONFLICT(id) DO UPDATE
        SET payload=EXCLUDED.payload""",
        (VERSION,json.dumps(state,allow_nan=False)))


def report(conn):
    row=conn.execute("SELECT payload FROM bob_intraday_ko_leverage WHERE id=%s",
                     (VERSION,)).fetchone()
    if not row:
        return dict(status="awaiting-first-worker-check",readOnly=True,
                    realOrders=False,productReturnVerified=False)
    state=row[0]
    rows=[]
    for policy in POLICIES:
        data=state["policies"][policy]
        for band in cohorts.BANDS:
            arm=data["arms"][band]
            position=arm.get("position") or {}
            eq=arm.get("equityEur")
            rows.append(dict(policy=policy,koTier=band,
                started=arm["started"],closed=arm["closed"],
                open=bool(position),activeLeverage=position.get("leverage"),
                trailingStopUpdates=position.get("trailingStopUpdates",0),
                observedIssuerPairs=data["eligiblePricePairs"],
                unknownIssuerExitBids=arm["missingExitBid"],
                unresolvedKO=arm["unresolvedKo"],
                lastBlock=arm["lastBlock"],initialEur=cohorts.CAPITAL,
                modelCashEur=round(arm["cashEur"],3),
                modelEquityEur=round(eq,3) if cohorts.number(eq) else None,
                modelRealizedEur=round(arm["realizedModelNetEur"],3),
                wins=arm["modelWins"],losses=arm["modelLosses"],
                drawdownPct=round(arm["observedMaxDrawdownPct"],3)))
    return dict(version=VERSION,status="collecting",checkedAt=state["checkedAt"],
                studies=rows,policyCount=len(POLICIES),armCount=len(rows),
                opportunities=state["opportunities"],
                evidence=state["selectionEvidence"],
                highestModeledLeverage=MAX_LEVERAGE,
                maxWorstCaseKoStakePct=100*KO_MAX_LOSS_FRACTION,
                stopBudgetPct=100*STOP_RISK_FRACTION,
                maximumHoldingMinutes=MAX_HOLD_MINUTES,
                realOrders=False,readOnly=True,productReturnVerified=False,
                brokerExecutionVerified=False,strategyWinnerConfirmed=False,
                liveRulesChanged=False,noHistoricalBackfill=True,note=NOTE)
