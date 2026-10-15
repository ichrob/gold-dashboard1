"""Read-only integrity and conversion diagnostics for Bob's shared market bundle.

A report is not a trade gate. Source times are never refreshed by this module.
"""
import math
from datetime import datetime, timezone

STEPS={'1m':60000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'4h':14400000}


def numeric(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def timestamp(at):
    try:
        if type(at) is not str:return None
        parsed=datetime.fromisoformat(at.replace('Z','+00:00'))
        return parsed.timestamp()*1000 if parsed.tzinfo else None
    except (ValueError,OverflowError):
        return None


def frame_health(raw, tf, now_ms):
    step=STEPS[tf]
    rows=[b for b in (raw or []) if isinstance(b,dict) and not b.get('isOpen')]
    rows=[b for b in rows if type(b.get('openTime')) in (float,int)
          and b['openTime']+step<=now_ms]
    rows=rows[-220:]
    count=len(rows)
    if not count:return dict(state='missing',closed=0,ema200='missing',lastClosedAt=None)
    last=rows[-1]
    identity=all(b.get('instrument')=='XAU/USD' and not b.get('estimated') for b in rows)
    valid=all(
        type(b.get('openTime')) in (int,float)
        and math.isfinite(b['openTime']) and b['openTime']%step==0
        and all(numeric(b.get(k)) for k in ('open','high','low','close'))
        and b['low']<=min(b['open'],b['close'])
        and b['high']>=max(b['open'],b['close'])
        and b['low']<=b['high']
        and (i==0 or rows[i-1]['openTime']<b['openTime'])
        for i,b in enumerate(rows))
    recent_contiguous=count>=3 and all(
        b['openTime']-a['openTime']==step for a,b in zip(rows[-3:-1],rows[-2:]))
    age=now_ms-last['openTime']
    fresh=step<=age<=step*2
    state=('wrong-basis' if not identity else 'invalid-ohlc' if not valid
           else 'recent-gap' if not recent_contiguous else 'stale' if not fresh
           else 'insufficient' if count<100 else 'ok')
    return dict(state=state,closed=count,ema200='available' if state=='ok' and count>=200 else 'context-unavailable',
                lastClosedAt=int(last['openTime']),ageSeconds=round(age/1000,1),
                source=last.get('source') or 'Quellenangabe fehlt')


def compare_spot_to_close(spot, frames, now_ms):
    price=spot.get('xaus')
    quote_at=timestamp(spot.get('spot_price_as_of'))
    bars=(frames.get('5m') or [])
    valid=[b for b in bars if isinstance(b,dict) and not b.get('isOpen')
           and b.get('instrument')=='XAU/USD' and not b.get('estimated')
           and type(b.get('openTime')) in (int,float)
           and b['openTime']+300000<=now_ms and all(numeric(b.get(k)) for k in ('open','high','low','close'))]
    if not valid or not numeric(price) or quote_at is None or not 0<=now_ms-quote_at<=60000:
        return dict(status='not-comparable',reason='Spot- oder bestätigte 5m-Schlussdaten fehlen')
    valid.sort(key=lambda b:b['openTime'])
    last=valid[-1]
    bar_close_at=last['openTime']+300000
    gap=abs(quote_at-bar_close_at)/1000
    # A spot tick minutes after the close is not a simultaneous comparison.
    if gap>90 or quote_at<bar_close_at:
        return dict(status='not-comparable',reason='Original-Kurszeiten nicht hinreichend gleich',clockGapSeconds=round(gap,1))
    if len(valid)<16:return dict(status='not-comparable',reason='ATR14 aus 5m-Kerzen nicht vorhanden')
    recent=valid[-15:]
    if any(b['openTime']-a['openTime']!=300000 for a,b in zip(recent[:-1],recent[1:])):
        return dict(status='not-comparable',reason='5m-Kerzen für ATR14 lückenhaft')
    ranges=[max(recent[i]['high']-recent[i]['low'],
                abs(recent[i]['high']-recent[i-1]['close']),
                abs(recent[i]['low']-recent[i-1]['close'])) for i in range(1,15)]
    atr=sum(ranges)/14
    threshold=max(3*atr,0.0025*last['close'])
    diff=abs(price-last['close'])
    return dict(status='deviation' if diff>threshold else 'aligned',
                clockGapSeconds=round(gap,1),absoluteDifferenceUsd=round(diff,5),
                warningThresholdUsd=round(threshold,5),spotAt=spot.get('spot_price_as_of'),
                closeAt=datetime.fromtimestamp(bar_close_at/1000,timezone.utc).isoformat(),
                note='Nur Plausibilitätsvergleich, keine Handelsfreigabe')


def fx_health(spot, now_ms):
    usd_eur,usd_chf=spot.get('usd_eur'),spot.get('usd_chf')
    m=spot.get('usd_eur_meta') or {}
    # The existing conversion API returns a *fetch* time, not a separate quote time.
    source_at=timestamp(m.get('sourceAt'))
    fetched_at=timestamp(m.get('fetchedAt'))
    age=None if source_at is None else (now_ms-source_at)/1000
    rates_ok=numeric(usd_eur) and numeric(usd_chf)
    state=('missing' if not rates_ok else 'source-time-unknown' if source_at is None
           else 'current' if 0<=age<=90 else 'stale')
    return dict(state=state,usdEur=usd_eur if numeric(usd_eur) else None,
                usdChf=usd_chf if numeric(usd_chf) else None,
                eurPerChf=round(usd_eur/usd_chf,9) if rates_ok else None,
                formula='CHF→EUR = CHF × (USD/EUR ÷ USD/CHF)',
                sourceAt=m.get('sourceAt'),fetchedAt=m.get('fetchedAt'),
                sourceClockVerified=source_at is not None and state=='current',
                indicative=True,
                note='FX-Abrufzeit ist kein unabhängiger Quellenzeitstempel; Produktfreigabe separat prüfen.')


def review(bundle, now=None):
    now_ms=(datetime.now(timezone.utc).timestamp() if now is None else now)*1000
    spot=bundle.get('spots') or {}
    frames=(bundle.get('history') or {}).get('bars_by_tf') or {}
    detail={tf:frame_health(frames.get(tf),tf,now_ms) for tf in ('1m','5m','15m','30m','1h')}
    spot_time=timestamp(spot.get('spot_price_as_of'))
    spot_ok=(spot.get('is_genuine_xauusd_spot') is True and not spot.get('spot_error')
             and numeric(spot.get('xaus')) and spot_time is not None
             and 0<=now_ms-spot_time<=60000)
    comparison=compare_spot_to_close(spot,frames,now_ms) if spot_ok else dict(
        status='not-comparable',reason='Gold-Spot nicht aktuell bestätigt')
    fx=fx_health(spot,now_ms)
    warnings=[]
    if not spot_ok:warnings.append('Gold-Spot fehlt oder ist veraltet')
    for tf in ('5m','15m','1h'):
        if detail[tf]['state']!='ok':warnings.append(tf+': '+detail[tf]['state'])
        if detail[tf]['ema200']!='available':warnings.append(tf+': EMA200-Kontext <200 bestätigte Kerzen oder nicht aktuell')
    if comparison['status']=='deviation':warnings.append('Abweichung Spot / 5m-Schluss – Quellenvergleich nötig')
    if fx['state']!='current':warnings.append('FX-Quellenzeit nicht aktuell unabhängig nachgewiesen')
    return dict(version='market-input-review-v1',readOnly=True,affectsTradeApproval=False,
                checkedAt=datetime.fromtimestamp(now_ms/1000,timezone.utc).isoformat(),
                spot=dict(state='ok' if spot_ok else 'unavailable',at=spot.get('spot_price_as_of'),
                          source=spot.get('primary') or spot.get('goldprice_status')),
                frames=detail,spotComparison=comparison,fx=fx,
                warnings=warnings[:12])
