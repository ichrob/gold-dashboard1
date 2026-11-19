"""Three KO-distance issuer-quote PAPER cohorts, always evidence-gated.

Independent of spot-proxy study and DEGIRO execution. Uses only the already
fetched, dated issuer EUR bid/ask and issuer KO terms, never chart/Swiss-DOTS
proxies or synthetic product fills. Missing issuer exit bid stays UNKNOWN.
"""
import copy
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION="gold-ko-distance-20261119-v1"
BANDS=("buffered-1p5-to-3","medium-3-to-6","wide-6-plus")
CAPITAL=1000.
FEE_EUR=1.
SLIPPAGE=.0005
MAX_EXPOSURE=.65
RISK_BUDGET=.01
MAX_HOLD_MINUTES=120
MINUTE=60000
ZURICH=ZoneInfo("Europe/Zurich")
NOTE=("Beobachtete Emittenten-EUR-Brief-/Geldkurse und aktuelle KO-Barriere. "
      "Drei virtuelle, getrennte 1.000-EUR-Kohorten: KO-Abstand bis 3 %, "
      "3–6 %, ab 6 %. Nur mit aktuellem verifizierten Preis-Paar, "
      "KO/Spot/Leverage-Nachweisen. Keine bestätigte DEGIRO-Ausführung, "
      "keine garantierten Stoppkurse und keine angenommene CHF-FX-Rate. "
      "Fehlende Ausstiegskurse bleiben unbekannt. Gebühren 1 EUR je "
      "Kauf/Verkauf plus 0,05 % Slippage je Seite als Beispiele.")


def number(x):
    return type(x) in (int,float) and math.isfinite(x)


def positive(x):
    return number(x) and x>0


def _band(distance):
    return (BANDS[0] if distance < 3 else
            BANDS[1] if distance < 6 else BANDS[2])


def _clock(value):
    from paper_simulation import stamp
    return stamp(value)


def _proof(choice,raw,market,now):
    import paper_simulation, paper_ko_guard
    if not isinstance(choice,dict) or not isinstance(raw,dict):
        return None
    isin=choice.get("isin")
    if not isinstance(isin,str) or not isin or choice.get("scope")!="XAU/USD":
        return None
    if (choice.get("estimated") or choice.get("indicative")
            or choice.get("direction")!=market.get("direction")):
        return None
    q=paper_simulation.fresh_quote(raw,now,isin)
    if (not q or q.get("currency")!="EUR"
            or raw.get("priceKind") in ("issuer-chart","calculated")):
        return None
    blocker,guard=paper_ko_guard.entry_reason(choice,raw,market,now)
    if blocker or not guard or guard.get("danger") or guard.get("crossed"):
        return None
    levproof=raw.get("leverageObservation") or {}
    levmodel=raw.get("leverageCalculation") or {}
    lev=(levproof.get("value") if levproof.get("current") is True
         else raw.get("leverage") if levmodel.get("available") is True
                       and levmodel.get("inputsFresh") is True else None)
    if not positive(lev) or lev>100 or not (positive(q.get("bid")) and positive(q.get("ask"))):
        return None
    if q["ask"] < q["bid"] or q["ask"]<=0:
        return None
    spread=100*(q["ask"]-q["bid"])/q["ask"]
    return dict(choice=choice,raw=raw,quote=q,guard=guard,
                leverage=lev,spreadPct=spread,
                band=_band(guard["distancePct"]))


def candidates(selection,quotes,market,now):
    """One ISIN per distance band with maximum current proof, no remote calls."""
    import stop_target_audit
    if (not market.get("ready") or not market.get("priceFresh")
            or market.get("direction") not in ("LONG","SHORT")
            or not stop_target_audit.valid_plan(market.get("plan"))):
        return {}
    choices=(selection or {}).get("choices") or []
    found={}
    for choice in choices[:20]:
        isin=choice.get("isin") if isinstance(choice,dict) else None
        p=_proof(choice,(quotes or {}).get(isin) or {},market,now)
        if p:
            band=p["band"]
            # Select minimal observed spread only within the same KO band;
            # resulting biases are audit limitations, not a market ranking.
            if band not in found or p["spreadPct"]<found[band]["spreadPct"]:
                found[band]=p
    return found


def seed(now):
    return dict(version=VERSION,startedAt=now,checkedAt=None,
      originalQuoteChecks=0,eligiblePricePairs=0,lastInput="not-observed",
      arms={band:dict(cashEur=CAPITAL,equityEur=CAPITAL,
         realizedModelNetEur=0.,position=None,started=0,closed=0,
         missingExitBid=0,unresolvedKo=0,
         lastSignal=None,lastBlock="waiting-issuer-evidence",
         lastEvidenceAt=None,lastExitAt=None,riskDay=None,dayStartEquity=CAPITAL,
         observedMaxDrawdownPct=0.,
         peakEur=CAPITAL,modelWins=0,modelLosses=0,
         exitCounts={}) for band in BANDS},realOrders=False)


