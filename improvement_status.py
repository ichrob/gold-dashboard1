"""Compact read-only operational evidence; no trading permissions or invented health."""
import time
import background_push
import decision_audit
import paper_health


def summarize(report, paper, rows, now):
    quality=report.get('dataQuality') or {}
    latest=report.get('latestCapture') or {}
    phase=background_push.degiro_session(now)
    last=latest.get('priceAt')
    fresh=latest.get('valid') is True and type(last) in (int,float) and 0<=now-last<=90000
    product_ok=(quality.get('status')=='ok' and quality.get('total',0)>0
                and quality.get('freshPct')==100 and quality.get('completePct')==100)
    data_state=('paused' if phase!='trading' else 'ok' if fresh and product_ok else 'waiting')
    counts=dict(evaluated=0,pending=0,invalidStart=0,missingFollowup=0)
    for record,truths in rows:
        at=decision_audit.milliseconds(record.get('recordedAt'))
        for horizon in (15,60,240):
            if at is None or not record.get('marketEvaluable'):
                counts['invalidStart']+=1
            elif now<at+(horizon+1)*60000:
                counts['pending']+=1
            elif decision_audit.outcome(record,truths.get(horizon),horizon) is not None:
                counts['evaluated']+=1
            else:counts['missingFollowup']+=1
    missing=counts['invalidStart']+counts['missingFollowup']
    repair=report.get('repairQuality') or {}
    known=repair.get('status')=='ok'
    cards=[
        dict(key='data',label='Daten vollständig und aktuell',state=data_state,
             detail='Planmässige Pause ausserhalb 08–22 Uhr; keine Live-Aktualität bestätigt.' if phase!='trading'
             else 'Aktuelle Erfassung und vollständige Produktdaten bestätigt.' if data_state=='ok'
             else 'Aktuelle Erfassung oder vollständige Produktnachweise noch offen.'),
        dict(key='tests',label='Tests auswertbar',state='open' if missing else 'ok' if counts['evaluated'] else 'waiting',
             detail=f"{counts['evaluated']} auswertbar · {counts['pending']} noch nicht fällig · {missing} ohne vollständigen Nachweis. Letzte {len(rows)} Entscheidungen, je 15/60/240 Minuten."),
        dict(key='simulation',label='Simulation aktiv',state=paper.get('state','unavailable'),
             detail='Planmässig pausiert; kein Nachweis eines aktuellen Handelsdurchlaufs.' if paper.get('state')=='paused'
             else f"{paper.get('accountsChecked',0)}/{paper.get('accountsTotal',5)} Konten mit gespeichertem Prüfzeitpunkt. Status bestätigt nur den Ablauf, keine Gewinne."),
        dict(key='improvement',label='Verbesserung nachgewiesen',state='candidate' if (report.get('assessment') or {}).get('code')=='benefit' else 'waiting',
             detail='Signalvorteil im untersuchten Vergleich; Produkt-Nettonutzen muss gesondert bestätigt werden.' if (report.get('assessment') or {}).get('code')=='benefit'
             else 'Noch kein belastbarer Verbesserungsnachweis; Auswertung läuft.')]
    return dict(available=True,checkedAt=now,cards=cards,counts=counts,
                openErrorTypes=repair.get('testProblemTypes') if known else None,
                affectedCases=repair.get('testCases') if known else None,
                note='Fehlerarten und betroffene Fälle sind getrennte Zahlen. Historische Lücken bleiben erhalten.')


def read(conn, report, now=None):
    now=int(time.time()*1000) if now is None else now
    decisions=conn.execute('SELECT id,payload FROM bob_decision_audit ORDER BY recorded_at DESC LIMIT 200').fetchall()
    outcomes={}
    if decisions:
        for key,horizon,truth in conn.execute('''SELECT decision_id,horizon,truth FROM bob_decision_outcomes
            WHERE decision_id=ANY(%s::text[]) AND horizon IN (15,60,240)''',([r[0] for r in decisions],)).fetchall():
            outcomes.setdefault(key,{})[horizon]=truth
    latest=conn.execute('SELECT payload FROM bob_improvement_observations WHERE campaign=%s ORDER BY slot DESC LIMIT 1',
                        (report['protocol']['version'],)).fetchone()
    current={**report,'latestCapture':__import__('cold_observations').resolve(conn,latest[0]) if latest else {}}
    return summarize(current,paper_health.snapshot(conn,now),
                     [(r,outcomes.get(key,{})) for key,r in decisions],now)
