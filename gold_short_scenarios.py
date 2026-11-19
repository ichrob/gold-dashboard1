"""New prospective SHORT-HOLD Gold research: regimes and evidence-only model fills.

Separate 1,000 EUR virtual reference accounts; not broker orders or a change to
Bob's 15 existing paper ledgers. All entry signals use already CLOSED original
minute bars, and exits only genuinely observed fresh spot quotes. Never infer a
stop fill, source-gap outcome, or historical product execution.
"""
import copy
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION="gold-short-regime-20261119-v1"
MINUTE=60000
INITIAL_EUR=1000.0
LEVERS=(5,10,20)
COST_VARIABLE=.006
COST_FIXED=2.
MAX_EXPOSURE=.65
MAX_CASES=100
MAX_HOURS=5
ZURICH=ZoneInfo("Europe/Zurich")
FAMILIES=("trend-reentry","breakout-retest","false-breakout")
OPTIONS={
 "control":{},
 "adx20":{"adx":20.},
 "age25":{"ageMinutes":25},
 "drift11":{"driftAtr":1.1},
 "rr20":{"minRR":2.0},
 "stop10":{"noProgressMinutes":10},
 "risk05":{"riskFraction":.005},
}
ARM_CONFIG={
 family+":"+option:{
  "family":family,"option":option,
  "adx":(25. if family!="false-breakout" else 25.),
  "ageMinutes":15,"driftAtr":.8,"minRR":1.5,
  "noProgressMinutes":15,"riskFraction":.01,
  "maxMinutes":{"trend-reentry":90,"breakout-retest":60,
                "false-breakout":45}[family],
  **cfg}
 for family in FAMILIES for option,cfg in OPTIONS.items()
}
NOTE=("Nur 21 prospektive Original-Gold-Spot-Schattenkonten zu je 1.000 EUR "
      "Modellreferenzkapital und drei rechnerischen Hebelszenarien; kein Echtgeld "
      "oder KO-/DEGIRO-Nettoertrag. Keine rückwirkenden Fills, unbekannte "
      "Quellenlücken bleiben unbepreist. Beispielkosten: 0,6 % auf "
      "virtuelles Einsatzkapital plus 2 EUR je Modellhandel.")


def num(x):
    return type(x) in (int,float) and math.isfinite(x)


def positive(x):
    return num(x) and x>0


def session(at,*,new=False):
    if not num(at):
        return False
    d=datetime.fromtimestamp(at/1000,ZURICH)
    # Close before issuer settlement and cease new entries 15m earlier.
    return (d.weekday()<5 and (8,0) <= (d.hour,d.minute) <
            ((21,30) if new else (21,45)))


def _signed(side):
    return 1 if side=="LONG" else -1


def _dir(close,op):
    return "LONG" if close>op else "SHORT" if close<op else None


def _atr(bars):
    if len(bars)<16:
        return None
    v=[max(b["high"]-b["low"],abs(b["high"]-a["close"]),
           abs(b["low"]-a["close"]))
       for a,b in zip(bars[-16:-1],bars[-15:])]
    out=sum(v)/len(v)
    return out if positive(out) else None


