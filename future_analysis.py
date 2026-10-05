"""Contract-specific, closed-bar GCZ26 analysis; never spot/continuous history.

Yahoo's exchange history is delayed. Spot nowcasts are not fed into indicators
and are not counted as a second technical confirmation source.
"""
import copy
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError, URLError
from email.utils import parsedate_to_datetime

SYMBOL='GCZ26.CMX'
CONTRACT='GCZ26'
_lock=threading.Lock()
_thread=None
_active_until=0
_state={}
_chart_locks = {('5m', '5d'): threading.Lock(), ('1h', '6mo'): threading.Lock()}
_chart_cache = {}
_chart_retry = {}
_chart_failures = {}
_chart_errors = {}


def parse_chart(payload,minutes,now=None):
    now=now or datetime.now(timezone.utc)
    chart=payload['chart']['result'][0];meta=chart['meta']
    if (meta['symbol']!=SYMBOL or meta['instrumentType']!='FUTURE'
            or meta['currency']!='USD' or meta['exchangeName']!='CMX'
            or meta.get('shortName')!='Gold Dec 26'
            or meta.get('dataGranularity')!=str(minutes)+'m' and not(minutes==60 and meta.get('dataGranularity')=='1h')):
        raise ValueError('Futures-Historie gehört nicht zum bestätigten GCZ26-Kontrakt')
    market_at=meta['regularMarketTime']
    if isinstance(market_at,bool) or not isinstance(market_at,(int,float)) or not 0<=now.timestamp()-market_at<=1800:
        raise ValueError('GCZ26-Handelsdaten zu alt oder Kurszeit zukünftig')
    quote=chart['indicators']['quote'][0];step=minutes*60
    rows=[]
    for i,ts in enumerate(chart['timestamp']):
        try:
            if isinstance(ts,bool) or not isinstance(ts,int) or ts%step or ts+step>min(now.timestamp(),market_at):continue
            o,h,l,c=[float(quote[k][i]) for k in ('open','high','low','close')]
            if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)) or l>min(o,c) or h<max(o,c) or l>h:continue
            rows.append(dict(t=ts,open=o,high=h,low=l,close=c))
        except (KeyError,ValueError,TypeError,IndexError):continue
    if len({r['t'] for r in rows})!=len(rows):raise ValueError('Doppelte Futures-Kerzen')
    return sorted(rows,key=lambda r:r['t']),market_at


def _fetch_chart(interval,range_value):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+SYMBOL+'?interval='+interval+'&range='+range_value
    with urlopen(Request(url,headers={'User-Agent':'Bob/2.0 contract history','Accept':'application/json'}),timeout=10) as response:
        if not response.url.startswith('https://query1.finance.yahoo.com/v8/finance/chart/'+SYMBOL+'?'):
            raise ValueError('Unerwartete Futures-Historien-Weiterleitung')
        body=response.read(3_000_001)
    if len(body)>3_000_000:raise ValueError('Futures-Historie zu groß')
    return json.loads(body)


def fetch_chart(interval, range_value):
    """Single shared request per chart/minute across reference and analysis.

    Cache hits preserve all original provider timestamps. Backoff applies to
    every consumer; a reference request cannot bypass the history retry gate.
    """
    key = (interval, range_value)
    if key not in _chart_locks:
        raise ValueError('Nicht registrierte GCZ26-Historienabfrage')
    with _chart_locks[key]:
        now = time.monotonic()
        cached = _chart_cache.get(key)
        if cached and now-cached[0] < 60:
            return copy.deepcopy(cached[1])
        if now < _chart_retry.get(key, 0):
            raise URLError('GCZ26-Datenquelle in gemeinsamer Wartezeit')
        try:
            value = _fetch_chart(interval, range_value)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            failures = _chart_failures.get(key, 0)+1
            _chart_failures[key] = failures
            _chart_errors[key] = history_error(exc)
            _chart_retry[key] = time.monotonic()+retry_delay(exc, failures)
            raise
        _chart_cache[key] = (time.monotonic(), copy.deepcopy(value))
        _chart_failures[key] = 0
        _chart_retry[key] = 0
        _chart_errors.pop(key, None)
        return value


def reference_failure(exc):
    """Share the provider retry deadline; consumers must not extend it."""
    key = ('5m', '5d')
    with _chart_locks[key]:
        remaining = _chart_retry.get(key, 0)-time.monotonic()
        if remaining > 0:
            return max(1, math.ceil(remaining)), _chart_errors.get(key, history_error(exc))
    # A successfully downloaded but stale/invalid quote can change on the
    # next ordinary poll. It is not a transport failure or a rate limit.
    delay = 60 if isinstance(exc, (ValueError, KeyError, TypeError, IndexError)) else retry_delay(exc, 1)
    return delay, history_error(exc)


