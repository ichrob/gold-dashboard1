"""Fixed prospective timing hypothesis, using persisted MBO observations only."""
import math

VERSION='entry-path-v1-20261019'
PROTOCOL=dict(version=VERSION,horizons=[5,15,30,60],priorMinutes=15,extensionPct=.30,
              earlierMinutes=5,costPct=[.04,.12],automaticRuleChange=False,
              scope='Last 30 fixed two-hour MBO trials; descriptive comparison, no adoption gate')


def finite(v):return type(v) in (int,float) and math.isfinite(v)


def good(r):
    return (r.get('valid') is True and finite(r.get('price')) and r['price']>0
            and finite(r.get('at')) and finite(r.get('priceAt'))
            and 0<=r['at']-r['priceAt']<=90000)


def point(rows,target,before=None):
    return next((r for r in sorted(rows,key=lambda r:r.get('priceAt') or 0)
                 if good(r) and target<=r['priceAt']<=target+90000
                 and r['at']<=target+180000 and (before is None or r['at']<=before)),None)


def evaluate(base,rows,now):
    at=base['at'];ready=base.get('ready') is True and base.get('direction') in ('LONG','SHORT')
    sign=1 if base.get('direction')=='LONG' else -1
    same=[r for r in rows if r.get('cohort')==base.get('cohort')]
    prior=point(same,at-900000,before=at)
    early=point(same,at-300000,before=at)
    extension=(base['price']/prior['price']-1)*100*sign if good(base) and ready and prior else None
    keep=extension<PROTOCOL['extensionPct'] if extension is not None else None
    result=dict(at=at,direction=base.get('direction') if ready else 'ABWARTEN',
                priorMovePct=extension,candidateKeep=keep,horizons=[],coveragePct=None,
                observedAdversePct=None,observedFavorablePct=None,comparison=[],earlierComparison=[],
                earlierDirection=early.get('direction') if early and early.get('ready') else None,
                label='Ergebnis noch offen')
    if not good(base):
        result['label']='Ausgangsnachweis fehlt';return result
    for minutes in PROTOCOL['horizons']:
        due=at+minutes*60000
        end=point(same,due,before=now)
        move=(end['price']/base['price']-1)*100 if end else None
        result['horizons'].append(dict(minutes=minutes,status='observed' if end else 'missing' if now>due+180000 else 'pending',
            sourceAt=end['priceAt'] if end else None,movePct=move,directionalPct=move*sign if move is not None and ready else None))
    # Extrema are observed samples, never claimed continuous highs/lows.
    path=[r for r in same if good(r) and at<r['priceAt']<=at+3600000 and r['at']<=min(now,at+3690000)]
    buckets={int((r['priceAt']-at-1)//30000) for r in path}
    expected=max(0,min(120,int((now-at)//30000)))
    result['coveragePct']=round(min(1,len(buckets)/expected)*100,1) if expected else None
    if path and ready:
        changes=[(r['price']/base['price']-1)*100*sign for r in path]
        result['observedAdversePct']=min(0,min(changes));result['observedFavorablePct']=max(0,max(changes))
    end=point(same,at+3600000,before=now)
    if end:
        if ready and keep is not None:
            gross=(end['price']/base['price']-1)*100*sign
            result['comparison']=[dict(costPct=c,baseline=gross-c,candidate=gross-c if keep else 0) for c in PROTOCOL['costPct']]
            result['label']='Ungünstiger 60-Minuten-Verlauf nach Kosten' if gross-PROTOCOL['costPct'][0]<0 else 'Positiver 60-Minuten-Verlauf nach Kosten'
        elif not ready:result['label']='ABWARTEN: Verlauf nur beschreibend'
        else:result['label']='Vorheriger Kursnachweis fehlt'
        if early and early.get('ready') is True and early.get('direction') in ('LONG','SHORT'):
            early_gross=(end['price']/early['price']-1)*100*(1 if early['direction']=='LONG' else -1)
            base_gross=(end['price']/base['price']-1)*100*sign if ready else None
            result['earlierComparison']=[dict(costPct=c,earlier=early_gross-c,baseline=base_gross-c if ready else 0) for c in PROTOCOL['costPct']]
    elif now>at+3780000:result['label']='Folgenachweis fehlt'
    return result


def read(conn,campaign,now):
    stored=conn.execute('SELECT payload FROM bob_improvement_protocol WHERE id=%s',(VERSION,)).fetchone()
    if not stored or stored[0]!=PROTOCOL:raise ValueError('Entry path protocol mismatch')
    trials=conn.execute('''SELECT slot,phase,payload FROM bob_improvement_trials WHERE campaign=%s
        ORDER BY slot DESC LIMIT 30''',(campaign,)).fetchall()
    # One indexed join, bounded to 30 windows; transfer only the necessary fields.
    samples=conn.execute('''WITH trials AS (SELECT slot,payload FROM bob_improvement_trials
        WHERE campaign=%s ORDER BY slot DESC LIMIT 30)
        SELECT t.slot,jsonb_build_object('at',o.payload->'at','priceAt',o.payload->'priceAt',
        'price',o.payload->'price','valid',o.payload->'valid','ready',o.payload->'ready',
        'direction',o.payload->'direction','cohort',o.payload->'cohort')
        FROM trials t JOIN bob_improvement_observations o ON o.campaign=%s
        AND o.slot BETWEEN t.slot-900000 AND t.slot+3900000 ORDER BY t.slot,o.slot''',(campaign,campaign)).fetchall()
    grouped={}
    for slot,row in samples:grouped.setdefault(slot,[]).append(row)
    items=[dict(evaluate(base,grouped.get(slot,[]),now),phase=phase,cohort=base.get('cohort')) for slot,phase,base in trials]
    groups=[]
    for phase in ('development','validation'):
        for cohort in sorted({r['cohort'] for r in items if r.get('cohort')}):
            selected=[r for r in items if r['phase']==phase and r['cohort']==cohort]
            paired=[r for r in selected if r['comparison']]
            early=[r for r in selected if r['earlierComparison']]
            groups.append(dict(phase=phase,cohort=cohort,cases=len(selected),paired=len(paired),earlyPairs=len(early),
                avoidedLosses=sum(r['candidateKeep'] is False and r['comparison'][0]['baseline']<0 for r in paired),
                missedGains=sum(r['candidateKeep'] is False and r['comparison'][0]['baseline']>0 for r in paired),
                earlierLosses=sum(r['earlierComparison'][0]['earlier']<0 for r in early),
                scenarios=[dict(costPct=c,difference=sum(r['comparison'][i]['candidate']-r['comparison'][i]['baseline'] for r in paired)/len(paired) if paired else None,
                    earlierDifference=sum(r['earlierComparison'][i]['earlier']-r['earlierComparison'][i]['baseline'] for r in early)/len(early) if early else None) for i,c in enumerate(PROTOCOL['costPct'])]))
    return dict(protocol=PROTOCOL,items=items,groups=groups,note='Feste Forschungsvariante: Signal auslassen bei mindestens 0,30 % vorheriger Bewegung in Signalrichtung innerhalb von 15 Minuten. Letzte 30 geplante Fälle, kein Gesamterfolgsnachweis. Frühvergleich: damals freigegebenes Signal fünf Minuten früher bis zum gemeinsamen Endpunkt, also längere Haltedauer. Originalzeiten innerhalb 90 Sekunden; fehlende Nachweise bleiben offen. Rückläufe sind nur beobachtete Stichproben, keine vollständigen Intrabar-Verläufe. Spotkosten 0,04/0,12 % sind Annahmen; keine Produktrendite und keine automatische Regelübernahme.')
