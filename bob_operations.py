"""Read-only reconciliation of bounded diagnostics; never trading approval.

An absent observation is unknown. An issue is never closed merely because the
product list looks complete. All clocks remain the clocks of their own source.
"""
import math
import time
from datetime import datetime


def stamp(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.timestamp() if parsed.tzinfo else None
        except ValueError:
            return None
    if type(value) in (int, float) and math.isfinite(value) and value > 0:
        return value / 1000 if value > 100000000000 else value
    return None


def fresh(value, now, seconds):
    at = stamp(value)
    return at is not None and 0 <= now-at <= seconds


def snapshot(report, now=None):
    now = time.time() if now is None else now
    areas = report.get('areas') or {}
    products = areas.get('products') or {}
    index = areas.get('problems') or {}
    product_fresh = products.get('status') == 'ok' and fresh(products.get('lastCheckedAt'), now, 300)
    index_fresh = index.get('status') == 'ok' and fresh(index.get('checkedAt'), now, 1200)
    items = [p for p in (products.get('items') or [])[:500] if isinstance(p, dict)]
    conflicts = [dict(isin=p.get('isin'), fields=[k for k in (p.get('fieldRecovery') or {}).get('conflicts', []) if k in ('ko','strike','ratio','currency')],
                      checkedAt=(p.get('fieldRecovery') or {}).get('checkedAt'),
                      sourceDecisions=(p.get('fieldRecovery') or {}).get('sourceDecisions', {}),
                      resolution='Originalquellen abgleichen; maßgebliche Quelle noch nicht bestätigt.')
                 for p in items if (p.get('fieldRecovery') or {}).get('state') == 'conflict']
    for entry in conflicts:
        decisions = entry['sourceDecisions']
        if decisions and all(d.get('state') == 'dated-issuer-selected' for d in decisions.values()):
            entry['resolution'] = 'Heute datierte Emittentenangabe gewählt; abweichende undatierte Vergleichswerte bleiben sichtbar. Keine zusätzliche Handelsfreigabe.'
    complete = product_fresh and bool(items) and products.get('total') == len(items) and products.get('incomplete') == 0
    cases = {}
    for row in (index.get('items') or [])[:100]:
        if not isinstance(row, dict) or not isinstance(row.get('code'), str):
            continue
        code = row['code']
        phase = row.get('kiStatus')
        state = {'in-progress':'in-progress', 'testing':'testing', 'needs-user':'needs-user',
                 'waiting-for-evidence':'blocked', 'waiting-for-review':'review'}.get(phase, 'new')
        comparison = 'not-compared'
        if code.startswith('product-'):
            comparison = ('source-conflict' if product_fresh and conflicts else
                          'current-list-complete-issue-evidence-review-required' if complete else
                          'current-product-evidence-not-complete')
        # Group duplicate categories while preserving all incident references.
        entry = cases.setdefault(code, dict(code=code, state=state, issueNumbers=[], occurrences=0,
            comparison=comparison, issueUpdatedAt=row.get('updatedAt'), repairVerified=False))
        entry['occurrences'] += 1
        if type(row.get('number')) is int and row['number'] not in entry['issueNumbers']:
            entry['issueNumbers'].append(row['number'])
        # Never hide a user action or blocked sibling behind a less urgent duplicate.
        rank = {'needs-user':6,'blocked':5,'testing':4,'in-progress':3,'review':2,'new':1}
        if rank[state] > rank[entry['state']]: entry['state'] = state
    jobs = []
    for key, label, source, clock, interval in (
        ('background','Überwachung',areas.get('background') or {},'lastSuccessAt',30),
        ('collection','Datensammlung',areas.get('collection') or {},'lastCycleAt',30),
        ('research','Forschungsprüfung',areas.get('strategyResearch') or {},'lastSuccessAt',None)):
        at = source.get(clock)
        period = source.get('updateIntervalSeconds', interval)
        if type(period) not in (int,float) or not math.isfinite(period) or period <= 0: period = None
        original = stamp(at)
        recent = fresh(at, now, max(120, period*2+60) if period else 900)
        paused = source.get('monitorStatus') == 'paused' or source.get('state') == 'paused'
        failure = source.get('status') in ('unavailable','failed') or bool(source.get('error'))
        jobs.append(dict(id=key,label=label,state='paused' if paused else 'unavailable' if failure else 'observed' if recent else 'unknown',
            lastSuccessAt=at if clock == 'lastSuccessAt' else None,
            lastObservedAt=at, observationKind='successful-cycle' if clock == 'lastSuccessAt' else 'collection-cycle-not-success-proof',
            expectedNextAt=original+period if original and period and recent and not paused else None,
            nextAttemptConfirmed=False))
    sim = areas.get('simulationAndPush') or {}
    jobs.append(dict(id='simulation',label='Simulation',state='unavailable' if sim.get('status') != 'observed' else 'observed',
        lastSuccessAt=None,lastObservedAt=None,expectedNextAt=None,nextAttemptConfirmed=False,
        observationKind='readable-snapshot-not-continuous-execution-proof'))
    actions = [dict(code=c['code'], text='Deine Hilfe ist nach Bobs Prüfung nötig. Details im Bereich Probleme.',view='problems')
               for c in cases.values() if index_fresh and c['state'] == 'needs-user']
    return dict(version=1, observedAt=report.get('observedAt'), readOnly=True, realOrders=False,
        productStatus=dict(state='unknown' if not product_fresh else 'conflict' if conflicts else 'complete' if complete else 'incomplete',
                           checkedAt=products.get('lastCheckedAt'), conflicts=conflicts,
                           tradeApproved=False),
        cases=list(cases.values()), problemIndexFresh=index_fresh,
        actions=actions, actionStatus='known' if index_fresh else 'unknown', jobs=jobs,
        historicalPolicy=dict(state='closed-without-result-only-after-documented-review',
            reopen='new-original-evidence-only', contributesToProfit=False,
            note='Fehlende Daten allein schließen keinen Fall. Begründeter historischer Abschluss bleibt getrennt von Reparatur und Handelsergebnis.'),
        comparisonPolicy=dict(automaticRuleChange=False, productNetValidated=False,
            metrics=['Signalverluste im Spotmodell','Signalverzögerung','Stopp-/Zielprüfung','Ergebnis nach belegten Produktkosten'],
            note='Variantenvergleich unter Besser werden. Spotmodellkosten sind keine tatsächlichen Produktkosten.'))
