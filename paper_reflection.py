"""Append one factual review per settled paper case; never execute or fit orders."""
import copy
import paper_costs

VERSION = 'paper-reflection-v1'


def record(control, case, now):
    """Called in the same ledger transaction as settlement; replay is harmless."""
    if (case.get('status') == 'open' or case.get('pendingUnits')
            or case.get('demonstration') or case.get('reflection', {}).get('version') == VERSION):
        return
    cost = paper_costs.evaluate(case, paper_costs.SCENARIOS[0])
    stress = paper_costs.evaluate(case, paper_costs.SCENARIOS[1])
    observations = []
    if cost is None:
        observations.append('Produkt-Ergebnis nicht vollständig belegt; nicht als Gewinn oder Verlust lernen.')
    elif cost['grossEur'] > 0 and cost['modelNetEur'] <= 0:
        observations.append('Bruttogewinn wird durch Beispielkosten aufgezehrt; Kostenrobustheit prüfen.')
    elif cost['modelNetEur'] < 0:
        observations.append('Verlust nach Beispielkosten; ein Verlust allein beweist keinen Strategiefehler.')
    else:
        observations.append('Ergebnis nach Beispielkosten nicht negativ; noch kein Nachweis eines dauerhaften Vorteils.')
    kinds = {e.get('kind') for e in case.get('events', [])}
    if 'data-gap' in kinds or case.get('status') == 'inconclusive':
        observations.append('Datenlücke erkannt; unbekannten Verlauf nicht rückwirkend ergänzen.')
    if case.get('exitReason') == 'stop':
        observations.append('Stopp beendet den Versuch; Wiedereinstieg erst mit neuer bestätigter Signal-Kerze.')
    if case.get('exitReason') == 'ko-safety-exit':
        observations.append('KO-Sicherheitsausstieg; betroffenes Produkt bleibt für den Handelstag ausgeschlossen.')
    review = dict(version=VERSION, at=now, caseId=case.get('id'),
                  direction=(case.get('plan') or {}).get('direction'),
                  exitReason=case.get('exitReason'), observations=observations,
                  costModel=cost, stressModel=stress,
                  action='Bestehende Schutzregeln beibehalten; Filter nur nach unabhängiger Validierung übernehmen.')
    case['reflection'] = review
    summary = control.setdefault('reflection', dict(version=VERSION, since=now,
        reviewed=0, evaluated=0, unpriced=0, modelLosses=0, modelNetEur=0., recent=[]))
    summary['reviewed'] += 1
    summary['lastAt'] = now
    if cost is None:
        summary['unpriced'] += 1
    else:
        summary['evaluated'] += 1
        summary['modelLosses'] += int(cost['modelNetEur'] < 0)
        summary['modelNetEur'] += cost['modelNetEur']
    summary['recent'] = (summary['recent'] + [copy.deepcopy(review)])[-20:]