def fetch_reference(now=None):
    """Use the existing exact-contract history feed's dated last-trade quote."""
    payload = fetch_chart('5m', '5d')
    _, market_at = parse_chart(payload, 5, now)
    meta = payload['chart']['result'][0]['meta']
    value = meta['regularMarketPrice']
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('GCZ26-Referenzkurs nicht verwendbar')
    return dict(contract=CONTRACT, underlying='Gold Future Dec 2026', underlyingType='FUTURE',
                underlyingPriceUsd=float(value),
                underlyingAt=datetime.fromtimestamp(market_at, timezone.utc).isoformat(),
                source='Yahoo Finance · GCZ26.CMX · verzögerter Börsenkurs',
                sourceUrl='https://finance.yahoo.com/quote/'+SYMBOL+'/',
                isExchangeRealtime=False, eligible=False)


def aggregate(rows,base_minutes,target_minutes):
    step=target_minutes*60;groups={}
    for row in rows:groups.setdefault(row['t']//step*step,[]).append(row)
    out=[];expected=target_minutes//base_minutes
    for ts,items in sorted(groups.items()):
        if len(items)!=expected or [r['t'] for r in items]!=[ts+i*base_minutes*60 for i in range(expected)]:continue
        out.append(dict(t=ts,open=items[0]['open'],high=max(r['high'] for r in items),
                        low=min(r['low'] for r in items),close=items[-1]['close']))
    return out


def ema_series(values,period):
    k=2/(period+1);out=[values[0]]
    for value in values[1:]:out.append(value*k+out[-1]*(1-k))
    return out


def rsi(values,period=14):
    diffs=[b-a for a,b in zip(values,values[1:])]
    gain=sum(max(v,0) for v in diffs[:period])/period
    loss=sum(max(-v,0) for v in diffs[:period])/period
    for d in diffs[period:]:gain=(gain*(period-1)+max(d,0))/period;loss=(loss*(period-1)+max(-d,0))/period
    return 50 if gain==loss==0 else 100 if loss==0 else 100-100/(1+gain/loss)


def frame(rows,minutes,now):
    if len(rows)<220:return dict(available=False,direction='NEUTRAL',reason='Weniger als 220 abgeschlossene Kontrakt-Kerzen',bars=len(rows))
    closed_at=rows[-1]['t']+minutes*60
    if not 0<=now.timestamp()-closed_at<=1800+minutes*60:
        return dict(available=False,direction='NEUTRAL',reason='Kontrakt-Historie veraltet',bars=len(rows))
    values=[r['close'] for r in rows[-500:]]
    e20,e50,e200=[ema_series(values,p)[-1] for p in (20,50,200)]
    mac=[a-b for a,b in zip(ema_series(values,12),ema_series(values,26))]
    signal=ema_series(mac,9)[-1];hist=mac[-1]-signal;strength=rsi(values)
    trend='LONG' if e20>e50>e200 else 'SHORT' if e20<e50<e200 else 'NEUTRAL'
    momentum='LONG' if hist>0 and 50<=strength<75 else 'SHORT' if hist<0 and 25<strength<=50 else 'NEUTRAL'
    direction=trend if trend==momentum else 'NEUTRAL'
    tr=[max(r['high']-r['low'],abs(r['high']-prev['close']),abs(r['low']-prev['close'])) for prev,r in zip(rows,rows[1:])]
    atr=sum(tr[:14])/14
    for v in tr[14:]:atr=(atr*13+v)/14
    return dict(available=True,direction=direction,trend=trend,momentum=momentum,rsi=strength,
                ema20=e20,ema50=e50,ema200=e200,macd=mac[-1],macdSignal=signal,macdHistogram=hist,
                price=values[-1],atr=atr,bars=len(rows),closedAt=datetime.fromtimestamp(closed_at,timezone.utc).isoformat(),
                expiresAt=datetime.fromtimestamp(closed_at+1800+minutes*60,timezone.utc).isoformat())


def structure(rows):
    pivots=[]
    for i in range(2,len(rows)-2):
        r=rows[i];neighbors=rows[i-2:i]+rows[i+1:i+3]
        if all(r['high']>n['high'] for n in neighbors):pivots.append(dict(kind='high',value=r['high'],t=r['t']))
        if all(r['low']<n['low'] for n in neighbors):pivots.append(dict(kind='low',value=r['low'],t=r['t']))
    highs=[p for p in pivots if p['kind']=='high'];lows=[p for p in pivots if p['kind']=='low']
    direction='NEUTRAL'
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1]['value']>highs[-2]['value'] and lows[-1]['value']>lows[-2]['value']:direction='LONG'
        if highs[-1]['value']<highs[-2]['value'] and lows[-1]['value']<lows[-2]['value']:direction='SHORT'
    fib=dict(direction='NEUTRAL',levels={})
    if pivots:
        last=pivots[-1];prior=[p for p in pivots[:-1] if p['kind']!=last['kind'] and p['t']<last['t']]
        if prior:
            a=prior[-1];b=last;up=a['kind']=='low' and b['value']>a['value'];down=a['kind']=='high' and b['value']<a['value']
            if up or down:
                fib=dict(direction='LONG' if up else 'SHORT',fromAt=a['t'],toAt=b['t'],
                         levels={str(level):b['value']+(a['value']-b['value'])*level for level in (.382,.5,.618,.786)})
    return direction,fib


