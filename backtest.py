#!/usr/bin/env python3
"""Deterministic Bob backtest engine.

Input JSON: {"bars": [{"openTime":..., "open":..., "high":..., "low":..., "close":..., "isOpen": false}, ...]}
The engine uses only closed bars, enters on the next bar open, applies the collective rule with a MACD-slope proxy (partial-model test),
ATR/structure stop, fixed-R target, spread/slippage costs, and conservative stop-first handling
when a single bar touches both stop and target.
"""
import json, math, sys

def ema(a,p):
    if not a: return None
    k=2/(p+1); e=a[0]
    for x in a[1:]: e=x*k+e*(1-k)
    return e

def rsi(a,p=14):
    if len(a)<=p: return 50.0
    g=l=0.0
    for i in range(1,p+1):
        d=a[i]-a[i-1]; g+=max(d,0); l+=max(-d,0)
    g/=p; l/=p
    for i in range(p+1,len(a)):
        d=a[i]-a[i-1]; g=(g*(p-1)+max(d,0))/p; l=(l*(p-1)+max(-d,0))/p
    return 100.0 if l==0 else 100-100/(1+g/l)

def atr(b,p=14):
    if len(b)<p+1:return 0
    tr=[max(x["high"]-x["low"],abs(x["high"]-b[i-1]["close"]),abs(x["low"]-b[i-1]["close"])) for i,x in enumerate(b[1:],1)]
    return sum(tr[-p:])/p

def collective_signal(values):
    """One price collective: repeated signs never increase its weight."""
    signs = {1 if v > 0 else -1 if v < 0 else 0 for v in values}
    if not signs or (1 in signs and -1 in signs):
        return 0
    return (1 if 1 in signs else -1 if -1 in signs else 0) * (0.5 if 0 in signs else 1)

def tf_score(b):
    b=[x for x in b if not x.get("isOpen")]
    if len(b)<200:return "NEUTRAL",False
    a=[x["close"] for x in b[-220:]]
    e20,e50=ema(a,20),ema(a,50); e200=ema(a,200) if len(a)>=200 else None
    R=rsi(a); f=ema(a,12); s=ema(a,26)
    # MACD slope proxy matching the live model's current/previous EMA spread.
    mac=(f-s)
    prev_a=a[:-1]; prev=(ema(prev_a,12)-ema(prev_a,26)) if len(prev_a)>=26 else mac
    score=collective_signal([a[-1]-e20,e20-e50,e50-e200,mac-prev,1 if 50<R<75 else -1 if 25<R<50 else 0])
    return ("LONG" if score>=0.5 else "SHORT" if score<=-0.5 else "NEUTRAL"),True

def stop_target(b,entry,dir,atr_mult=1.5,rr=2.0):
    if len(b)<40:return None,None
    atrv=atr(b)
    lookback=b[-40:]
    highs=[x["high"] for x in lookback]; lows=[x["low"] for x in lookback]
    swing=lookback[-12:]
    swing_h=max(x["high"] for x in swing); swing_l=min(x["low"] for x in swing)
    sup=min(lows); res=max(highs); buf=max(atrv*.20,.01)
    structure=(min(swing_l,sup)-buf) if dir=="LONG" else (max(swing_h,res)+buf)
    atrstop=entry-atrv*atr_mult if dir=="LONG" else entry+atrv*atr_mult
    stop=min(structure,atrstop) if dir=="LONG" else max(structure,atrstop)
    maxdist=atrv*max(2.5,atr_mult+.75)
    if abs(entry-stop)>maxdist: stop=entry-maxdist if dir=="LONG" else entry+maxdist
    risk=abs(entry-stop)
    target=entry+risk*rr if dir=="LONG" else entry-risk*rr
    return stop,target

