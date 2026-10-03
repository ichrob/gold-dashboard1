"""Experimental OHLC observations. Never used by selection, scoring or push.

Thresholds are frozen research hypotheses, not empirically calibrated probabilities.
Only observed OHLC history is accepted; estimated futures snapshots are not inputs.
"""
import json
import math
import threading
import time
from collections import OrderedDict

VERSION = 'wick-context-v1'
STEPS = {'5m': 300000, '15m': 900000, '1h': 3600000}
_seen = OrderedDict()
_lock = threading.Lock()


def number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def analyze(bars, tf, now_ms=None):
    now_ms = time.time()*1000 if now_ms is None else now_ms
    out = dict(version=VERSION, mode='shadow', affectsSelection=False,
               timeframe=tf, status='unavailable', direction='NEUTRAL',
               reason='Keine verwendbaren abgeschlossenen OHLC-Kerzen')
    step = STEPS.get(tf)
    if not step or not isinstance(bars, list):
        return out
    closed = []
    for bar in bars:
        if not isinstance(bar, dict):
            return out
        ts = bar.get('openTime')
        if not number(ts) or ts % step:
            out['reason'] = 'Ungültige Kerzenzeit'
            return out
        if ts > now_ms:
            out['reason'] = 'Kerzenzeit liegt in der Zukunft'
            return out
        if bar.get('isOpen') is True or ts+step > now_ms:
            continue
        if bar.get('isOpen') is not False:
            out['reason'] = 'Kerzenschluss nicht bestätigt'
            return out
        if not all(number(bar.get(k)) for k in ('open', 'high', 'low', 'close')):
            out['reason'] = 'Ungültige OHLC-Werte'
            return out
        o, h, l, c = (bar[k] for k in ('open', 'high', 'low', 'close'))
        if l > min(o, c) or h < max(o, c) or l > h:
            out['reason'] = 'Widersprüchliche OHLC-Werte'
            return out
        if bar.get('instrument') not in ('XAU/USD', 'GC=F') or bar.get('estimated'):
            out['reason'] = 'Unbekannter Basiswert oder geschätzte Kerzen'
            return out
        closed.append(bar)
    if len(closed) < 21:
        out['reason'] = 'Mindestens 21 abgeschlossene Kerzen erforderlich'
        return out
    # Never silently sort duplicate/reversed evidence or bridge missing candles.
    if any(b['openTime'] <= a['openTime'] for a, b in zip(closed, closed[1:])):
        out['reason'] = 'Doppelte oder ungeordnete Kerzenzeiten'
        return out
    window = closed[-21:]
    if len({b['instrument'] for b in window}) != 1:
        out['reason'] = 'Basiswertwechsel im Analysefenster'
        return out
    if any(b['openTime']-a['openTime'] != step for a, b in zip(window, window[1:])):
        out['reason'] = 'Lücke im Analysefenster; keine Dochtbewertung'
        return out
    b = window[-1]
    out.update(instrument=b['instrument'], candleAt=b['openTime'],
               closedAt=b['openTime']+step)
    if now_ms-out['closedAt'] > step:
        out['reason'] = 'Abgeschlossene Kerze zu alt'
        return out
    previous = window[:-1]
    atr = sum(max(x['high']-x['low'], abs(x['high']-p['close']),
                  abs(x['low']-p['close']))
              for p, x in zip(window[-16:-2], window[-15:-1]))/14
    width = b['high']-b['low']
    if width <= 0 or atr <= 0:
        out['reason'] = 'Keine auswertbare Handelsspanne'
        return out
    body = abs(b['close']-b['open'])/width
    upper = (b['high']-max(b['open'], b['close']))/width
    lower = (min(b['open'], b['close'])-b['low'])/width
    position = (b['close']-b['low'])/width
    support = min(x['low'] for x in previous)
    resistance = max(x['high'] for x in previous)
    near_support = abs(b['low']-support) <= .25*atr and b['close'] > support
    near_resistance = abs(b['high']-resistance) <= .25*atr and b['close'] < resistance
    direction, reason = 'NEUTRAL', 'Kein eindeutiger Docht-Hinweis an einer Preiszone'
    if width < .5*atr:
        reason = 'Kerze im Verhältnis zur Volatilität zu klein'
    elif body <= .3 and upper >= .3 and lower >= .3:
        reason = 'Beidseitige Dochte: unentschlossenes Kerzenbild'
    elif lower >= .55 and body <= .35 and position >= .7 and near_support:
        direction, reason = 'LONG', 'Untere Zurückweisung an vorheriger Unterstützung'
    elif upper >= .55 and body <= .35 and position <= .3 and near_resistance:
        direction, reason = 'SHORT', 'Obere Zurückweisung an vorherigem Widerstand'
    out.update(status='observed', direction=direction, reason=reason,
               metrics=dict(bodyFraction=body, upperFraction=upper,
                            lowerFraction=lower, closePosition=position,
                            rangeAtr=width/atr, priorAtr=atr,
                            support=support, resistance=resistance))
    return out


