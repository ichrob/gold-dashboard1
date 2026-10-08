"""Offline comparison of frozen shadow records, not a DEGIRO strategy backtest.

python candle_study.py study.json --test-from-ms TIMESTAMP --cost-bps 0
Input: {"observations": [BOB_CANDLE_SHADOW JSON records], "bars_by_tf": {...}}
The cutoff must be chosen before inspecting outcomes. Test records are never used
to tune wick-context-v1. Returns are in the underlying, not leveraged products.
"""
import argparse
import json
from candle_shadow import STEPS, VERSION, analyze, number


def early_hints(data, test_from_ms, cost_bps=0):
    """Exploratory wick hints, equal clock horizon within each pair; no live signals."""
    results={}
    observations=data.get('observations',[])
    def verified(tf):
        rows=data.get('bars_by_tf',{}).get(tf,[])
        out=[];used=set()
        for r in sorted((x for x in observations if x.get('timeframe')==tf and number(x.get('observedAt'))),key=lambda x:x['observedAt']):
            at=r.get('candleAt');seen=r['observedAt']
            if not number(at) or (r.get('instrument'),at) in used or r.get('version')!=VERSION or r.get('affectsSelection') is not False:continue
            check=analyze([b for b in rows if number(b.get('openTime')) and b['openTime']<=at],tf,seen)
            if check.get('status')!='observed' or check.get('direction')!=r.get('direction') or check.get('instrument')!=r.get('instrument'):continue
            used.add((r.get('instrument'),at));out.append(r)
        return out
    for fast,slow in [('1m','5m'),('30m','1h')]:
        hints,context=verified(fast),verified(slow)
        step=STEPS[fast];horizon=3*STEPS[slow];count=horizon//step
        totals=dict(evaluated=0,positive=0,nonpositive=0,missingOutcome=0,missingContext=0,laterConfirmations=0)
        returns=[];leads=[];next_at=0
        rows=data.get('bars_by_tf',{}).get(fast,[])
        for r in hints:
            seen=r['observedAt'];direction=r['direction']
            if seen<test_from_ms or seen<next_at or direction not in ('LONG','SHORT'):continue
            prior=[x for x in context if x['instrument']==r['instrument'] and x['observedAt']<=seen and seen-x['closedAt']<=STEPS[slow]]
            if not prior:totals['missingContext']+=1;continue
            if prior[-1]['direction']==direction:continue
            future=[b for b in rows if number(b.get('openTime')) and b['openTime']>=seen][:count]
            if len(future)!=count:totals['missingOutcome']+=1;continue
            start=future[0]['openTime']
            valid=start-seen<=step and all(b['openTime']==start+i*step and b.get('instrument')==r['instrument'] and not b.get('estimated') and b.get('isOpen') is False and all(number(b.get(k)) for k in ('open','high','low','close')) and b['low']<=min(b['open'],b['close']) and b['high']>=max(b['open'],b['close']) for i,b in enumerate(future))
            if not valid:totals['missingOutcome']+=1;continue
            value=(future[-1]['close']/future[0]['open']-1)*10000*(1 if direction=='LONG' else -1)-cost_bps
            returns.append(value);totals['evaluated']+=1
            totals['positive' if value>0 else 'nonpositive']+=1
            later=[x for x in context if x['instrument']==r['instrument'] and seen<x['observedAt']<=start+horizon and x['direction']==direction]
            if later:
                leads.append((later[0]['observedAt']-seen)/60000);totals['laterConfirmations']+=1
            next_at=start+horizon
        results[fast+'_'+slow]={**totals,'horizonMinutes':horizon/60000,'meanNetBps':sum(returns)/len(returns) if returns else None,'meanObservedLeadMinutes':sum(leads)/len(leads) if leads else None,'status':'ausgewertet' if returns else 'noch keine auswertbaren Fälle'}
    return {'pairs':results,'definition':'Früher Docht-Hinweis bei noch nicht gleichgerichteter größerer Zeitebene. Nichtpositiver Verlauf nach Kostenannahme = Fehlstart-Proxy, kein Stop-Loss-Test. Zeitvorsprung nur gegenüber später tatsächlich protokollierten Bestätigungen. 1m: 15 Minuten Folgeverlauf; 30m: 180 Minuten. Paarergebnisse nicht direkt als Rangliste vergleichen. Keine Aussage über längere Trendteilnahme oder Produktrendite.'}


