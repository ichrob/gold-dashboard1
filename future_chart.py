"""Display-only Yahoo GC=F candles; never injected into Spot analysis."""
import math
import threading
import time
_cache={}
_lock=threading.Lock()
STEPS={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400}
def snapshot(tf, fetch):
    if tf not in STEPS:raise ValueError('Unbekannte Zeitebene')
    with _lock:
        old=_cache.get(tf)
        if old and time.monotonic()-old[0]<30:return old[1]
        interval='1h' if tf=='4h' else tf
        span='1d' if tf=='1m' else '1mo' if tf in ('1h','4h') else '5d'
        try:
            data=fetch(f'https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF?interval={interval}&range={span}',retries=1,user_agent='Mozilla/5.0')
            result=data['chart']['result'][0];q=result['indicators']['quote'][0];rows=[]
            for i,t in enumerate(result.get('timestamp') or []):
                try:
                    o,h,l,c=(float(q[k][i]) for k in ('open','high','low','close'))
                    if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)) or l>min(o,c) or h<max(o,c):continue
                    rows.append(dict(openTime=t*1000,open=o,high=h,low=l,close=c,instrument='GC=F',source='Yahoo Finance · GC=F',isOpen=t+STEPS[interval]>time.time()))
                except (ValueError,TypeError,IndexError):continue
            if tf=='4h':
                grouped={}
                for r in rows:
                    key=r['openTime']//14400000*14400000
                    if key not in grouped:grouped[key]={**r,'openTime':key}
                    else:grouped[key].update(high=max(grouped[key]['high'],r['high']),low=min(grouped[key]['low'],r['low']),close=r['close'])
                    grouped[key]['isOpen']=key+14400000>time.time()*1000
                rows=list(grouped.values())
            out=dict(bars=rows[-300:],instrument='GC=F',note='Yahoo Futures-Referenz; möglicherweise verzögert, kein bestätigter GCZ26-Kontrakt')
            _cache[tf]=(time.monotonic(),out)
            return out
        except Exception:
            return {**(old[1] if old else {'bars':[]}), 'error':'Future-Kursreihe derzeit nicht abrufbar'}