def snapshot(history, baseline=None, now_ms=None, emit=True):
    """Freeze one observation per source/timeframe/close in this process.

    Baseline is existing MTF context, NOT full product selection or trade return.
    Logs are research evidence; process memory is bounded and not durable storage.
    """
    now_ms = time.time()*1000 if now_ms is None else now_ms
    result = dict(version=VERSION, mode='shadow', affectsSelection=False,
                  checkedAt=now_ms, byTimeframe={})
    for tf in STEPS:
        row = analyze(history.get(tf, []), tf, now_ms)
        base = (baseline or {}).get(tf, {})
        direction = base.get('dir') if base.get('available') else 'NEUTRAL'
        row['baselineDirection'] = direction
        row['agreement'] = ('unclear' if 'NEUTRAL' in (direction, row['direction'])
                            else 'supports' if direction == row['direction'] else 'conflicts')
        result['byTimeframe'][tf] = row
        if emit and row['status'] == 'observed':
            key = (VERSION, row['instrument'], tf, row['candleAt'])
            with _lock:
                if key not in _seen:
                    _seen[key] = True
                    if len(_seen) > 4096:
                        _seen.popitem(last=False)
                    print('BOB_CANDLE_SHADOW '+json.dumps(dict(row, observedAt=now_ms),
                          ensure_ascii=False, allow_nan=False), flush=True)
    return result


PANEL = r'''<script>
(()=>{
 const anchor=document.getElementById('blockStructure')?.parentElement;
 if(!anchor)return;
 const panel=document.createElement('details');
 const title=document.createElement('summary');title.textContent='Kerzenbild · Testbetrieb';
 const info=document.createElement('div');info.className='small';
 info.textContent='Nur Beobachtung. Kein Einfluss auf Freigabe oder Push. Nutzen noch nicht nachgewiesen.';
 const output=document.createElement('div');output.className='small';
 panel.append(title,info,output);anchor.append(panel);
 let busy=false;
 async function refresh(){
  if(busy||document.visibilityState==='hidden'||!panel.open)return;
  busy=true;const ctl=new AbortController();const timeout=setTimeout(()=>ctl.abort(),8000);
  try{
   const response=await fetch('/api/live',{cache:'no-store',signal:ctl.signal});
   if(!response.ok)throw Error('Daten fehlen');
   const data=(await response.json()).candleShadow;
   if(!data||Date.now()-data.checkedAt>120000)throw Error('Testdaten fehlen oder sind veraltet');
   output.replaceChildren();
   for(const tf of ['5m','15m','1h']){
    const r=data.byTimeframe[tf],line=document.createElement('p');
    const label=r.status==='observed'?(r.direction==='NEUTRAL'?'unklar':r.direction+'-Hinweis'):'nicht verfügbar';
    line.textContent=tf+' · '+(r.instrument||'Quelle offen')+' · '+label+' — '+r.reason+
      (r.closedAt?' · Kerzenschluss '+new Date(r.closedAt).toLocaleString():'')+
      (r.agreement==='supports'?' · passt zur MTF-Richtung':r.agreement==='conflicts'?' · widerspricht der MTF-Richtung':'');
    output.append(line);
   }
  }catch(_){output.textContent='Kerzen-Testdaten nicht verfügbar. Keine bestätigte Aussage.';}
  finally{clearTimeout(timeout);busy=false;}
 }
 panel.addEventListener('toggle',refresh);setInterval(refresh,60000);
})();
</script>'''