def analyse(five,hourly,market_at,now=None):
    now=now or datetime.now(timezone.utc)
    frames={tf:frame(rows,minutes,now) for tf,rows,minutes in
            [('5m',five,5),('15m',aggregate(five,5,15),15),('1h',hourly,60),('4h',aggregate(hourly,60,240),240)]}
    valid=all(frames[tf]['available'] for tf in ('5m','15m','1h'))
    directions=[frames[tf]['direction'] for tf in ('5m','15m','1h')]
    overall=directions[0] if valid and directions[0] in ('LONG','SHORT') and len(set(directions))==1 else 'NEUTRAL'
    market_structure,fib=structure(five[-200:])
    f5,f1=frames['5m'],frames['1h']
    expires=min([now.timestamp()+180,market_at+1800]+[
        datetime.fromisoformat(v['expiresAt']).timestamp() for tf,v in frames.items() if tf!='4h' and v['available']])
    blocks=dict(trend=f1.get('trend','NEUTRAL'),momentum=f5.get('momentum','NEUTRAL'),
                fibonacci=fib['direction'],mtf=overall,volatility='NEUTRAL',marketStructure=market_structure)
    return dict(contract=CONTRACT,available=valid,direction=overall,frames=frames,blocks=blocks,
                fibonacci=fib,atr=f5.get('atr'),rsi=f5.get('rsi'),macdHistogram=f5.get('macdHistogram'),
                source='Yahoo Finance · GCZ26.CMX · verzögerte Börsenhistorie',
                sourceUrl='https://finance.yahoo.com/quote/GCZ26.CMX/',technicalSourceFamilies=1,
                checkedAt=now.isoformat(),expiresAt=datetime.fromtimestamp(expires,timezone.utc).isoformat(),
                reason='Intraday-MTF 1h/15m/5m bestätigt auf abgeschlossenen GCZ26-Kerzen; 4h nur Hintergrund' if overall!='NEUTRAL' else 'ABWARTEN: Kontrakt-MTF unvollständig oder uneinheitlich',
                note='Spot-Kursschätzung zählt nicht als zusätzliche technische Bestätigung. Historie ist verzögert.')


def _collect():
    global _state
    failures=0
    while True:
        started=time.monotonic()
        wait_seconds=60
        with _lock:active=started<_active_until
        if active:
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    a=pool.submit(fetch_chart,'5m','5d');b=pool.submit(fetch_chart,'1h','6mo')
                    five,at5=parse_chart(a.result(),5);hourly,at1=parse_chart(b.result(),60)
                state=analyse(five,hourly,min(at5,at1))
                failures=0
            except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
                failures+=1
                wait_seconds=retry_delay(exc,failures)
                state=dict(contract=CONTRACT,available=False,direction='NEUTRAL',
                           reason=history_error(exc),retryAfterSeconds=wait_seconds)
            with _lock:_state=state
        threading.Event().wait(max(1,wait_seconds-(time.monotonic()-started)))


def retry_delay(exc, failures, now=None):
    now=time.time() if now is None else now
    delay=min(1800,60*2**min(max(failures,1),5))
    if isinstance(exc,HTTPError) and exc.code==429:
        delay=max(300,delay)
        header=exc.headers.get('Retry-After','') if exc.headers else ''
        try:
            seconds=int(header) if str(header).isdigit() else parsedate_to_datetime(header).timestamp()-now
            delay=max(delay,min(86400,max(0,seconds)))
        except (ValueError,TypeError,OverflowError):pass
    return delay


def history_error(exc):
    # Expose only a controlled error class/status, never upstream bodies,
    # headers, URLs, or potentially sensitive exception representations.
    if isinstance(exc, HTTPError):
        return 'GCZ26-Historie: Datenanbieter antwortet mit HTTP '+str(exc.code)
    if isinstance(exc, (TimeoutError, URLError)):
        return 'GCZ26-Historie: Verbindung zum Datenanbieter fehlgeschlagen oder Zeitlimit erreicht'
    if isinstance(exc, ValueError):
        # parse_chart's identity/freshness checks contain only fixed messages.
        message=str(exc)
        if message in ('Futures-Historie gehört nicht zum bestätigten GCZ26-Kontrakt',
                       'GCZ26-Handelsdaten zu alt oder Kurszeit zukünftig',
                       'Doppelte Futures-Kerzen', 'Unerwartete Futures-Historien-Weiterleitung',
                       'Futures-Historie zu groß'):
            return message
    return 'GCZ26-Historie: Antwort fehlt oder Datenformat nicht verwendbar'


def ensure_collector():
    global _thread,_active_until
    with _lock:
        _active_until=time.monotonic()+3600
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_collect,name='bob-gcz26-history',daemon=True);_thread.start()


def current(now=None):
    now=now or datetime.now(timezone.utc)
    with _lock:out=copy.deepcopy(_state)
    if not out:out=dict(contract=CONTRACT,available=False,direction='NEUTRAL',reason='Kontrakt-Historie wird geladen')
    if out.get('available') and datetime.fromisoformat(out['expiresAt'])<now:
        out.update(available=False,direction='NEUTRAL',reason='Kontraktspezifische Analyse veraltet')
    return out
