"""Descriptive diagnostics and frozen prospective single-filter comparisons. No trading."""
from datetime import datetime
from zoneinfo import ZoneInfo
import math
VERSION='signal-review-v1'
# Fixed protocol: collection days before this date, later days are untouched validation.
VALIDATION_DAY='2026-10-19'
LABELS={'baseline':'Bestehende Regel','trend':'Zusätzlich intakter 1h/15m-Trend in Signalrichtung','adx':'Zusätzlich 5m-Wilder-ADX mindestens 25'}

def capture(r):
    t=r.get('trendContext') or {};i=r.get('indicators') or {};d=r.get('direction')
    adx=i.get('adx');known=isinstance(adx,(int,float)) and not isinstance(adx,bool) and math.isfinite(adx)
    return dict(version=VERSION,validationDay=VALIDATION_DAY,baseline=d,
        trend=(d if t.get('intact') and t.get('direction')==d else 'NEUTRAL') if t.get('available') else None,
        adx=(d if adx>=25 else 'NEUTRAL') if known else None)

def diagnostics(rows,score):
    groups={};examples=[];seen=set()
    for r,truths in sorted(rows,key=lambda x:(x[0].get('origin')!='background',x[0].get('recordedAt',0))):
        if r.get('direction') not in ('LONG','SHORT'):continue
        key=r.get('barAt')
        if key in seen:continue
        seen.add(key)
        t=r.get('trendContext') or {};i=r.get('indicators') or {}
        tags=['Richtung '+r['direction'],'Phase '+str(t.get('phase','UNKNOWN'))]
        if not r.get('marketEvaluable'):tags.append('Kurszeit/Preis nicht auswertbar')
        if t.get('available') and t.get('hourDirection') in ('LONG','SHORT') and t['hourDirection']!=r['direction']:tags.append('Gegen Stundenrichtung')
        if t.get('phase')=='RANGE':tags.append('Seitwärtsphase')
        if t.get('phase')=='WEAKENING':tags.append('Trend geschwächt')
        for h,truth in zip((15,60,240),truths):
            result=score(r,truth,h);v=result.get('directionalPct') if result else None
            for tag in tags:
                g=groups.setdefault((h,tag),dict(horizon=h,label=tag,win=0,loss=0,flat=0,missing=0))
                g['missing' if v is None else 'win' if v>0 else 'loss' if v<0 else 'flat']+=1
            if v is not None and v<0 and len(examples)<30:
                examples.append(dict(at=r.get('recordedAt'),direction=r['direction'],horizon=h,changePct=v,tags=tags,reason=r.get('reason'),priceAt=r.get('priceAt')))
    return dict(groups=list(groups.values()),examples=examples,note='Deskriptive Hinweise, keine bewiesenen Fehlerursachen. Gleiche Kerze einmal, Hintergrund bevorzugt; aufeinanderfolgende Kerzen können abhängig sein. Ein verspäteter Einstieg ist ohne unabhängige Referenz nicht bewiesen.')

def prospective(rows,score):
    phases={p:{k:dict(cases=0,kept=0,filtered=0,wins=0,losses=0,flat=0,sumPct=0.,avoidedLoss=0,missedWin=0,missing=0) for k in LABELS} for p in ('collection','validation')}
    records=sorted((x for x in rows if (x[0].get('reviewVariants') or {}).get('version')==VERSION and x[0].get('origin')=='background'),key=lambda x:x[0]['recordedAt'])
    last=None
    for r,truths in records:
        if last is not None and r['recordedAt']-last<3600000:continue
        # Select samples before looking at outcomes, including missing outcomes.
        last=r['recordedAt']
        if r.get('direction') not in ('LONG','SHORT'):continue
        day=datetime.fromtimestamp(r['recordedAt']/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
        phase='validation' if day>=VALIDATION_DAY else 'collection'
        result=score(r,truths[1],60);v=result.get('directionalPct') if result else None
        for k in LABELS:
            m=phases[phase][k];d=r['reviewVariants'].get(k)
            if v is None or d is None:m['missing']+=1;continue
            keep=d==r['direction'];m['cases']+=1;m['kept' if keep else 'filtered']+=1
            value=v if keep else 0;m['sumPct']+=value
            if keep:m['wins' if v>0 else 'losses' if v<0 else 'flat']+=1
            else:m['avoidedLoss']+=v<0;m['missedWin']+=v>0
    return dict(version=VERSION,labels=LABELS,phases=phases,validationDay=VALIDATION_DAY,automaticRuleChange=False,
        note='Nur ab Aktivierung eingefrorene Hintergrundsignale. Je Variante genau ein Zusatzfilter; keine rückwirkende Anpassung. Gemeinsame 60-Minuten-Folgekurse, mindestens eine Stunde Abstand. Ab 19.10.2026 separate Validierung; fehlende Evidenz ausgeschlossen. Kein automatischer Sieger oder Regelwechsel; keine Gebühren/Produktrendite. Erster Richtungsfall je UTC-Stunde aus dem gesamten verfügbaren 30-Tage-Archiv; zusätzlich mindestens eine Stunde Abstand. Historie rolliert nach 30 Tagen aus.')
