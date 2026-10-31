"""Read-only interpretation of the fixed prospective MBO trials."""
import math


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def entry(phase,base,outcome,followup,now):
    at=base.get('at');due=at+3600000 if finite(at) else None
    valid=base.get('valid') is True and finite(base.get('price')) and base['price']>0
    ready=base.get('ready') is True and base.get('direction') in ('LONG','SHORT')
    row=dict(at=at,phase=phase,decision=base.get('direction') if ready else 'ABWARTEN',
        reason=base.get('reason') or 'Kein gespeicherter Entscheidungsgrund',
        sourceAt=base.get('priceAt'),price=base.get('price'),adx=base.get('adx'),
        cohort=base.get('cohort'),build=base.get('build'),evidence=base.get('evidence') or {},
        status='pending',result='Folgebeobachtung nach 60 Minuten steht aus.',
        lesson='Noch keine Bewertung möglich.',directionalPct=None,netSpotPct=None,
        marketMovePct=None,outcomeAt=None)
    if not valid or due is None:
        row.update(status='invalid',result='Ausgangsdaten nicht gültig.',lesson='Datenlücke prüfen; keine Aussage zur Qualität der Entscheidung.')
    elif ready and outcome and finite(outcome.get('directionalPct')):
        scenarios=outcome.get('scenarios') or []
        standard=next((s for s in scenarios if s.get('costPct')==.04),None)
        net=standard.get('baseline') if standard else None
        row.update(status='evaluated',directionalPct=outcome['directionalPct'],netSpotPct=net,outcomeAt=outcome.get('at'))
        if not finite(net):row.update(status='missing',result='Kostenvergleich fehlt.',lesson='Ergebnis unvollständig; keine Bewertung.')
        elif base.get('keep') is False:
            row.update(result='Testfilter hätte das Signal ausgelassen.',lesson=('Filter hätte ein negatives Spot-Ergebnis vermieden.' if net<0 else 'Filter hätte ein positives Spot-Ergebnis ausgelassen.' if net>0 else 'Auslassen hätte im Standardvergleich keinen Unterschied gemacht.'))
        else:
            row.update(result='Bisherige Regel und Testfilter behalten das Signal.',lesson=('Signal nach angenommenen Kosten negativ: als Prüffall sammeln.' if net<0 else 'Signal nach angenommenen Kosten positiv: als Prüffall sammeln.' if net>0 else 'Nach angenommenen Kosten ausgeglichen.'))
    elif not ready and followup and valid_followup(base,followup):
        move=(followup['price']/base['price']-1)*100
        row.update(status='observed',marketMovePct=move,outcomeAt=followup['priceAt'],result='Marktbewegung nach ABWARTEN beobachtet.',lesson='Beschreibender Verlauf, kein Beleg für einen handelbaren verpassten Gewinn. Damals lag kein freigegebenes Richtungssignal vor.')
    elif due is not None and now>due+180000:
        row.update(status='missing',result='Gültiger Folgenachweis fehlt.',lesson='Nicht als Erfolg oder Misserfolg zählen; Originalnachweis fehlt.')
    return row


def valid_followup(base,row):
    due=base['at']+3600000
    return (row.get('valid') is True and finite(row.get('price')) and row['price']>0
            and finite(row.get('priceAt')) and due<=row['priceAt']<=due+90000
            and finite(row.get('at')) and due<=row['at']<=due+180000)


def read(conn,campaign,now):
    trials=conn.execute('''SELECT phase,payload,outcome FROM bob_improvement_trials
        WHERE campaign=%s ORDER BY slot DESC LIMIT 30''',(campaign,)).fetchall()
    rows=[]
    for phase,base,outcome in trials:
        followup=None
        if base.get('valid') and not base.get('ready') and finite(base.get('at')):
            due=base['at']+3600000
            # PK campaign/slot bounds cap each read at seven scheduled observations.
            candidates=conn.execute('''SELECT payload FROM bob_improvement_observations
                WHERE campaign=%s AND valid AND slot BETWEEN %s AND %s ORDER BY slot LIMIT 8''',
                (campaign,due//30000*30000,due+180000)).fetchall()
            followup=next((__import__('cold_observations').resolve(conn,p) for (p,) in candidates if valid_followup(base,p)),None)
        rows.append(entry(phase,base,outcome,followup,now))
    return dict(items=rows,limit=30,horizonMinutes=60,
        note='Letzte 30 fest geplante Prüffälle im Zweistundentakt, keine vollständige Signalliste. Entwicklung und spätere unabhängige Prüfung bleiben getrennt. Ergebnisse beziehen sich auf Gold-Spot nach 60 Minuten; 0,04 % Standardkosten sind eine Annahme, keine Produktrendite. Einzelne Fälle ändern keine Regel. Ob ein Einstieg zu spät war, lässt sich aus diesem Endpunkt allein nicht beurteilen.')
