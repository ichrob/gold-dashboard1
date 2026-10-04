import json, os, time
from urllib.request import Request, urlopen

BOB_URL=os.environ.get("BOB_URL","https://bob-private-scanner.onrender.com").rstrip("/")
TOKEN=os.environ.get("BOB_WORKER_TOKEN","")

def get(path):
    r=Request(BOB_URL+path,headers={"Accept":"application/json","X-Bob-Worker-Token":TOKEN})
    with urlopen(r,timeout=25) as x:return json.loads(x.read().decode())

def post(path,payload):
    b=json.dumps(payload,separators=(",",":")).encode()
    r=Request(BOB_URL+path,data=b,method="POST",headers={"Content-Type":"application/json","X-Bob-Worker-Token":TOKEN})
    with urlopen(r,timeout=25) as x:return json.loads(x.read().decode())

def ema(a,p):
    k=2/(p+1);e=a[0]
    for v in a[1:]:e=v*k+e*(1-k)
    return e

def emas(a,p):
    k=2/(p+1);e=a[0];o=[e]
    for v in a[1:]:e=v*k+e*(1-k);o.append(e)
    return o

def rsi(a,p=14):
    if len(a)<p+2:return 50
    g=sum(max(a[i]-a[i-1],0) for i in range(1,p+1))/p
    l=sum(max(a[i-1]-a[i],0) for i in range(1,p+1))/p
    for i in range(p+1,len(a)):
        d=a[i]-a[i-1];g=(g*(p-1)+max(d,0))/p;l=(l*(p-1)+max(-d,0))/p
    return 100 if l==0 else 100-100/(1+g/l)

def atr(c,p=14):
    if len(c)<p+1:return 0
    tr=[max(c[i]["high"]-c[i]["low"],abs(c[i]["high"]-c[i-1]["close"]),abs(c[i]["low"]-c[i-1]["close"])) for i in range(1,len(c))]
    return sum(tr[-p:])/min(p,len(tr))

def collective_signal(values):
    """One price collective: repeated signs never increase its weight."""
    signs = {1 if v > 0 else -1 if v < 0 else 0 for v in values}
    if not signs or (1 in signs and -1 in signs):
        return 0
    return (1 if 1 in signs else -1 if -1 in signs else 0) * (0.5 if 0 in signs else 1)

def tfscore(bars):
    c=[x for x in bars if not x.get("isOpen")][-220:]
    if len(c)<200:return "NEUTRAL",False
    a=[float(x["close"]) for x in c];e20,e50=ema(a,20),ema(a,50);e200=ema(a,200) if len(a)>=200 else None
    f,s=emas(a,12),emas(a,26);mac=f[-1]-s[-1];prev=f[-2]-s[-2];R=rsi(a);score=0;n=0
    score=collective_signal([a[-1]-e20,e20-e50,e50-e200,mac-prev,1 if 50<R<75 else -1 if 25<R<50 else 0])
    return ("LONG" if score>=0.5 else "SHORT" if score<=-0.5 else "NEUTRAL"),True

def adx(c,p=14):
    if len(c)<p*2+2:return 0
    tr=[];pl=[];mi=[]
    for i in range(1,len(c)):
        tr.append(max(c[i]["high"]-c[i]["low"],abs(c[i]["high"]-c[i-1]["close"]),abs(c[i]["low"]-c[i-1]["close"])))
        u=c[i]["high"]-c[i-1]["high"];d=c[i-1]["low"]-c[i]["low"];pl.append(u if u>d and u>0 else 0);mi.append(d if d>u and d>0 else 0)
    t=sum(tr[-p:])/p;P=sum(pl[-p:])/p;M=sum(mi[-p:])/p
    dp,dm=(100*P/t,100*M/t) if t else (0,0)
    return 100*abs(dp-dm)/(dp+dm) if dp+dm else 0

def score(c):
    a=[float(x["close"]) for x in c];e20,e50,e200=ema(a,20),ema(a,50),ema(a,200);R=rsi(a);at=atr(c);f,s=emas(a,12),emas(a,26)
    mac=f[-1]-s[-1];sig=emas([f[i]-s[i] for i in range(len(a))],9)[-1];ad=adx(c)
    v=a[-20:];mid=sum(v)/len(v);sd=(sum((x-mid)**2 for x in v)/len(v))**.5;st=100*(c[-1]["close"]-min(x["low"] for x in c[-14:]))/(max(x["high"] for x in c[-14:])-min(x["low"] for x in c[-14:]) or 1)
    sup=min(x["low"] for x in c[-30:]);res=max(x["high"] for x in c[-30:]);pts=0
    value=collective_signal([a[-1]-e20,e20-e50,e50-e200,mac-sig,1 if 50<R<75 else -1 if 25<R<50 else 0])
    return 50+50*value,R,at,ad,sup,res

def main():
    if not TOKEN:raise RuntimeError("BOB_WORKER_TOKEN fehlt")
    b=get("/api/live?fresh=%d"%int(time.time()*1000));h=b.get("history",{}).get("bars_by_tf",{})
    t={x:tfscore(h.get(x,[])) for x in ("5m","15m","1h","4h")}
    if not all(v[1] for v in t.values()):print("Bob worker: MTF unvollständig");return
    d=[t[x][0] for x in ("4h","1h","15m","5m")]
    mtf="LONG" if d[0]=="LONG" and d[1]=="LONG" and d[2]!="SHORT" and d[3]!="SHORT" else "SHORT" if d[0]=="SHORT" and d[1]=="SHORT" and d[2]!="LONG" and d[3]!="LONG" else "NEUTRAL"
    c=[x for x in h.get("5m",[]) if not x.get("isOpen")]
    if len(c)<200 or mtf=="NEUTRAL":print("Bob worker: kein bestätigtes MTF-Signal");return
    sc,R,at,ad,sup,res=score(c[-220:]);direction="LONG" if sc>=70 and mtf=="LONG" else "SHORT" if sc<=30 and mtf=="SHORT" else "NEUTRAL"
    if direction=="NEUTRAL":print("Bob worker: Score bestätigt kein Signal");return
    entry=c[-1]["close"];buf=max(at*.2,.01);sl=min(min(x["low"] for x in c[-12:]),sup)-buf if direction=="LONG" else max(max(x["high"] for x in c[-12:]),res)+buf
    atrsl=entry-at*1.5 if direction=="LONG" else entry+at*1.5;sl=min(sl,atrsl) if direction=="LONG" else max(sl,atrsl)
    if abs(entry-sl)>at*2.5:sl=entry-at*2.5 if direction=="LONG" else entry+at*2.5
    sid="xau5m:%s:%s"%(c[-1]["openTime"],direction)
    body=f"{direction}: bestätigtes Bob-Signal. XAU/USD {entry:.2f}. Score {sc:.0f}/100 · MTF {mtf}. Technischer Stop {sl:.2f}. RSI {R:.1f} · ADX {ad:.1f}."
    print("Bob worker:",post("/api/push/send",{"title":"Bob – neues Gold-Signal","body":body,"data":{"signalId":sid,"kind":"signal","direction":direction,"price":entry,"score":round(sc,2),"mtf":mtf,"stop":sl}}),flush=True)

if __name__=="__main__":main()
