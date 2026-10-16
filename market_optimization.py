"""Prospective market diagnostics; frozen inputs, observed spot outcomes only."""
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = 'market-review-v1'
HORIZONS = (1, 5, 15, 30)
LABELS = {'baseline':'Aktuelle Regel', 'early':'Frühimpuls ergänzend',
          'regime':'Marktphasenfilter', 'timing':'Einstiegsfilter'}


def num(v):
    return type(v) in (int, float) and math.isfinite(v)


def milliseconds(v):
    if num(v):return v
    try:
        parsed=datetime.fromisoformat(v.replace('Z','+00:00'))
        return parsed.timestamp()*1000 if parsed.tzinfo else None
    except (ValueError,TypeError,AttributeError,OverflowError):return None


def capture(r):
    old = r['optimization']
    q = r.get('entryQuality') or {}
    at = r['recordedAt']
    stamp = q.get('priceAt')
    fresh = (q.get('available') is True and num(stamp) and 0 <= at-stamp <= 300000)
    atr = q.get('atr5m') if fresh else None
    atr = atr if num(atr) and atr > 0 else None
    base = r['direction']
    timing = ('NEUTRAL' if base == 'NEUTRAL' else
              q.get('direction') if fresh and q.get('direction') in (base, 'NEUTRAL') else None)
    price_at=milliseconds(r.get('priceAt'))
    return dict(version=VERSION, atr5m=atr, atrAt=stamp if atr else None,
                regime=old['regime'], reason=old['reason'], blockers=old['blockers'],
                variants={k:old['variants'][k] for k in ('baseline','early','regime')} | {'timing':timing},
                entry={k:q.get(k) if fresh else None for k in ('deviationAtr','roomR','signalAgeMinutes')},
                entryReasons=[str(x)[:200] for x in (q.get('reasons') or [])[:5]] if fresh else [],
                inputFresh=price_at is not None and 0 <= at-price_at <= 60000,
                automaticRuleChange=False)


def report(rows, score, now=None):
    now=time.time()*1000 if now is None else now
    ordered=sorted((r for r,_ in rows if r.get('origin')=='background'),key=lambda r:r['recordedAt'])
    groups={}; moves=[]; reasons={}; sampled=0; last=None; pending=0; missing=0; atr_missing=0
    for r, truths in sorted(rows,key=lambda row:row[0]['recordedAt']):
        f=r.get('marketOptimization') or {}; at=r['recordedAt']
        if r.get('origin')!='background' or f.get('version')!=VERSION:continue
        # Longest horizon + its maximum observation tolerance; sample before
        # looking at outcomes and keep all variants on a common cohort.
        if last is not None and at-last<31*60000:continue
        last=at;sampled+=1
        phase='validation' if datetime.fromtimestamp(at/1000,ZoneInfo('Europe/Zurich')).date().isoformat()>='2026-10-26' else 'collection'
        evidence=r.get('_marketReviewTruths') or {}
        results={}
        values=f['variants']
        reason='; '.join(f['blockers']) or f['reason']
        if values['baseline']=='NEUTRAL':reasons[reason]=reasons.get(reason,0)+1
        if f.get('atr5m') is None:atr_missing+=1
        for h in HORIZONS:
            truth=evidence.get(h,evidence.get(str(h)))
            if h==15 and truth is None:truth=truths[0] if truths else None
            result=score(r,truth,h) if f.get('inputFresh') else None
            # A 1-minute result must not actually be an almost 2-minute price.
            if result and h==1 and milliseconds(result['at'])>at+90000:result=None
            if not result or any(values.get(k) not in ('LONG','SHORT','NEUTRAL') for k in LABELS):
                if now<at+h*60000+(30000 if h==1 else 60000):pending+=1
                else:missing+=1
                continue
            results[h]=result
            change=result['changePct']
            group=groups.setdefault((phase,f['regime'],h),dict(cases=0,variants={k:dict(signals=0,wait=0,sumPct=0.,wins=0,losses=0) for k in LABELS}))
            group['cases']+=1
            for k,d in values.items():
                m=group['variants'][k]
                value=(change if d=='LONG' else -change)-.04 if d!='NEUTRAL' else 0.
                m['sumPct']+=value;m['signals']+=d!='NEUTRAL';m['wait']+=d=='NEUTRAL'
                m['wins']+=d!='NEUTRAL' and value>0;m['losses']+=d!='NEUTRAL' and value<0
            # ATR is a fixed, prior 5m reference, not a forecast or a
            # time-scaled volatility estimate. Preserve fixed threshold too.
            atr=f.get('atr5m');strength=abs(change)*r['price']/100/atr if atr else None
            strong_fixed=abs(change)>=.15;strong_atr=strength is not None and strength>=1
            direction='LONG' if change>0 else 'SHORT' if change<0 else 'NEUTRAL'
            if (strong_fixed or strong_atr) and (values['baseline']!=direction or f['blockers']):
                later=next((x for x in ordered if at<x['recordedAt']<=at+h*60000 and x.get('marketEvaluable') and x.get('direction')==direction),None)
                moves.append(dict(at=at,horizon=h,direction=direction,changePct=change,moveAtr=strength,
                    fixedThreshold=strong_fixed,atrThreshold=strong_atr,reason=reason,
                    alreadyPresent=values['baseline']==direction,
                    delayMinutes=(later['recordedAt']-at)/60000 if later else None,
                    entry=f['entry'],entryReasons=f['entryReasons']))
        # Endpoint reversal only; no claim about unobserved intraperiod paths.
        if 1 in results and 30 in results:
            first=results[1]['changePct'];end=results[30]['changePct']
            for item in moves:
                if item['at']==at:item['endpointReversal']=first*end<0
    return dict(version=VERSION,sampled=sampled,pending=pending,missing=missing,atrMissing=atr_missing,
        labels=LABELS,horizons=list(HORIZONS),groups=[dict(phase=p,regime=g,horizon=h,**v) for (p,g,h),v in groups.items()],
        moves=moves[-20:],moveCount=len(moves),waitReasons=reasons,automaticRuleChange=False,
        note='Neue Fälle, mindestens 31 Minuten Abstand. Je Zeitraum dieselben Fälle für alle Varianten. '
        'Bewegungsschwellen: 0,15 % oder 1 vorher bekannte 5m-ATR; keine Gewinnprognose. '
        'Mittelwerte nach beispielhaften 0,04 % Spotkosten, keine Produktrendite. '
        '1-Minuten-Folgekurs maximal 30 s später, sonst maximal 60 s. Fehlende Werte werden ausgeschlossen. '
        'Richtungsumkehr vergleicht nur 1-/30-Minuten-Endpunkte; Zwischenbewegungen bleiben unbekannt. '
        'Verzögerung bedeutet später protokolliertes Signal, nicht den tatsächlichen Bewegungsbeginn. '
        'Keine automatische Regelübernahme; Prüfung ab 26.10.2026 separat.')