def signals(rows,now):
    """3 distinct 5m-setups, all using closed, coherent original 1m candles."""
    import intraday_timing_study as candles
    if not rows or len(rows)!=120 or any(b.get("estimated") for b in rows):
        return {family:None for family in FAMILIES}, "original-minute-coverage"
    bars=candles.aggregate(rows,5,now)
    if len(bars)<17 or any(x.get("estimated") for x in bars):
        return {family:None for family in FAMILIES}, "closed-five-minute-coverage"
    atr=_atr(bars)
    if not positive(atr):
        return {family:None for family in FAMILIES}, "atr-unavailable"
    a,b,c=bars[-3:]
    if not 0<=now-c["closeTime"]<=5*MINUTE:
        return {family:None for family in FAMILIES}, "five-minute-signal-not-fresh"
    prior=bars[-12:-3]
    hi=max(z["high"] for z in prior);lo=min(z["low"] for z in prior)
    out=dict.fromkeys(FAMILIES)
    # Counter-direction retrace followed by a local continuation close.
    for side in ("LONG","SHORT"):
        sign=_signed(side)
        earlier=_dir(a["close"],a["open"])==side
        retraced=sign*(b["close"]-b["open"])<-.15*atr
        resumed=(sign*(c["close"]-c["open"])>=.25*atr
                 and sign*(c["close"]-b["close"])>.20*atr
                 and sign*(c["close"]-(b["high"] if sign>0 else b["low"]))>=-.15*atr)
        if earlier and retraced and resumed:
            stop=(min(b["low"],c["low"])-.2*atr if sign>0
                  else max(b["high"],c["high"])+.2*atr)
            target=(hi+.2*atr if sign>0 else lo-.2*atr)
            out["trend-reentry"]=dict(direction=side,kind="trend-reentry",
                barAt=c["openTime"],closedAt=c["closeTime"],close=c["close"],
                atr=atr,stopAnchor=stop,targetAnchor=target)
        # A closed breakout, then retest, then second confirmation.
        level=hi if sign>0 else lo
        breakout=sign*(a["close"]-level)>.15*atr and _dir(a["close"],a["open"])==side
        retest=(abs((b["low"] if sign>0 else b["high"])-level)<=.45*atr
                and sign*(b["close"]-level)>=-.15*atr)
        follow=(_dir(c["close"],c["open"])==side
                and sign*(c["close"]-(b["high"] if sign>0 else b["low"]))>=.10*atr)
        if breakout and retest and follow:
            stop=(min(b["low"],c["low"])-.2*atr if sign>0
                  else max(b["high"],c["high"])+.2*atr)
            measured=hi-lo
            target=level+sign*max(1.5*atr,measured)
            out["breakout-retest"]=dict(direction=side,kind="breakout-retest",
                barAt=c["openTime"],closedAt=c["closeTime"],close=c["close"],
                atr=atr,stopAnchor=stop,targetAnchor=target)
        # Failed breakout on a CLOSED previous bar, followed by a reversal
        # confirmation. This is directionally opposite the original sweep.
        sweep=(sign*(a["high"]-hi)>.1*atr if sign>0
               else sign*(a["low"]-lo)>.1*atr)
        level=hi if sign>0 else lo
        back_in=sign*(b["close"]-level)<-.15*atr
        reverse_side="SHORT" if side=="LONG" else "LONG"
        flip=(_dir(c["close"],c["open"])==reverse_side
              and -sign*(c["close"]-b["close"])>.25*atr)
        if sweep and back_in and flip:
            reverse_sign=-sign
            stop=(max(a["high"],b["high"])+.2*atr if sign>0
                  else min(a["low"],b["low"])-.2*atr)
            target=(lo+.2*atr if sign>0 else hi-.2*atr)
            out["false-breakout"]=dict(direction=reverse_side,
                kind="false-breakout",barAt=c["openTime"],
                closedAt=c["closeTime"],close=c["close"],
                atr=atr,stopAnchor=stop,targetAnchor=target)
    return out,None


def gate(sig,market,price,now,cfg):
    if sig is None:
        return "no-setup"
    if (not isinstance(market,dict) or market.get("ready") is not True
            or market.get("priceFresh") is not True):
        return "market-analysis-not-ready"
    if (not price.get("available") or price.get("estimated")
            or not num(price.get("at")) or market.get("dataAt") != price["at"]
            or not positive(market.get("price"))
            or abs(market["price"]-price["price"])>.02):
        return "original-spot-not-aligned"
    if not session(now,new=True) or not (market.get("session") or {}).get("entryAllowed"):
        return "session-closed"
    if price["at"] < sig["closedAt"]:
        return "spot-before-closed-signal"
    if not 0<=now-(market.get("analysisBarAt") or 0)-15*MINUTE<=cfg["ageMinutes"]*MINUTE:
        return "prior-main-signal-age"
    if abs(price["price"]-sig["close"])>cfg["driftAtr"]*sig["atr"]:
        return "spot-close-drift"
    frames=((market.get("dmi") or {}).get("frames") or {})
    fif=frames.get("15m") or {};hour=frames.get("1h") or {}
    adx=fif.get("adx")
    if not num(adx) or not num(hour.get("adx")):
        return "original-adx-unavailable"
    side=sig["direction"]
    if cfg["family"]=="false-breakout":
        # Flat-structure reversal; reject strong 15m trend. Never trade
        # against a confirmed opposite main trend.
        if adx>cfg["adx"] or (market.get("direction") in ("LONG","SHORT")
                            and market["direction"]!=side):
            return "strong-or-opposed-trend"
    else:
        if (adx < cfg["adx"] or fif.get("direction")!=side
                or hour.get("direction")!=side
                or (market.get("trendContext") or {}).get("direction")!=side):
            return "mtf-adx-not-confirmed"
        snap=market.get("analysisSnapshot") or {}
        e20=snap.get("e20");e50=snap.get("e50")
        if not positive(e20) or not positive(e50) or _signed(side)*(e20-e50)<=0:
            return "ema-20-50-not-confirmed"
        if market.get("direction") in ("LONG","SHORT") and market["direction"]!=side:
            return "main-opposes-study"
    return None


