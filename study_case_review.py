"""User-requested retrospective review; original cases and counters are immutable."""
import math

# Fixed boundary of the cases inspected before the user's 12 Nov instruction.
CUTOFF = 1794503140815
VERSION = 'historical-study-review-20261112-v1'
LIMIT = 600
NOTE = ('Historische Prüfung abgeschlossen; Originalergebnisse bleiben unbestätigt. '
        'Endpunktmodelle nutzen gespeicherte Kurse und angenommene Kosten; '
        'Zwischenverlauf, Stop, Ziel und KO bleiben unbekannt. '
        'Wiederaufnahme bei neuen Originalnachweisen möglich; neue Studien laufen weiter.')


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def review(case):
    if (not isinstance(case, dict) or case.get('status') != 'inconclusive'
            or case.get('simulationOnly') or str(case.get('id', '')).endswith(':model-v1')
            or not finite(case.get('closedAt')) or not 0 < case['closedAt'] <= CUTOFF):
        return None
    out = dict(status='closed-original-unresolved', reviewVersion=VERSION,
               originalResultVerified=False, performanceEligible=False,
               reopenWithOriginalEvidence=True, modelStatus='unavailable',
               reason='Gespeicherte Start-/Endkurse oder Modellkosten reichen nicht aus.',
               returnsPct={}, pathComplete=False, productReturnVerified=False)
    at, end = case.get('at'), case.get('endAt')
    cost, exit_point, legs = case.get('costAssumptionPct'), case.get('exit'), case.get('legs')
    if (not finite(at) or not finite(end) or not 0 < at < end <= case['closedAt']
            or not finite(cost) or cost < 0 or not isinstance(exit_point, dict)
            or not isinstance(legs, dict) or not legs):
        return out
    exit_at, exit_price = exit_point.get('at'), exit_point.get('price')
    if (not finite(exit_at) or not end <= exit_at <= min(end+60000, case['closedAt'])
            or not finite(exit_price) or exit_price <= 0 or exit_point.get('estimated')):
        return out
    values = {}
    for name, leg in legs.items():
        if not isinstance(leg, dict):
            return out
        entry = leg.get('entry')
        if entry is None and leg.get('wait') is True:
            values[name] = 0.0
            continue
        if not isinstance(entry, dict) or leg.get('direction') not in ('LONG', 'SHORT'):
            return out
        entry_at, price = entry.get('at'), entry.get('price')
        if (not finite(entry_at) or not at <= entry_at < end
                or not finite(price) or price <= 0 or entry.get('estimated')):
            return out
        value = 100 * (1 if leg['direction'] == 'LONG' else -1) * (exit_price/price-1) - cost
        if not math.isfinite(value):
            return out
        values[name] = value
    out.update(modelStatus='endpoint-model', reason=None, returnsPct=values,
               costAssumptionPct=cost, retrospectivelyCalculated=True,
               stopOutcome='unknown', targetOutcome='unknown', koOutcome='unknown')
    return out


def report(conn, campaign):
    # Existing small ledger, capped by three studies * 200 cases. Never scan
    # the large spot archive or mutate original outcomes in a report request.
    rows = conn.execute('''SELECT payload FROM bob_quality_cases
        WHERE campaign=%s AND payload->>'status'='inconclusive'
        ORDER BY id LIMIT %s''', (campaign, LIMIT * 2 + 1)).fetchall()
    counts = dict(reviewed=0, modeled=0, unavailable=0)
    items = []
    by_study = {}
    for (case,) in rows[:LIMIT * 2]:
        result = review(case)
        if result is None:
            continue
        study = case.get('study')
        if study not in ('entry-delay', 'warning-confirmed', 'sideways-filter'):
            continue
        by_study[study] = by_study.get(study, 0) + 1
        counts['reviewed'] += 1
        counts['modeled' if result['modelStatus']=='endpoint-model' else 'unavailable'] += 1
        items.append(dict(study=case.get('study'), closedAt=case['closedAt'], **result))
    items.sort(key=lambda r:r['closedAt'], reverse=True)
    return dict(status='observed', version=VERSION, cutoffAt=CUTOFF, counts=counts, byStudy=by_study,
                truncated=len(rows)>LIMIT * 2, items=items[:10], itemLimit=10,
                originalEvidenceUnchanged=True, realOrders=False, note=NOTE)
