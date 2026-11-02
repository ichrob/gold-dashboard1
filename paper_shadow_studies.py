"""Three independent forward-only, fully journalled research studies.

No brokerage connection, market fetch, provider retries, synthetic fills or
changes to live Bob signals. Everything is sampled from the existing paper
worker's exact original bundle and already validated product quotes.
"""
import copy
import json
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

STUDIES = ("regime-routing", "wait-vs-enter", "product-e2e")
VERSION = "bob-shadow-studies-v1"
HORIZON_MS = 60 * 60000
TOLERANCE_MS = 60000
ZURICH = ZoneInfo("Europe/Zurich")
SIGNAL_COST_PCT = 0.16   # Illustrative round-trip XAU benchmark, not DEGIRO costs.
PRODUCT_FEE_EUR = 1.0
PRODUCT_SLIPPAGE = 0.0005  # Assumption per side, separate from observed spread.


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def positive(value):
    return number(value) and value > 0


def seed(study, now):
    return dict(version=VERSION, study=study, startedAt=now, checkedAt=None,
                status="collecting", realOrders=False, lastBarAt=None,
                casesStarted=0, casesPriced=0, casesInconclusive=0,
                casesRejected=0, openCases=[], capital=1000.0, cash=1000.0,
                position=None, profit=0.0, observedMaxDrawdown=0.0,
                peak=1000.0, eventCount=0)


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_shadow_study_control (
        study TEXT PRIMARY KEY, payload JSONB NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_shadow_study_events (
        study TEXT NOT NULL, at TIMESTAMPTZ NOT NULL,
        cycle BIGINT NOT NULL, payload JSONB NOT NULL,
        PRIMARY KEY(study,cycle))""")
    conn.execute("""CREATE INDEX IF NOT EXISTS bob_shadow_study_events_recent
        ON bob_shadow_study_events(study,at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_shadow_study_cases (
        id TEXT PRIMARY KEY, study TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL,
        closed_at TIMESTAMPTZ, payload JSONB NOT NULL)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS bob_shadow_study_cases_recent
        ON bob_shadow_study_cases(study,started_at DESC)""")
    now=int(time.time()*1000)
    for study in STUDIES:
        conn.execute("""INSERT INTO bob_shadow_study_control(study,payload)
            VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING""",
            (study,json.dumps(seed(study,now))))


def original_input(bundle, market, now):
    """Assert that the exact market spot is the original source observation.

    A future or estimated clock, absent closed 15m bar, or a different source
    never becomes a valid study price merely because the evaluator is ready.
    """
    from paper_simulation import stamp
    spots=(bundle or {}).get("spots") or {}
    history=(bundle or {}).get("history") or {}
    bars=(history.get("bars_by_tf") or {}).get("15m") or []
    at=stamp(spots.get("spot_price_as_of"))
    price=market.get("price")
    data_at=market.get("dataAt")
    analysis_at=market.get("analysisBarAt")
    verified_bars=[b for b in bars if isinstance(b,dict)
                   and number(b.get("openTime"))
                   and b.get("isOpen") is not True
                   and b.get("providerIsOpen") is not True
                   and b.get("estimated") is not True]
    matching=any(b["openTime"] == analysis_at for b in verified_bars)
    good=(spots.get("is_genuine_xauusd_spot") is True
          and spots.get("xaus_is_spot") is True
          and market.get("ready") is True
          and market.get("priceFresh") is True
          and positive(price) and number(data_at) and number(at)
          and abs(data_at-at)<=2000 and 0<=now-at<=60000
          and matching)
    return dict(verified=bool(good),sourceAt=at if number(at) else None,
        analysisBarAt=analysis_at if number(analysis_at) else None,
        price=price if positive(price) else None,closed15mMatched=matching,
        reason=None if good else "original-spot-or-15m-evidence-unverified")


def regime_decision(market, input_quality):
    import ranking_regimes
    regime=ranking_regimes.classify(market)
    direction=market.get("direction")
    approved=direction in ("LONG","SHORT") and input_quality["verified"]
    # Two precommitted hypotheses on the same observed, prospective clock.
    baseline=direction if approved else "ABWARTEN"
    gated=(direction if approved and regime["trend"]=="strong-trend"
           and regime["volatility"] in ("normal","high") else "ABWARTEN")
    return dict(kind="paired-regime-route",regime=regime,baseline=baseline,
                candidate=gated,reason="historical-regime-descriptive-gate-v1")


def wait_decision(market, input_quality):
    neutral=market.get("direction")=="NEUTRAL"
    frames=((market.get("dmi") or {}).get("frames") or {})
    short=(frames.get("5m") or {}).get("direction")
    direction=short if short in ("LONG","SHORT") and neutral and input_quality["verified"] else None
    return dict(kind="paired-wait-study",baseline="ABWARTEN",
                candidate=direction or "ABWARTEN",
                reason=("5m-DMI-counterfactual-only" if direction
                        else "no-neutral-contrarian-scenario"),
                liveApproval=False)


def price_signal_case(case, observed, now):
    """Only an original *later* source quote within the frozen horizon wins."""
    target=case["entryAt"]+HORIZON_MS
    at=observed.get("sourceAt")
    if number(at) and observed.get("verified") and target<=at<=target+TOLERANCE_MS:
        sign=1 if case["candidate"]=="LONG" else -1
        movement=100*sign*(observed["price"]/case["entryPrice"]-1)
        candidate=movement-SIGNAL_COST_PCT
        baseline=0.0 if case["study"]=="wait-vs-enter" else (
            movement-SIGNAL_COST_PCT if case["baseline"] in ("LONG","SHORT") else 0.0)
        if case["study"]=="regime-routing" and case["candidate"]=="ABWARTEN":
            candidate=0.0
        return dict(status="priced-reference-spot-only",pricedAt=at,
                    exitPrice=observed["price"],baselinePct=baseline,
                    candidatePct=candidate,
                    differencePct=candidate-baseline,
                    costAssumptionPct=SIGNAL_COST_PCT,
                    executableProductReturnVerified=False)
    if now>target+TOLERANCE_MS:
        return dict(status="inconclusive-original-followup-missing",
                    pricedAt=None,exitPrice=None,baselinePct=None,
                    candidatePct=None,differencePct=None)
    return None


def write_case(conn, item, opened):
    conn.execute("""INSERT INTO bob_shadow_study_cases
        (id,study,started_at,closed_at,payload)
        VALUES(%s,%s,to_timestamp(%s/1000.0),%s,%s::jsonb)
        ON CONFLICT DO NOTHING""",
        (item["id"],item["study"],item["entryAt"],
         None if opened else datetime.fromtimestamp(item["closedAt"]/1000,ZURICH),
         json.dumps(item,allow_nan=False)))


def close_case(conn,item,now):
    conn.execute("""UPDATE bob_shadow_study_cases
        SET closed_at=to_timestamp(%s/1000.0),payload=%s::jsonb
        WHERE id=%s AND closed_at IS NULL""",
        (now,json.dumps(item,allow_nan=False),item["id"]))


def update_signal_study(conn,control,study,decision,quality,now):
    pending=[]
    for item in control.get("openCases") or []:
        outcome=price_signal_case(item,quality,now)
        if outcome is None:
            pending.append(item)
            continue
        item={**item,**outcome,closedAt=now}
        close_case(conn,item,now)
        control["casesPriced" if item["status"]=="priced-reference-spot-only"
                else "casesInconclusive"]+=1
    control["openCases"]=pending
    bar=quality.get("analysisBarAt")
    if (quality["verified"] and number(bar)
            and bar!=control.get("lastBarAt")):
        control["lastBarAt"]=bar
        # No trade at all if both models agree on ABWARTEN.
        if decision["candidate"] in ("LONG","SHORT") or decision.get("baseline") in ("LONG","SHORT"):
            item=dict(id=f"{study}:{int(bar)}",study=study,entryAt=quality["sourceAt"],
                      barAt=bar,entryPrice=quality["price"],
                      baseline=decision["baseline"],candidate=decision["candidate"],
                      originalInput=copy.deepcopy(quality),
                      entryDecision=copy.deepcopy(decision),status="pending-60m")
            write_case(conn,item,True)
            control["openCases"].append(item)
            control["casesStarted"]+=1
    return dict(study=study,decision=decision,openCases=len(control["openCases"]),
                casesPriced=control["casesPriced"],
                inconclusive=control["casesInconclusive"])


def chosen_product(selection,quotes,market,now):
    import paper_simulation
    import paper_ko_guard
    import stop_target_audit
    if (not market.get("ready") or not market.get("priceFresh")
            or market.get("direction") not in ("LONG","SHORT")
            or not stop_target_audit.valid_plan(market.get("plan"))):
        return None,"no-confirmed-gold-stop-target-plan"
    for choice in (selection.get("choices") or []):
        if (choice.get("indicative") or choice.get("estimated")
                or choice.get("direction")!=market["direction"]
                or choice.get("scope")!="XAU/USD"):
            continue
        isin=choice.get("isin")
        raw=quotes.get(isin) or {}
        q=paper_simulation.fresh_quote(raw,now,isin)
        blocker,_=paper_ko_guard.entry_reason(choice,raw,market,now)
        if q and blocker is None:
            return (choice,raw,q),None
    return None,"no-verified-product-bid-ask-ko"


def product_study(conn,control,quality,market,selection,quotes,now):
    import paper_ko_guard
    import paper_simulation
    p=control.get("position")
    record=dict(study="product-e2e",state="no-new-entry",reason="waiting",
                priceEvidence=copy.deepcopy(quality),positionOpen=bool(p))
    if p:
        raw=quotes.get(p["isin"]) or {}
        guard,blocked=paper_ko_guard.assess(p,raw,market,now)
        terminal=paper_ko_guard.terminal(raw,p["isin"])
        if terminal or (guard and guard["crossed"]):
            p["settlementUnknown"]=True
        gold=quality.get("price")
        direction=p["direction"]
        sign=1 if direction=="LONG" else -1
        due=(p.get("exitDue") or
             (quality["verified"] and (sign*(gold-p["stop"])<=0
                  or sign*(gold-p["target"])>=0
                  or (market.get("direction") in ("LONG","SHORT")
                      and market["direction"]!=direction)))
             or now-p["entryAt"]>=3*3600000
             or (datetime.fromtimestamp(now/1000,ZURICH).hour,
                 datetime.fromtimestamp(now/1000,ZURICH).minute)>=(21,45))
        if due and not p.get("exitDue"):
            p["exitDue"]=now
        record.update(state="open-position",reason="monitoring-or-exit-pending",
                      exitDue=p.get("exitDue"),koGuard=guard,koBlock=blocked,
                      settlementUnknown=p.get("settlementUnknown") is True)
        if p.get("settlementUnknown"):
            record.update(state="unresolved-terminal",reason="ko-or-product-terminal-unpriced")
        elif p.get("exitDue"):
            q=paper_simulation.fresh_quote(raw,now,p["isin"])
            # The stop is NOT an executable stop: only a new, issuer-dated bid
            # matched to the original gold clock can settle the shadow trade.
            bid_at=paper_simulation.stamp((q or {}).get("bidAt"))
            if (quality["verified"] and q and guard and blocked is None
                    and not guard["crossed"] and number(bid_at)
                    and bid_at>=p["exitDue"]):
                proceeds=p["units"]*q["bid"]*(1-PRODUCT_SLIPPAGE)-PRODUCT_FEE_EUR
                profit=proceeds-p["entryDebit"]
                completed={**p, "status":"closed-with-observed-issuer-bid",
                    "exitAt":now,"exitOriginalSpotAt":quality["sourceAt"],
                    "exitQuoteAt":bid_at,"exitBid":q["bid"],"proceeds":proceeds,
                    "profitEur":profit,"costModel":dict(feePerSide=PRODUCT_FEE_EUR,
                        slippagePerSide=PRODUCT_SLIPPAGE,spreadIncludedInBidAsk=True),
                    "brokerExecutionVerified":False,"closedAt":now}
                close_case(conn,completed,now)
                control["cash"]+=proceeds
                control["profit"]+=profit
                control["casesPriced"]+=1
                control["position"]=None
                record.update(state="observed-model-exit",reason="observed-new-bid")
            else:
                record.update(state="exit-unpriced",reason="dated-exit-bid-or-ko-proof-missing")
        return record
    if not quality["verified"]:
        record["reason"]="original-spot-input-not-confirmed"
        return record
    candidate,reason=chosen_product(selection,quotes,market,now)
    bar=quality.get("analysisBarAt")
    if not candidate or bar==control.get("lastBarAt"):
        record["reason"]=reason or "same-bar-no-duplicate-entry"
        return record
    choice,raw,q=candidate
    control["lastBarAt"]=bar
    exposure=min(control["cash"]*.65,650.0)
    full_ask=q["ask"]*(1+PRODUCT_SLIPPAGE)
    units=math.floor((exposure-PRODUCT_FEE_EUR)/full_ask)
    if units<=0:
        record["reason"]="capital-insufficient-for-whole-unit"
        return record
    debit=units*full_ask+PRODUCT_FEE_EUR
    if debit>control["cash"]:
        record["reason"]="no-borrowing-allowed"
        return record
    plan=market["plan"]
    p=dict(id=f"product-e2e:{int(bar)}",study="product-e2e",isin=choice["isin"],
           scope="XAU/USD",direction=choice["direction"],entryAt=now,
           entryOriginalSpotAt=quality["sourceAt"],entrySpot=quality["price"],
           entryBarAt=bar,entryAsk=q["ask"],entryQuoteAt=paper_simulation.stamp(q.get("askAt")),
           units=units,entryDebit=debit,stop=plan["stop"],target=plan["target"],
           source=q.get("source"),currency="EUR",status="open",
           completeIssuerQuote=True,assumedCosts=dict(feePerSide=PRODUCT_FEE_EUR,
           slippagePerSide=PRODUCT_SLIPPAGE,spreadIncludedInBidAsk=True),
           entryChoice=copy.deepcopy(choice),brokerExecutionVerified=False)
    write_case(conn,p,True)
    control["cash"]-=debit
    control["position"]=p
    control["casesStarted"]+=1
    record.update(state="observed-model-entry",reason="issuer-ask-ko-verified",
                  entryCaseId=p["id"],units=units,entryDebit=debit)
    return record


def tick(conn,bundle,market,selection,quotes,now=None):
    """One atomic journal of all three studies; called after normal ledgers.

    A caller savepoint makes a failure observational only. Full original
    decision snapshots are retained; no automatic purge or averaging.
    """
    now=int(time.time()*1000) if now is None else now
    quality=original_input(bundle,market,now)
    decisions={"regime-routing":regime_decision(market,quality),
               "wait-vs-enter":wait_decision(market,quality)}
    for study in STUDIES:
        row=conn.execute("""SELECT payload FROM bob_shadow_study_control
            WHERE study=%s FOR UPDATE""",(study,)).fetchone()
        if row is None:
            raise RuntimeError("shadow-studies-not-initialized")
        control=copy.deepcopy(row[0])
        if study=="product-e2e":
            result=product_study(conn,control,quality,market,selection,quotes,now)
        else:
            result=update_signal_study(conn,control,study,decisions[study],quality,now)
        control["checkedAt"]=now
        control["status"]="collecting" if quality["verified"] else "input-unverified"
        control["eventCount"]=control.get("eventCount",0)+1
        event=dict(version=VERSION,study=study,observedAt=now,
                   originalInput=copy.deepcopy(quality),
                   direction=market.get("direction"),score=market.get("score"),
                   decisionReason=market.get("decisionReason"),
                   analysisBarAt=market.get("analysisBarAt"),
                   regime=__import__("ranking_regimes").classify(market),
                   result=result,productEvidence=(
                       {k:{field:v.get(field) for field in
                           ("bid","ask","bidAt","askAt","quoteAt","source",
                            "currency","productVerified","paperQuoteAccepted")}
                        for k,v in quotes.items() if isinstance(v,dict) and
                        k in [c.get("isin") for c in (selection.get("choices") or [])]}
                       if study=="product-e2e" else None),
                   readOnly=True,realOrders=False)
        conn.execute("""INSERT INTO bob_shadow_study_events
            (study,at,cycle,payload) VALUES(%s,to_timestamp(%s/1000.0),%s,%s::jsonb)
            ON CONFLICT DO NOTHING""",
            (study,now,now,json.dumps(event,allow_nan=False)))
        conn.execute("""UPDATE bob_shadow_study_control
            SET payload=%s::jsonb WHERE study=%s""",
            (json.dumps(control,allow_nan=False),study))


def report(conn):
    """Bounded count/status view; raw journal remains in private DB."""
    try:
        rows=conn.execute("""SELECT study,payload FROM bob_shadow_study_control
            WHERE study=ANY(%s::text[])""",(list(STUDIES),)).fetchall()
    except Exception:
        return dict(status="unavailable",readOnly=True,reason="study-report-query-failed")
    result=[]
    for study,control in rows:
        p=control.get("position")
        result.append(dict(study=study,status=control.get("status"),
            startedAt=control.get("startedAt"),checkedAt=control.get("checkedAt"),
            eventsRecorded=control.get("eventCount"),
            casesStarted=control.get("casesStarted"),casesPriced=control.get("casesPriced"),
            casesInconclusive=control.get("casesInconclusive"),
            openCases=len(control.get("openCases") or [])+(1 if p else 0),
            modelCapitalEur=control.get("cash") if study=="product-e2e" else None,
            modelProfitEur=control.get("profit") if study=="product-e2e" else None,
            realizedResultVerified=False,realOrders=False))
    return dict(status="observed" if len(result)==len(STUDIES) else "partial",
        version=VERSION,studies=result,readOnly=True,realOrders=False,
        scope="prospective-original-evidence-with-full-event-journal",
        note="Three independent observations, no broker fills or verified net profit. "
             "A source gap never becomes an inferred exit.")
