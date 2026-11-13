"""Private, bounded planning settings and latest handset scenarios; no orders."""
import json
import math
from pathlib import Path
import time


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_handset_planning (
        id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL DEFAULT 0,
        config JSONB, result JSONB)''')
    conn.execute('INSERT INTO bob_handset_planning(id) VALUES(1) ON CONFLICT DO NOTHING')


def validate(value):
    limits = dict(budgetCHF=(.01, 10000000), riskCHF=(.01, 10000000),
                  feesCHF=(0, 100000), trailAtr=(.1, 10), minRR=(.1, 20))
    optional = dict(feeProfile={'unknown', 'CH_STANDARD'},
                    fxMode={'unknown', 'AUTO_CHF', 'NO_CONVERSION'})
    if (not isinstance(value, dict) or not set(limits) <= set(value)
            or set(value) - set(limits) - set(optional)):
        raise ValueError('Kapital, Risiko und Modellparameter fehlen')
    for key, choices in optional.items():
        if key in value and (not isinstance(value[key], str) or value[key] not in choices):
            raise ValueError('Ungültige Tarifvorgabe: '+key)
    for key, (low, high) in limits.items():
        v = value[key]
        if key == 'feesCHF' and v is None:
            continue  # Automatic fees unresolved is not zero; limits can be saved.
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('Ungültige Planungsvorgabe: '+key)
    if (value['riskCHF'] > value['budgetCHF'] or
            (value['feesCHF'] is not None and value['feesCHF'] >= value['riskCHF'])):
        raise ValueError('Gebühren müssen unter Risiko und Risiko höchstens beim Kapital liegen')
    return dict(value)


def read(conn):
    exists=conn.execute("SELECT to_regclass('bob_handset_planning')").fetchone()
    if not exists or not exists[0]:
        return dict(config=None, revision=0, result=None, resultFresh=False, realOrders=False)
    row = conn.execute('SELECT config,revision,result FROM bob_handset_planning WHERE id=1').fetchone()
    if not row or len(row) != 3:
        return dict(config=None, revision=0, result=None, resultFresh=False, realOrders=False)
    result = row[2]
    age = time.time()*1000-(result or {}).get('calculatedAt', 0)
    return dict(config=row[0], revision=row[1], result=result,
                resultFresh=bool(result and 0 <= age <= 90000), realOrders=False)


def handle(conn, payload):
    if payload.get('action') == 'plan-read':
        return dict(ok=True, **read(conn))
    config = validate(payload.get('config'))
    revision = payload.get('expectedRevision')
    if type(revision) is not int or revision < 0:
        raise ValueError('Gespeicherten Planungsstand zuerst laden')
    row = conn.execute('''UPDATE bob_handset_planning SET config=%s::jsonb,
        revision=revision+1,result=NULL WHERE id=1 AND revision=%s RETURNING revision''',
        (json.dumps(config, allow_nan=False), revision)).fetchone()
    if not row:
        raise ValueError('Vorgaben wurden anderswo geändert. Neu laden und erneut prüfen.')
    return dict(ok=True, config=config, revision=row[0], result=None, resultFresh=False, realOrders=False)


def tick(conn, evidence, quotes, market, bundle, now):
    """Reuse the existing paper worker cycle, source snapshot and bounded runtime."""
    import degiro_product_audit
    import evaluator_runtime
    state = read(conn)
    if market.get('handsetPlanRevision') != state['revision']:
        return  # Configuration changed since the independent model was built.
    report = degiro_product_audit.read(conn, now)
    if report.get('listUploadedAt') != evidence.get('listUploadedAt'):
        return
    rows = [x for x in report.get('items', []) if x.get('handsetObservation')]
    if not rows:
        return
    fingerprint = json.dumps([[x['isin'], x['handsetObservation'].get('observedAt'),
                              x.get('state')] for x in rows], sort_keys=True)
    old = state.get('result') or {}
    if (old.get('fingerprint') == fingerprint and old.get('configRevision') == state['revision']
            and old.get('listUploadedAt') == report.get('listUploadedAt')
            and 0 <= now-old.get('calculatedAt', 0) < 30000):
        return
    from datetime import datetime, timezone
    from handset_contract_model import prepare
    clock=datetime.fromtimestamp(now/1000, timezone.utc)
    # Private copies only; never publish these comparison models to rankings.
    comparison_quotes={row['isin']:prepare(quotes.get(row['isin']),clock) for row in rows[:12]}
    request = dict(report=report, products=evidence.get('products', [])[:12], quotes=comparison_quotes,
                   plans=market.get('handsetPlans') or {}, spots=bundle.get('spots') or {},
                   config=state['config'], now=now)
    proc = evaluator_runtime.run(['node', str(Path(__file__).with_name('handset_planning.js'))],
        input=json.dumps(request, allow_nan=False), text=True, capture_output=True,
        timeout=6, check=True, priority=2)
    result = json.loads(proc.stdout)
    result.update(fingerprint=fingerprint, configRevision=state['revision'],
                  listUploadedAt=report.get('listUploadedAt'))
    # Do not overwrite a newer configuration saved during this calculation.
    conn.execute('''UPDATE bob_handset_planning SET result=%s::jsonb
        WHERE id=1 AND revision=%s''', (json.dumps(result, allow_nan=False), state['revision']))