def candidate(sig,price,cfg):
    if sig is None or not price.get("available"):
        return None,"no-setup"
    p=price["price"];side=sig["direction"];sign=_signed(side)
    risk=sign*(p-sig["stopAnchor"])
    if not positive(risk) or not .45*sig["atr"]<=risk<=3*sig["atr"]:
        return None,"stop-distance-invalid"
    target=sig["targetAnchor"]
    rr=sign*(target-p)/risk
    if rr < cfg["minRR"] or not positive(target):
        return None,"target-room-insufficient"
    return dict(direction=side,entry=p,entrySourceAt=price["at"],
        signalBarAt=sig["barAt"],signalClosedAt=sig["closedAt"],
        stop=p-sign*risk,target=target,risk=risk,
        atr=sig["atr"],rr=rr,estimated=False,
        realOrders=False,productReturnVerified=False),None


def _slot():
    return dict(equityEur=INITIAL_EUR,peakEur=INITIAL_EUR,
                modelNetEur=0.,completed=0,wins=0,
                maxDrawdownPct=0.,inconclusive=0)


def _arm():
    return dict(position=None,started=0,closed=0,inconclusive=0,
                lastSignal=None,lastExitAt=None,lastBlock="awaiting-source",
                blockCounts={},exitCounts={},levers={str(x):_slot() for x in LEVERS},
                lastObservedAt=None)


def seed(now):
    return dict(version=VERSION,startedAt=now,checkedAt=None,arms={
        key:_arm() for key in ARM_CONFIG},lastInput=None,realOrders=False)


def _close_position(arm,cfg,p,now,observed,why):
    side=p["direction"];sign=_signed(side)
    arm["closed"]+=1
    arm["exitCounts"][why]=arm["exitCounts"].get(why,0)+1
    move=sign*(observed/p["entry"]-1)
    for lev in LEVERS:
        slot=arm["levers"][str(lev)]
        eq=slot["equityEur"]
        risk_pct=p["risk"]/p["entry"]
        stake=min(.65*eq,eq*cfg["riskFraction"]/(lev*risk_pct))
        if stake<=0 or 1+lev*move<=0:
            slot["inconclusive"]+=1
            continue
        net=stake*lev*move - stake*COST_VARIABLE-COST_FIXED
        slot["equityEur"]=max(0.,eq+net)
        slot["peakEur"]=max(slot["peakEur"],slot["equityEur"])
        slot["maxDrawdownPct"]=max(slot["maxDrawdownPct"],
             100*(slot["peakEur"]-slot["equityEur"])/slot["peakEur"])
        slot["modelNetEur"]+=net
        slot["completed"]+=1
        slot["wins"]+=int(net>0)
    arm["lastExitAt"]=now
    arm["position"]=None


