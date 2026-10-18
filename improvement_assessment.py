"""Descriptive, versioned evidence review. Never grants a trading approval."""
import random
import math
from collections import defaultdict

VERSION='evidence-review-v1'
LABELS={'collecting':'Daten werden gesammelt','unclear':'Vorteil bisher unklar',
        'worse':'Variante schlechter in den untersuchten Fällen',
        'benefit':'Vorteil in den untersuchten Fällen'}


def regime(payload):
    context=(payload.get('evidence') or {}).get('context') or {}
    adx=context.get('adx');trend=context.get('trend')
    if type(adx) not in (int,float) or not math.isfinite(adx):return 'unknown'
    if adx<20:return 'sideways'
    return {'LONG':'rising','SHORT':'falling'}.get(trend,'unknown')


def interval(rows,scenario=0):
    """Exploratory two-day block bootstrap, not a universal performance proof."""
    daily=defaultdict(list)
    for day,phase,p,o in rows:
        if o:
            s=o['scenarios'][scenario];daily[day].append(s['candidate']-s['baseline'])
    days=sorted(daily)
    if len(days)<20:return None
    blocks=[]
    for i in range(0,len(days),2):
        values=[v for day in days[i:i+2] for v in daily[day]]
        blocks.append((sum(values),len(values)))
    rng=random.Random(20261019);means=[]
    for _ in range(1000):
        draw=rng.choices(blocks,k=len(blocks));means.append(sum(x[0] for x in draw)/sum(x[1] for x in draw))
    means.sort()
    return dict(low=means[24],high=means[974],days=len(days),blocks=len(blocks),
                method='Orientierender 95%-Bereich aus Zweitagesblöcken; keine allgemeine Gewinnzusage.')


def assess(rows,comparison,real,progress,started,reliability):
    current=[r for r in rows if r[2].get('cohort')==comparison['cohort'] and r[1]=='validation']
    done=[r for r in current if r[3]];v=comparison['validation']
    enough=progress[2]==100
    bounds=[interval(done,i) for i in range(2)]
    differences=[s['difference'] for s in v['scenarios']]
    retained=v['retained']/v['count'] if v['count'] else 0
    code='collecting' if not done else 'unclear'
    if enough and all(b is not None for b in bounds):
        if all(d is not None and d<0 for d in differences) and all(b['high']<0 for b in bounds):code='worse'
        elif retained>=.4 and all(d is not None and d>0 for d in differences) and all(b['low']>0 for b in bounds):code='benefit'
    if not started:next_step='Start am 19. Oktober ab 08:00 Schweizer Zeit abwarten; Bob erfasst automatisch.'
    elif reliability['expected'] and (reliability['coveragePct'] or 0)<95:next_step='Bob sammelt weiter. Datenlücken müssen behoben werden, bevor das Qualitätsziel erreicht ist.'
    elif comparison['development']['count']<60 or comparison['development']['days']<10:next_step='Entwicklungsdaten vervollständigen; danach beginnt automatisch die getrennte Prüfung.'
    elif not enough:next_step='Spätere Prüffälle und vollständige Folgekurse sammeln; Regel unverändert lassen.'
    elif real['pairedCount']<20 or real['pairedDays']<10:next_step='Weitere zeitlich zugeordnete Abrechnungen vorhandener Trades auswerten; keine zusätzlichen Trades für die Statistik.'
    elif code=='benefit':next_step='Vorteil einschließlich Produktkosten und Marktphasen gesondert prüfen; noch keine automatische Übernahme.'
    elif code=='worse':next_step='Testvariante nicht übernehmen; Ursache prüfen und einen neuen Versuch getrennt planen.'
    else:next_step='Bisherige Regel beibehalten; für einen Vorteil fehlen eindeutige Nachweise.'
    regimes=[]
    for key,label in [('rising','Steigender Markt'),('falling','Fallender Markt'),('sideways','Seitwärtsmarkt'),('unknown','Marktphase nicht zugeordnet')]:
        selected=[r for r in done if regime(r[2])==key]
        diffs=[r[3]['scenarios'][0]['candidate']-r[3]['scenarios'][0]['baseline'] for r in selected]
        days=len({r[0] for r in selected});mean=sum(diffs)/len(diffs) if diffs else None
        sufficient=len(selected)>=30 and days>=5 and key!='unknown'
        label_result='Noch zu wenige Fälle/Tage' if not sufficient else ('Beobachteter Vorteil' if mean>0 else 'Beobachteter Nachteil' if mean<0 else 'Kein Unterschied')
        regimes.append(dict(key=key,label=label,cases=len(selected),days=days,difference=mean,result=label_result))
    retained_false=sum(r[3]['keep'] and r[3]['directionalPct']<=0 for r in done)
    baseline_false=sum(r[3]['directionalPct']<=0 for r in done)
    return dict(version=VERSION,code=code,label=LABELS[code],nextStep=next_step,
        decision={'collecting':'weiter prüfen','unclear':'weiter prüfen','worse':'Testvariante verwerfen','benefit':'gesonderte Prüfung vorgeschlagen'}[code],
        independentCases=len(done),days=len({r[0] for r in done}),retainedPct=retained*100,
        independenceNote='Ein 60-Minuten-Fall je festem Zweistundenfenster. 30-Sekunden-Messungen sind keine zusätzlichen Testfälle. Fälle können weiterhin zusammenhängen; Unsicherheit wird nach Tagesblöcken betrachtet.',
        intervals=bounds,regimes=regimes,
        falseSignals=dict(baseline=baseline_false,candidate=retained_false,
            baselinePct=100*baseline_false/len(done) if done else None,
            candidatePct=100*retained_false/v['retained'] if v['retained'] else None),
        missedWinners=v['missedGains'],avoidedLosses=v['avoidedLosses'],
        netDifferenceCHF=(real['pairedCandidateCHF']-real['pairedBaselineCHF'] if real['pairedCount'] and all(type(real.get(k)) in (int,float) for k in ('pairedCandidateCHF','pairedBaselineCHF')) else None),
        priceAccuracy='Noch kein eigener Vorher-/Nachher-Nachweis in dieser Kampagne; keine Verbesserung behauptet.',
        automaticRuleChange=False,scope='Spot-Signaltest mit Kostenannahmen; reale Vergleichswerte betreffen nur tatsächlich gehandelte Fälle.')
