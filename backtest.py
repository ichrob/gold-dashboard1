#!/usr/bin/env python3
"""Deterministic Bob backtest engine.

Input JSON: {"bars": [{"openTime":..., "open":..., "high":..., "low":..., "close":..., "isOpen": false}, ...]}
The engine uses only closed bars, enters on the next bar open, applies the live score/MTF logic,
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

def tf_score(b):
    b=[x for x in b if not x.get("isOpen")]
    if len(b)<50:return "NEUTRAL",False
    a=[x["close"] for x in b[-220:]]
    e20,e50=ema(a,20),ema(a,50); e200=ema(a,200) if len(a)>=200 else None
    R=rsi(a); f=ema(a,12); s=ema(a,26)
    # MACD slope proxy matching the live model's current/previous EMA spread.
    mac=(f-s)
    prev_a=a[:-1]; prev=(ema(prev_a,12)-ema(prev_a,26)) if len(prev_a)>=26 else mac
    score=(1 if a[-1]>e20 else -1)+(1 if e20>e50 else -1)+(1 if e50>e200 else -1 if e200 is not None else 0)+(1 if mac>prev else -1)
    if math.isfinite(R):
        score += 1 if 50<=R<=70 else -1 if R<35 else 0
    components=5 if e200 is not None else 4
    return ("LONG" if score>=2 else "SHORT" if score<=-2 else "NEUTRAL"),True

def stop_target(b,entry,dir,atr_mult=1.5,rr=2.0):
    if len(b)<40:return None,None
    atrv=atr(b)
    highs=[x["high"] for x in b[-40:]]; lows=[x["low"] for x in b[-40:]]
    swing_h=max(highs); swing_l=min(lows)
    sup=min(lows); res=max(highs); buf=max(atrv*.20,.01)
    structure=swing_l-buf if dir=="LONG" else swing_h+buf
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
    i=220
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
        pts=maxv=0
        if e20>e50>e200: pts+=3
        elif e20<e50<e200: pts-=3
        maxv+=3
        if mac>pmac and R>=50 and R<75: pts+=2
        elif mac<pmac and R<50 and R>25: pts-=2
        maxv+=2
        # ADX/Bollinger/VWAP are omitted from this standalone engine rather than approximated.
        # This keeps the baseline honest: the resulting test is explicitly a partial-model test.
        maxv+=2+1+1+.5
        score=50+50*(pts/maxv)
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