def compare(data, test_from_ms, cost_bps=0):
    if not number(test_from_ms) or not isinstance(cost_bps, (int,float)) or cost_bps<0:
        raise ValueError('Ungültiger Testbeginn oder Kostenannahme')
    import math
    if not math.isfinite(cost_bps):raise ValueError('Ungültige Kostenannahme')
    output={}
    for tf,step in STEPS.items():
        bars=data.get('bars_by_tf',{}).get(tf,[])
        records=sorted((r for r in data.get('observations',[])
                        if r.get('timeframe')==tf and number(r.get('observedAt'))),
                       key=lambda r:r['observedAt'])
        baseline=[];retained=[];removed=[];used=set();next_at=0
        for r in records:
            seen=r['observedAt'];candle=r.get('candleAt');direction=r.get('baselineDirection')
            if (seen<test_from_ms or seen<next_at or r.get('version')!=VERSION
                    or r.get('status')!='observed' or r.get('affectsSelection') is not False
                    or direction not in ('LONG','SHORT') or not number(candle)
                    or not candle+step<=seen<=candle+2*step):continue
            key=(r.get('instrument'),candle)
            if key in used:continue
            used.add(key)
            # Validate original context with only history available at observation.
            past=[b for b in bars if number(b.get('openTime')) and b['openTime']<=candle]
            check=analyze(past,tf,seen)
            if (check.get('status')!='observed' or check.get('direction')!=r.get('direction')
                    or check.get('instrument')!=r.get('instrument')):continue
            # First bar open after observation; never enter retrospectively.
            future=[b for b in bars if number(b.get('openTime')) and b['openTime']>=seen][:3]
            if len(future)!=3 or future[0]['openTime']-seen>step:continue
            start=future[0]['openTime']
            if any(b['openTime']!=start+i*step or b.get('instrument')!=r['instrument']
                   or b.get('isOpen') is not False
                   or not all(number(b.get(k)) for k in ('open','high','low','close'))
                   or b['low']>min(b['open'],b['close']) or b['high']<max(b['open'],b['close'])
                   for i,b in enumerate(future)):continue
            value=(future[-1]['close']/future[0]['open']-1)*10000*(1 if direction=='LONG' else -1)-cost_bps
            baseline.append(value)
            conflicts=r['direction'] in ('LONG','SHORT') and r['direction']!=direction
            (removed if conflicts else retained).append(value)
            # Same non-overlapping opportunities for both arms.
            next_at=start+3*step
        def summary(values):
            return {'count':len(values),'meanNetBps':sum(values)/len(values) if values else None,
                    'positiveFraction':sum(v>0 for v in values)/len(values) if values else None}
        output[tf]={'baseline':summary(baseline),'withConflictFilter':summary(retained),
                    'removed':summary(removed),'removedPositive':sum(v>0 for v in removed),
                    'removedNonpositive':sum(v<=0 for v in removed)}
    return {'version':VERSION,'testFromMs':test_from_ms,'roundTripCostBps':cost_bps,
            'scope':'Explorative MTF-Richtungsprüfung am Basiswert; keine Produktfreigabe, kein Profitabilitätsnachweis',
            'horizonBars':3,'byTimeframe':output,
            'earlyHints':early_hints(data,test_from_ms,cost_bps)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input');parser.add_argument('--test-from-ms',type=int,required=True)
    parser.add_argument('--cost-bps',type=float,default=0)
    args=parser.parse_args()
    with open(args.input,encoding='utf-8') as f:data=json.load(f)
    print(json.dumps(compare(data,args.test_from_ms,args.cost_bps),ensure_ascii=False,indent=2,allow_nan=False))