def backtest(bars,cost_bps=5,slippage=0.20):
    bars=sorted([b for b in bars if not b.get("isOpen")],key=lambda x:x["openTime"])
    trades=[]; equity=0.0; peak=0.0; maxdd=0.0
    # The live MTF model requires 200 closed bars on every timeframe.
    # Estimate the input bar size so the test does not manufacture a 4h history
    # from only a few days of 5m/15m/1h data.
    deltas=[(bars[i]["openTime"]-bars[i-1]["openTime"])/60000 for i in range(1,min(len(bars),500)) if bars[i]["openTime"]>bars[i-1]["openTime"]]
    source_minutes=max(1,round(sum(deltas)/len(deltas))) if deltas else 60
    required_source_bars=math.ceil(200*240/source_minutes)+2
    i=max(220,required_source_bars)
    while i<len(bars)-1:
        window=bars[:i+1]
        dirs={}
        for tf,step in (("5m",5),("15m",15),("1h",60),("4h",240)):
            # Resample closed bars from the same source only for test fixtures.
            grouped={}
            ms=step*60*1000
            for x in window:
                k=(x["openTime"]//ms)*ms
                z=grouped.get(k)
                if z is None: grouped[k]=dict(x,openTime=k)
                else:
                    z["high"]=max(z["high"],x["high"]); z["low"]=min(z["low"],x["low"]); z["close"]=x["close"]
            dirs[tf]=tf_score(list(grouped.values()))[0]
        long_chain=dirs["4h"]==dirs["1h"]=="LONG" and dirs["15m"]!="SHORT" and dirs["5m"]!="SHORT"
        short_chain=dirs["4h"]==dirs["1h"]=="SHORT" and dirs["15m"]!="LONG" and dirs["5m"]!="LONG"
        direction="LONG" if long_chain else "SHORT" if short_chain else None
        if not direction: i+=1; continue
        closes=[x["close"] for x in window]
        # Advanced score, matching Bob's core trend/momentum components.
        e20,e50,e200=ema(closes,20),ema(closes,50),ema(closes,200)
        R=rsi(closes); fast=ema(closes,12); slow=ema(closes,26)
        prev=window[:-1]; pa=[x["close"] for x in prev]
        mac=fast-slow; pmac=ema(pa,12)-ema(pa,26)
        # Partial-model historical test: MACD slope remains a documented proxy.
        score=50+50*collective_signal([closes[-1]-e20,e20-e50,e50-e200,mac-pmac,1 if 50<R<75 else -1 if 25<R<50 else 0])
        if (direction=="LONG" and score<70) or (direction=="SHORT" and score>30):
            i+=1; continue
        entrybar=bars[i+1]; entry=entrybar["open"]+(slippage if direction=="LONG" else -slippage)
        stop,target=stop_target(window,entry,direction)
        if stop is None: i+=1; continue
        risk=abs(entry-stop)
        exit_price=None; reason=None; j=i+1
        while j<len(bars):
            x=bars[j]
            hit_stop=(x["low"]<=stop) if direction=="LONG" else (x["high"]>=stop)
            hit_target=(x["high"]>=target) if direction=="LONG" else (x["low"]<=target)
            if hit_stop:
                exit_price=stop-(slippage if direction=="LONG" else -slippage); reason="stop"; break
            if hit_target:
                exit_price=target-(slippage if direction=="LONG" else -slippage); reason="target"; break
            j+=1
        if exit_price is None: break
        gross=(exit_price-entry) if direction=="LONG" else (entry-exit_price)
        cost=abs(entry)+abs(exit_price)
        cost*=cost_bps/10000.0
        net=gross-cost
        Rnet=net/risk if risk else 0
        equity+=Rnet; peak=max(peak,equity); maxdd=max(maxdd,peak-equity)
        trades.append({"entry":entry,"exit":exit_price,"direction":direction,"R":Rnet,"reason":reason,"bars":j-i})
        i=max(i+1,j)
    wins=sum(t["R"]>0 for t in trades); losses=sum(t["R"]<=0 for t in trades)
    grosswin=sum(t["R"] for t in trades if t["R"]>0); grossloss=-sum(t["R"] for t in trades if t["R"]<0)
    return {"trades":len(trades),"wins":wins,"losses":losses,"win_rate":wins/len(trades) if trades else None,
            "avg_R":sum(t["R"] for t in trades)/len(trades) if trades else None,
            "expectancy_R":sum(t["R"] for t in trades)/len(trades) if trades else None,
            "profit_factor":grosswin/grossloss if grossloss else None,
            "net_R":equity,"max_drawdown_R":maxdd,"trades_detail":trades}

def main():
    if len(sys.argv)<2:
        print("usage: backtest.py bars.json"); return 2
    with open(sys.argv[1],encoding="utf-8") as f: data=json.load(f)
    print(json.dumps(backtest(data["bars"]),indent=2))
if __name__=="__main__": raise SystemExit(main())