def _monitor_market(market,p):
    # Existing KO verifier expects the FROZEN product direction, not the
    # current signal direction. This does not grant a new product approval.
    return {**market,"plan":{"unit":"USD/oz","direction":p["direction"]}}


def advance(old,market,selection,quotes,now):
    import paper_simulation,paper_ko_guard
    s=copy.deepcopy(old)
    if not number(now) or (number(s.get("checkedAt")) and now<=s["checkedAt"]):
        return s
    s["checkedAt"]=now
    valid_market=(isinstance(market,dict) and market.get("ready") is True
        and market.get("priceFresh") is True
        and positive(market.get("price")) and number(market.get("dataAt"))
        and 0<=now-market["dataAt"]<=MINUTE)
    if not valid_market:
        s["lastInput"]="original-gold-not-verified"
    else:
        s["lastInput"]="original-gold-observed"
    if valid_market:s["originalQuoteChecks"]+=1
    # One ranked product in each distance tier, only when source proof exists.
    options=candidates(selection,quotes,market,now) if valid_market else {}
    for band in BANDS:
        arm=s["arms"][band]
        p=arm.get("position")
        if p:
            raw=(quotes or {}).get(p["isin"]) or {}
            terminal=paper_ko_guard.terminal(raw,p["isin"])
            guard,why=paper_ko_guard.assess(
                 p,raw,_monitor_market(market,p),now) if valid_market else (None,"gold-not-fresh")
            if terminal or guard and guard["crossed"]:
                arm["lastBlock"]="ko-or-product-status-unresolved"
                if not p.get("settlementUnknown"):
                    arm["unresolvedKo"]+=1
                p["settlementUnknown"]=True
                arm["equityEur"]=None
                continue
            if p.get("settlementUnknown"):
                continue
            if valid_market and market["dataAt"]>p["lastSourceAt"]:
                sign=1 if p["direction"]=="LONG" else -1
                if (sign*(market["price"]-p["stop"])<=0
                    or sign*(market["price"]-p["target"])>=0
                    or (market.get("direction") in ("LONG","SHORT")
                        and market["direction"]!=p["direction"])
                    or now-p["entryAt"]>=MAX_HOLD_MINUTES*MINUTE
                    or datetime.fromtimestamp(now/1000,ZURICH).strftime("%H:%M")>="21:45"):
                    p["exitDue"]=p.get("exitDue") or now
                p["lastSourceAt"]=market["dataAt"]
                p["lastSpotObservedAt"]=now
            if p.get("exitDue"):
                quote=paper_simulation.fresh_quote(raw,now,p["isin"])
                bidAt=_clock((quote or {}).get("bidAt"))
                if (quote and guard and why is None and not guard["crossed"]
                        and positive(bidAt) and bidAt>=p["exitDue"]
                        and bidAt<=now):
                    proceeds=p["units"]*quote["bid"]*(1-SLIPPAGE)-FEE_EUR
                    result=proceeds-p["entryDebit"]
                    arm["cashEur"]+=proceeds
                    arm["realizedModelNetEur"]+=result
                    arm["closed"]+=1
                    arm["modelWins"]+=int(result>0)
                    arm["modelLosses"]+=int(result<0)
                    arm["exitCounts"]["issuer-bid-observed"]=arm["exitCounts"].get("issuer-bid-observed",0)+1
                    arm["equityEur"]=arm["cashEur"]
                    arm["peakEur"]=max(arm["peakEur"],arm["equityEur"])
                    arm["observedMaxDrawdownPct"]=max(arm["observedMaxDrawdownPct"],
                        100*(arm["peakEur"]-arm["equityEur"])/arm["peakEur"])
                    arm["position"]=None
                    arm["lastExitAt"]=now
                    arm["lastBlock"]="closed-issuer-bid-model-only"
                else:
                    arm["missingExitBid"]+=1
                    arm["lastBlock"]="dated-exit-bid-not-observed"
                    arm["equityEur"]=None
                continue
            # Mark only a FRESH aligned bid, never an assumed future fill.
            quote=paper_simulation.fresh_quote(raw,now,p["isin"])
            if quote and guard and why is None and not guard["crossed"]:
                marked=arm["cashEur"]+p["units"]*quote["bid"]*(1-SLIPPAGE)-FEE_EUR
                arm["equityEur"]=marked
                arm["peakEur"]=max(arm["peakEur"],marked)
                arm["observedMaxDrawdownPct"]=max(arm["observedMaxDrawdownPct"],
                    100*(arm["peakEur"]-marked)/arm["peakEur"])
            else:
                arm["equityEur"]=None
            continue
        if not valid_market or not options.get(band):
            arm["lastBlock"]="no-timestamped-issuer-ko-pair"
            continue
        clock=datetime.fromtimestamp(now/1000,ZURICH)
        if clock.weekday()>=5 or not (8<=clock.hour<21) or not (market.get("session") or {}).get("entryAllowed"):
            arm["lastBlock"]="session-closed"
            continue
        today=clock.date().isoformat()
        if arm.get("riskDay")!=today:
            arm["riskDay"]=today
            arm["dayStartEquity"]=arm["cashEur"]
        if arm["cashEur"]<=.97*arm["dayStartEquity"]:
            arm["lastBlock"]="daily-loss-limit"
            continue
        if number(arm.get("lastExitAt")) and now-arm["lastExitAt"]<3*MINUTE:
            arm["lastBlock"]="cooldown"
            continue
        signal=market.get("analysisBarAt")
        if not number(signal) or signal==arm.get("lastSignal"):
            arm["lastBlock"]="same-or-missing-original-signal"
            continue
        p=options[band];choice=p["choice"];q=p["quote"]
        plan=market["plan"]
        risk=abs(plan["entry"]-plan["stop"])
        if not positive(risk) or not positive(plan["entry"]):
            arm["lastBlock"]="stop-risk-unavailable"
            continue
        # Same 1% account risk budget across different ACTUAL issuer leverage;
        # no borrowing, max 65% deployed at a time, whole product units only.
        risk_frac=p["leverage"]*risk/plan["entry"]
        budget=min(arm["cashEur"]*MAX_EXPOSURE,
                   arm["cashEur"]*RISK_BUDGET/risk_frac) if positive(risk_frac) else 0.
        units=math.floor((budget-FEE_EUR)/(q["ask"]*(1+SLIPPAGE)))
        if units<1 or units>100000:
            arm["lastBlock"]="insufficient-capital"
            continue
        debit=units*q["ask"]*(1+SLIPPAGE)+FEE_EUR
        if debit>arm["cashEur"]:
            arm["lastBlock"]="insufficient-capital"
            continue
        arm["cashEur"]-=debit
        arm["equityEur"]=None  # not known until an aligned subsequent issuer bid
        arm["started"]+=1
        arm["lastSignal"]=signal
        arm["lastEvidenceAt"]=now
        arm["lastBlock"]="observed-model-entry"
        arm["position"]=dict(isin=choice["isin"],direction=choice["direction"],
            scope="XAU/USD",entryAt=now,lastSourceAt=market["dataAt"],
            lastSpotObservedAt=now,entryQuoteAt=_clock(q.get("askAt")),
            entryAsk=q["ask"],entryDebit=debit,units=units,
            stop=plan["stop"],target=plan["target"],entrySpot=market["price"],
            leverage=p["leverage"],entryKoEvidence=p["guard"],
            realOrders=False,brokerExecutionVerified=False)
        s["eligiblePricePairs"]+=1
    return s


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_ko_distance_state
        (id TEXT PRIMARY KEY,payload JSONB NOT NULL)""")


def tick(conn,market,selection,quotes,now):
    row=conn.execute("SELECT payload FROM bob_ko_distance_state WHERE id=%s FOR UPDATE",
        (VERSION,)).fetchone()
    state=advance(row[0] if row else seed(now),market,selection,quotes,now)
    conn.execute("""INSERT INTO bob_ko_distance_state VALUES(%s,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload""",
        (VERSION,json.dumps(state,allow_nan=False)))


def report(conn):
    row=conn.execute("SELECT payload FROM bob_ko_distance_state WHERE id=%s",
                     (VERSION,)).fetchone()
    if not row:
        return dict(status="awaiting-first-worker-check",readOnly=True,
            realOrders=False,productReturnVerified=False)
    state=row[0];arms=[]
    for tier in BANDS:
        a=state["arms"][tier]
        arms.append(dict(koTier=tier,started=a["started"],closed=a["closed"],
           positionOpen=bool(a["position"]),missingExitBid=a["missingExitBid"],
           unresolvedKo=a["unresolvedKo"],lastBlock=a["lastBlock"],
           initialEur=CAPITAL,modelCashEur=round(a["cashEur"],3),
           modelEquityEur=round(a["equityEur"],3)
               if number(a.get("equityEur")) else None,
           modelRealizedEur=round(a["realizedModelNetEur"],3),
           modelWins=a["modelWins"],modelLosses=a["modelLosses"],
           observedMaxDrawdownPct=round(a["observedMaxDrawdownPct"],3)))
    return dict(status="collecting",version=VERSION,
        checkedAt=state["checkedAt"],arms=arms,
        originalQuoteChecks=state["originalQuoteChecks"],
        eligiblePricePairs=state["eligiblePricePairs"],
        lastInput=state["lastInput"],readOnly=True,realOrders=False,
        productReturnVerified=False,brokerExecutionVerified=False,
        strategyWinnerConfirmed=False,noHistoricalBackfill=True,note=NOTE)
