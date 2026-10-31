"""Independent arithmetic audit. Formula agreement is not market accuracy.

EMA uses the first close seed, RSI/ADX Wilder smoothing, ATR a 14-TR
arithmetic mean, matching Bob's documented definitions (not a Wilder ATR).
No reference implementation imports Bob's indicator functions.
"""
import hashlib
import json
import math
import time
import threading
from decimal import Decimal, localcontext

VERSION = 'metric-quality-v1'
LABELS = {'e20':'EMA 20','e50':'EMA 50','e200':'EMA 200','R':'RSI 14',
          'at':'ATR 14 (arithmetisch)','macd':'MACD 12/26','sig':'MACD-Signal 9',
          'hist':'MACD-Histogramm','adx':'ADX 14','plusDI':'+DI 14','minusDI':'−DI 14',
          'gearing':'Berechneter Hebel','issuerGearing':'Hebel / Emittentenvergleich',
          'koDistance':'KO-Abstand','pnl':'Laufendes Bruttoergebnis / Original-Geldkurs'}
STEPS = {'1m':60000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'4h':14400000}

# Immutable metric checks remain available beyond the reporting window.
# Payloads may move to private Drive after verified read-through; keys remain.
def _prune_expired_checks(conn, now, monotonic=None):
    """Retained compatibility hook: never erase history or cold references."""
    return False



def finite(x):return type(x) in (float,int) and math.isfinite(x)


def reference(bars):
    with localcontext() as ctx:
        ctx.prec=40
        D=lambda x:Decimal(str(x))
        close=[D(b['close']) for b in bars]
        def smooth(values,alpha,seed=None):
            value=values[0] if seed is None else seed;out=[value]
            for x in values[1:]:
                value += alpha*(x-value);out.append(value)
            return out
        def ema(period):return smooth(close,Decimal(2)/Decimal(period+1))
        changes=[b-a for a,b in zip(close,close[1:])]
        gains=[max(x,Decimal(0)) for x in changes];losses=[max(-x,Decimal(0)) for x in changes]
        def wilder(values):
            seed=sum(values[:14])/14
            return smooth([seed]+values[14:],Decimal(1)/14)
        gain,loss=wilder(gains)[-1],wilder(losses)[-1]
        rsi=50 if gain==loss==0 else 100 if loss==0 else 100-100/(1+gain/loss)
        tr=[];up=[];down=[]
        for a,b in zip(bars,bars[1:]):
            high,low,prev=D(b['high']),D(b['low']),D(a['close'])
            tr.append(max(high-low,abs(high-prev),abs(low-prev)))
            u=high-D(a['high']);d=D(a['low'])-low
            up.append(u if u>d and u>0 else Decimal(0));down.append(d if d>u and d>0 else Decimal(0))
        t,p,m=map(wilder,(tr,up,down))
        dx=[100*abs(u-d)/(u+d) if u+d else Decimal(0) for u,d in zip(p,m)]
        adx=wilder(dx)[-1]
        mac=[a-b for a,b in zip(ema(12),ema(26))]
        sig=smooth(mac,Decimal(2)/10)[-1]
        return {k:float(v) for k,v in dict(e20=ema(20)[-1],e50=ema(50)[-1],
            e200=ema(200)[-1],R=rsi,at=sum(tr[-14:])/14,macd=mac[-1],sig=sig,
            hist=mac[-1]-sig,adx=adx,plusDI=100*p[-1]/t[-1] if t[-1] else 0,
            minusDI=100*m[-1]/t[-1] if t[-1] else 0).items()}


