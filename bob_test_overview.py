"""Read-only index of existing bounded studies. No invented completion or scores."""
from bob_operations import fresh

LABELS = {
 'signals':'Signal-Eingangsdaten', 'signal-outcomes':'Signal-Ausgänge',
 'improvement-trials':'Verbesserungsvergleich', 'list-price-pairs':'Modell gegen Originalkurs',
 'three-stop-study':'Drei Stopp-Varianten', 'stop-target-cases':'Stopp und Ziel',
 'legacy-fast-cautious':'Schnell gegen vorsichtig',
 'ranking-EUR':'Rangliste EUR', 'ranking-CHF':'Rangliste CHF',
 'ranking-exits-EUR':'Ranglisten-Ausstiege EUR', 'ranking-exits-CHF':'Ranglisten-Ausstiege CHF',
 'entry-filter-state':'Einstiegsfilter', 'price-correction-states':'Preiskorrektur'}


def count(value):
    return value if type(value) is int and value >= 0 else None


def snapshot(report, now):
    areas=report.get('areas') or {}
    evidence=areas.get('comparisonEvidence') or {}
    health=areas.get('comparisonHealth') or evidence.get('comparisonHealth') or {}
    rows=[]
    campaign=(areas.get('simulationAndPush') or {}).get('qualityCampaign') or {}
    for item in campaign.get('studies') or []:
        rows.append(dict(id='quality-'+item['id'],label=item['label'],
            state=campaign.get('status','unavailable'),startedAt=campaign.get('startedAt'),
            lastObservedAt=campaign.get('checkedAt'),sampledRecords=item.get('started',item.get('cycles')),
            comparableCases=item.get('complete'),completed=False,truncated=False,
            missing=campaign.get('note'),note='Neue begrenzte Testreihe; keine automatische Regelübernahme.',
            qualityPct=item.get('qualityPct'),inconclusive=item.get('inconclusive'),
            technicalGaps=item.get('missingIntervals'),workerErrors=item.get('workerErrors')))

    for key,label in LABELS.items():
        source=(health.get('items') or {}).get(key) or {}
        counts=source.get('counts') or {}
        comparable=count(counts.get('comparable'))
        rows.append(dict(id=key,label=label,state=source.get('status','unavailable'),
            startedAt=None,lastObservedAt=source.get('latestSampleAt'),
            sampledRecords=count(source.get('sampledRecords')),comparableCases=comparable,
            completed=False,truncated=source.get('truncated') is True,
            missing='Studienbeginn und vollständige Abschlussprüfung nicht belegt.',
            note='Begrenzte Stichprobe; gespeicherte Ausgänge sind kein bestandener Test.'))
    for account in (areas.get('simulationAndPush') or {}).get('accounts',[]):
        recent=account.get('recentCases') or {}
        cases=recent.get('items') or []
        rows.append(dict(id='paper-'+str(account.get('profile')),label='Simulation '+str(account.get('profile')),
            state='completed' if account.get('status')=='completed' else 'checked' if fresh(account.get('checkedAt'),now,120) else 'unavailable',
            startedAt=account.get('startAt'),lastObservedAt=account.get('checkedAt'),
            sampledRecords=len(cases) if recent.get('status')=='observed' else None,
            comparableCases=None,completed=False,truncated=True,
            missing='Abschluss und vollständige Nettoauswertung separat prüfen.',
            note='Aktuelle Eingangsprüfung beweist keinen Einstieg oder Gewinn.'))
    # The independent 2,000 EUR risk study is a real registered test family,
    # not one of the seven main paper ledgers. Keep all three expected delay
    # variants in the inventory even when a variant is missing or stale.
    risk=areas.get('riskPaper') or {}
    risk_accounts={a.get('delaySeconds'):a for a in (risk.get('accounts') or [])
                   if isinstance(a,dict) and a.get('delaySeconds') in (0,30,60)}
    risk_at=risk.get('checkedAt')
    risk_fresh=(risk.get('status') in ('observed','partial')
                and fresh(risk_at,now,120))
    for delay in (0,30,60):
        account=risk_accounts.get(delay) or {}
        observed=risk_fresh and account.get('status')=='observed'
        rows.append(dict(id='risk-paper-'+str(delay),
            label='2.000-Euro-Risikostudie '+str(delay)+' s',
            state='checked' if observed else 'unavailable',
            startedAt=risk.get('startedAt'),lastObservedAt=risk_at,
            sampledRecords=count(account.get('closed')) if observed else None,
            comparableCases=None,completed=False,truncated=True,
            missing='Abschluss und vollständige Nettoauswertung separat prüfen.',
            note='Gespeicherter Modellstand mit angenommenen Kosten; kein Broker-Fill, '
                 'kein verifizierter Gewinn und kein Beleg kontinuierlicher Ausführung.'))
    # The three new studies belong in the existing test inventory. They are
    # independently journalled, not extra live trading portfolios.
    shadow=(areas.get('simulationAndPush') or {}).get('shadowStudies') or {}
    found={item.get('study'):item for item in shadow.get('studies',[])
           if isinstance(item,dict) and item.get('study') in
           ('regime-routing','wait-vs-enter','product-e2e')}
    phase=((areas.get('simulationAndPush') or {}).get('paper') or {}).get('sessionMode')
    for study,label in (
        ('regime-routing','Marktphasen-Vergleich'),
        ('wait-vs-enter','Abwarten gegen Einsteigen'),
        ('product-e2e','1.000 € · vollständiger Goldprodukt-Modellverlauf')):
        data=found.get(study) or {}
        observed=shadow.get('status') in ('observed','partial') and bool(data)
        recent=observed and fresh(data.get('checkedAt'),now,120)
        state=('checked' if recent else 'night-paused'
               if observed and phase in ('night','weekend') else 'unavailable')
        rows.append(dict(id='shadow-'+study,label=label,state=state,
            startedAt=data.get('startedAt'),lastObservedAt=data.get('checkedAt'),
            sampledRecords=count(data.get('eventsRecorded')) if observed else None,
            comparableCases=count(data.get('casesPriced')) if observed else None,
            completed=False,truncated=False,
            missing='Vorwärtsvergleich mit Originalzeitstempeln, ohne Broker-Ausführungsbeleg.',
            note='Jede Papier-Auswertung dauerhaft protokolliert; kein Echtgeld, '
                 'keine bestätigte Nettorendite. Ungeklärte Fälle bleiben ungeklärt.'))
    comparison=shadow.get('entryExitComparison') or {}
    for entry,label in (('early','Frühwarnung'),('confirmed','Bestätigung'),('pullback','Rücksetzer')):
        for exit_mode,exit_label in (('fixed','festes Ziel'),('trailing','nachgezogener Stopp')):
            variants=[(comparison.get('variants') or {}).get(f'{entry}:{exit_mode}:{delay}',{}) for delay in (0,30,60)]
            recent=fresh(comparison.get('checkedAt'),now,120)
            rows.append(dict(id=f'entry-exit-{entry}-{exit_mode}',label=f'{label} · {exit_label} · 0/30/60 s',
                state='checked' if recent else 'night-paused' if comparison.get('checkedAt') and phase in ('night','weekend') else 'unavailable',
                startedAt=None,lastObservedAt=comparison.get('checkedAt'),
                sampledRecords=comparison.get('episodesSampled'),comparableCases=None,
                completed=False,truncated=comparison.get('truncated',False),
                missing='Gepaarte Auswertung und ausreichende neue Fälle erforderlich.',
                note='Nur Spielgeld; angenommene Kosten. Abgeschlossene Varianten: '+str(sum(v.get('closed',0) for v in variants))+'. Kein bestätigter Strategievorteil.'))
    chain_accounts=(evidence.get('accountSamples') or
                    (areas.get('simulationAndPush') or {}).get('accounts',[]))
    chains=[c.get('evidenceChain') for a in chain_accounts
            for c in (a.get('recentCases') or {}).get('items',[]) if isinstance(c.get('evidenceChain'),dict)]
    return dict(version=1,readOnly=True,realOrders=False,items=rows,
        qualityCampaign=campaign,
        entryExitEvaluation=comparison.get("evaluation") or {"version":1,"status":"unavailable"},
        evidenceChains=chains[:35],chainSampleAvailable=bool(chains),
        note='Keine Gesamterfolgsquote: unterschiedliche Tests, Stichproben und unbekannte Ergebnisse bleiben getrennt.',
        releaseNote='Build und veröffentlichte Skripte werden unabhängig geprüft. Ein grüner Build bestätigt keine vollständige fachliche Reparatur.',
        drillNote='Isolierte Tests prüfen Quellenausfall, veraltete Kurse, Wiederanlauf und doppelte Meldungen; kein Ausfall wird im laufenden Bob ausgelöst.')