def advance(old,bundle,market,now):
    """Single bounded worker call; no broker access, no retroactive trades."""
    import intraday_timing_study as candles
    state=copy.deepcopy(old)
    if not num(now) or (num(state.get("checkedAt")) and now<=state["checkedAt"]):
        return state
    state["checkedAt"]=now
    rows,source_error=candles.minute_history(bundle,now,False)
    sigs,signal_error=signals(rows,now)
    price=candles.source(bundle,now,False)
    state["lastInput"]=dict(status="original" if not (source_error or signal_error) else "unavailable",
                            code=source_error or signal_error,
                            checkedAt=now,sourceAt=price.get("at"),
                            originalSpotFresh=price.get("available") is True)
    for key,cfg in ARM_CONFIG.items():
        arm=state["arms"].setdefault(key,_arm())
        p=arm.get("position")
        if p is not None:
            if (not price.get("available") or not num(price.get("at"))
                    or now-p["lastObservedAt"]>90000
                    or price["at"]-p["lastSourceAt"]>90000):
                if now-p["lastObservedAt"]>90000:
                    arm["inconclusive"]+=1;arm["position"]=None
                    arm["lastExitAt"]=now
                    arm["lastBlock"]="unobserved-exit-gap"
                continue
            if price["at"]<=p["lastSourceAt"]:
                continue
            current=price["price"];side=p["direction"];sign=_signed(side)
            held=price["at"]-p["entrySourceAt"]
            progress=sign*(current-p["entry"])
            why=("stop" if sign*(current-p["stop"])<=0 else
                 "target" if sign*(current-p["target"])>=0 else
                 "session-exit" if not session(now) else
                 "time-limit" if held>=cfg["maxMinutes"]*MINUTE else
                 "no-progress" if held>=cfg["noProgressMinutes"]*MINUTE
                    and progress<.25*p["risk"] else
                 "main-opposite" if market.get("ready") is True and
                    market.get("direction") in ("LONG","SHORT") and
                    market["direction"]!=side else None)
            p["lastObservedAt"]=now;p["lastSourceAt"]=price["at"]
            if why:
                _close_position(arm,cfg,p,now,current,why)
            else:
                p["bestPrice"]=(max(p["bestPrice"],current) if sign>0
                                else min(p["bestPrice"],current))
            continue
        sig=sigs.get(cfg["family"])
        blocked=source_error or signal_error or gate(sig,market,price,now,cfg)
        plan=None
        if not blocked:
            plan,blocked=candidate(sig,price,cfg)
        arm["lastBlock"]=blocked
        key_signal=(str(sig["closedAt"])+":"+sig["direction"] if sig else None)
        if blocked:
            arm["blockCounts"][blocked]=arm["blockCounts"].get(blocked,0)+1
            continue
        if (arm["started"]>=MAX_CASES
                or key_signal==arm.get("lastSignal")
                or num(arm.get("lastExitAt")) and now-arm["lastExitAt"]<3*MINUTE):
            arm["lastBlock"]="case-cap-or-cooldown"
            continue
        today=datetime.fromtimestamp(now/1000,ZURICH).date().isoformat()
        if arm.get("riskDay")!=today:
            arm["riskDay"]=today
            arm["dayStartEquity"]=arm["levers"]["10"]["equityEur"]
        if arm["levers"]["10"]["equityEur"]<=.97*arm["dayStartEquity"]:
            arm["lastBlock"]="daily-loss-limit"
            continue
        if not positive(plan.get("stop")):
            arm["lastBlock"]="invalid-stop"
            continue
        arm["started"]+=1
        arm["lastSignal"]=key_signal
        arm["position"]={**plan, "id":VERSION+":"+key+":"+key_signal,
            "family":cfg["family"],"option":cfg["option"],
            "openedAt":now,"lastObservedAt":now,
            "lastSourceAt":price["at"],"bestPrice":plan["entry"],
            "realOrders":False,"productReturnVerified":False}
    return state


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_short_regime_state (
        id TEXT PRIMARY KEY, payload JSONB NOT NULL)""")


def tick(conn,bundle,market,now):
    row=conn.execute("SELECT payload FROM bob_short_regime_state WHERE id=%s FOR UPDATE",
                     (VERSION,)).fetchone()
    s=advance(row[0] if row else seed(now),bundle,market,now)
    conn.execute("""INSERT INTO bob_short_regime_state(id,payload)
        VALUES(%s,%s::jsonb) ON CONFLICT(id) DO UPDATE
        SET payload=EXCLUDED.payload""",
        (VERSION,json.dumps(s,allow_nan=False)))


def report(conn):
    row=conn.execute("SELECT payload FROM bob_short_regime_state WHERE id=%s",
                     (VERSION,)).fetchone()
    if not row:
        return dict(status="awaiting-first-worker-check",readOnly=True,
                    realOrders=False,productReturnVerified=False)
    state=row[0]
    out=[]
    for name,cfg in ARM_CONFIG.items():
        a=state["arms"].get(name) or _arm()
        out.append(dict(name=name,family=cfg["family"],option=cfg["option"],
            adx=cfg["adx"],ageMinutes=cfg["ageMinutes"],
            driftAtr=cfg["driftAtr"],minRR=cfg["minRR"],
            noProgressMinutes=cfg["noProgressMinutes"],
            riskFraction=cfg["riskFraction"],maxMinutes=cfg["maxMinutes"],
            started=a["started"],closed=a["closed"],open=bool(a.get("position")),
            inconclusive=a["inconclusive"],lastBlock=a.get("lastBlock"),
            exitCounts=copy.deepcopy(a.get("exitCounts") or {}),
            leverageScenarios=[dict(leverage=int(lev),
                equityEur=round(a["levers"][str(lev)]["equityEur"],4),
                completed=a["levers"][str(lev)]["completed"],
                wins=a["levers"][str(lev)]["wins"],
                maxDrawdownPct=round(a["levers"][str(lev)]["maxDrawdownPct"],3))
                for lev in LEVERS]))
    return dict(status="collecting",version=VERSION,
        checkedAt=state.get("checkedAt"),startedAt=state["startedAt"],
        variants=out,configurationsReported=len(ARM_CONFIG)*len(LEVERS),
        originalSource=state.get("lastInput"),initialEurPerArm=INITIAL_EUR,
        modelCostVariable=COST_VARIABLE,modelCostFixedEur=COST_FIXED,
        realOrders=False,productReturnVerified=False,
        strategyWinnerConfirmed=False,liveRulesChanged=False,note=NOTE)