def compare(bars,actual,tf,now):
    step=STEPS.get(tf)
    clean=bool(step and len(bars)>=28 and all(isinstance(b,dict) and b.get('instrument')=='XAU/USD'
        and not b.get('isOpen') and not b.get('estimated') and finite(b.get('openTime'))
        and b['openTime']%step==0 and b['openTime']+step<=now
        and all(finite(b.get(k)) and b[k]>0 for k in ('open','high','low','close'))
        and b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'] for b in bars))
    clean=clean and all(b['openTime']-a['openTime']==step for a,b in zip(bars,bars[1:]))
    fresh=bool(clean and 0<=now-bars[-1]['openTime']<=2*step)
    base=dict(version=VERSION,timeframe=tf,at=bars[-1].get('openTime') if bars else now,
              checkedAt=now,inputCount=len(bars),source='XAU/USD · geschlossene OHLC',
              inputHash=hashlib.sha256(json.dumps(bars,sort_keys=True).encode()).hexdigest())
    if not fresh:return dict(base,status='unavailable',reason='Aktuelle, vollständige und passende OHLC fehlen',metrics={})
    expected=reference(bars);metrics={}
    for k in actual.keys() & expected.keys():
        a=actual[k];e=expected[k];tolerance=max(1e-8,abs(e)*1e-9)
        warm=len(bars)>=int(k[1:]) if k in ('e20','e50','e200') else True
        error=abs(a-e) if finite(a) and warm else None
        metrics[k]=dict(label=LABELS[k],actual=a if finite(a) else None,reference=e,
            absoluteError=error,tolerance=tolerance,status='unavailable' if error is None else
            'matched' if error<=tolerance else 'mismatch')
    status='mismatch' if any(m['status']=='mismatch' for m in metrics.values()) else 'matched' if metrics else 'unavailable'
    return dict(base,status=status,metrics=metrics)


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_metric_checks (
        version TEXT NOT NULL, scope TEXT NOT NULL, bar_at BIGINT NOT NULL,
        checked_at BIGINT NOT NULL, payload JSONB NOT NULL,
        PRIMARY KEY(version,scope,bar_at))''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_metric_checked ON bob_metric_checks(checked_at)')


def capture(conn,bundle,market,now=None):
    now=int(time.time()*1000) if now is None else now
    snapshot=market.get('analysisSnapshot') or {};tf=snapshot.get('timeframe','15m')
    source=(bundle.get('history') or {}).get('bars_by_tf') or {}
    frames=[('display:'+tf,tf,[b for b in source.get(tf,[]) if not b.get('isOpen') and b.get('instrument')=='XAU/USD'][-240:],snapshot)]
    for frame,actual in ((market.get('dmi') or {}).get('frames') or {}).items():
        step=STEPS.get(frame,0)
        bars=sorted([b for b in source.get(frame,[]) if not b.get('isOpen') and finite(b.get('openTime')) and b['openTime']+step<=now],key=lambda b:b['openTime'])[-220:]
        frames.append(('dmi:'+frame,frame,bars,{k:actual.get(k) for k in ('adx','plusDI','minusDI')}))
    for scope,frame,bars,actual in frames:
        row=compare(bars,actual,frame,now)
        conn.execute('''INSERT INTO bob_metric_checks VALUES(%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT DO NOTHING''',(VERSION,scope,int(row['at'] or now),now,json.dumps(row,allow_nan=False)))
    _prune_expired_checks(conn, now)


def report(conn,now=None):
    now=int(time.time()*1000) if now is None else now
    rows=conn.execute('''SELECT version,scope,bar_at,checked_at,payload FROM bob_metric_checks WHERE version=%s
        AND checked_at>=%s ORDER BY checked_at DESC LIMIT 10000''',(VERSION,now-30*86400000)).fetchall()
    groups={}
    for version,scope,bar_at,checked_at,row in rows:
        row = __import__('cold_metrics').resolve(conn, row, scope, identity=(version,scope,bar_at,checked_at))
        for key in (row.get('metrics') or {k:None for k in LABELS if k not in ('gearing','issuerGearing','koDistance','pnl')}):
            if key not in LABELS:continue
            g=groups.setdefault((scope,key),dict(id=scope+':'+key,label=LABELS[key]+' · '+scope,
                count=0,missing=0,mismatches=0,lastAt=row['checkedAt'],lastStatus='unavailable',
                freshUntil=(row.get('at',row['checkedAt'])+2*STEPS[scope.split(':')[-1]]) if scope.split(':')[-1] in STEPS else row['checkedAt']+90000,
                unit=row.get('currency',''),errors=[]))
            m=row['metrics'].get(key,{})
            if not g['count'] and not g['missing']:g['lastStatus']=m.get('status','unavailable')
            if m.get('absoluteError') is None:g['missing']+=1
            else:
                g['count']+=1;g['errors'].append(m['absoluteError']);g['mismatches']+=m['status']=='mismatch'
    out=[]
    for g in groups.values():
        errors=g.pop('errors');g['mae']=sum(errors)/len(errors) if errors else None
        g['maxError']=max(errors) if errors else None
        g['status']='stale' if now>g['freshUntil'] else g['lastStatus']
        out.append(g)
    return dict(rows=out,windowDays=30,detailsLimit=10000,truncated=len(rows)==10000,
        note='Unabhängige Dezimal-Nachrechnung derselben OHLC; keine Bestätigung der Kursquelle oder Signalprofitabilität. Formelwerte werden nicht optimiert.')


def product_check(conn,quote,now):
    """Arithmetic gearing check and separately gated independent issuer evidence."""
    calc=quote.get('leverageCalculation') or {};i=calc.get('inputs') or {};metrics={}
    def add(k,a,b,tolerance):
        error=abs(a-b) if finite(a) and finite(b) else None
        metrics[k]=dict(label=LABELS[k],actual=a if finite(a) else None,reference=b,
            absoluteError=error,tolerance=tolerance,status='unavailable' if error is None else
            'matched' if error<=tolerance else 'mismatch')
    import leverage_backup
    from datetime import datetime,timezone
    current=leverage_backup.current_evidence(quote,datetime.fromtimestamp(now/1000,timezone.utc))
    if current:
        with localcontext() as ctx:
            ctx.prec=40;D=lambda k:Decimal(str(i[k]))
            expected=float(D('basisPriceUsd')*D('usdEur')*D('ratio')/D('askNative'))
        add('gearing',calc['value'],expected,max(1e-8,expected*1e-9))
        from product_trade_history import clock
        at=clock(quote.get('leverageAt'));qt=clock(i.get('askAt'))
        # An undated or different-side issuer value cannot validate ask gearing.
        issuer=quote.get('leverage') if (at and qt and abs((at-qt).total_seconds())<=30
            and 0<=now-at.timestamp()*1000<=90000 and not quote.get('leverageEstimated')
            and quote.get('leveragePriceSide')=='ask') else None
        add('issuerGearing',calc['value'] if issuer is not None else None,issuer,0.01)
    else:
        for k in ('gearing','issuerGearing'):add(k,None,None,1e-8)
    at=(quote.get('leverageCalculation') or {}).get('at') or quote.get('bidAt')
    from product_trade_history import clock
    source_at=clock(at);stamp=int(source_at.timestamp()*1000) if source_at else int(now//60000)*60000
    row=dict(metrics=metrics,checkedAt=now,source=quote.get('source'),status='observed')
    conn.execute('''INSERT INTO bob_metric_checks VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
        (VERSION,'product:'+str(quote.get('isin')),stamp,int(now),json.dumps(row)))


def pnl_check(conn,trade_id,product,pair,now):
    metrics={}
    if finite(pair.get('gold')) and pair['gold']>0 and finite(product.get('ko')) and finite(pair.get('koDistancePct')):
        expected=float(abs(Decimal(str(pair['gold']))-Decimal(str(product['ko'])))/Decimal(str(pair['gold']))*100)
        error=abs(expected-pair['koDistancePct'])
        metrics['koDistance']=dict(label=LABELS['koDistance'],actual=pair['koDistancePct'],reference=expected,
            absoluteError=error,tolerance=.000501,status='matched' if error<=.000501 else 'mismatch')
    qty=product.get('quantity');entry=product.get('entry')
    if finite(qty) and qty>0 and finite(entry) and entry>0:
        actual=(pair['estimated']-entry)*qty;reference=(pair['quoted']-entry)*qty
        metrics['pnl']=dict(label=LABELS['pnl'],actual=actual,reference=reference,absoluteError=abs(actual-reference),
            tolerance=.01,status='matched' if abs(actual-reference)<=.01 else 'mismatch')
    if not metrics:return
    row=dict(metrics=metrics,checkedAt=now,source=pair['source'],currency=pair['currency'],
        note='Brutto anhand eingetragener Kaufdaten; keine Gebühren oder bestätigte Ausführung.')
    conn.execute('INSERT INTO bob_metric_checks VALUES(%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
        (VERSION,'trade:'+trade_id,pair['at'],int(now),json.dumps(row)))
