"""Private, bounded planning settings and latest handset scenarios; no orders."""
import json
import hashlib
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


# Device proof remains a dated per-field observation. A phone may switch
# broker accounts; never combine separate sessions as confirmed account
# identity, real costs, or a permission to submit orders.
def read_account_context(conn, now=None):
    now=int(time.time()) if now is None else int(now)
    table=conn.execute("SELECT to_regclass('bob_android_remote')").fetchone()
    if not table or not table[0]:return None
    rows=conn.execute("""SELECT r.state FROM bob_android_remote r
        JOIN bob_android_diagnostic_devices d USING(token_hash)
        WHERE NOT d.revoked AND d.expires_at>now() LIMIT 2""").fetchall()
    if len(rows)!=1:return None
    values=rows[0][0]
    if not isinstance(values,dict):return None
    source=values.get('verifiedSettings')
    if not isinstance(source,dict):return None
    results={}
    for field,choices in (('feeProfile',('BASIC','ACTIVE','TRADER')),
                          ('autoFx',('ON','OFF'))):
        value=source.get(field)
        if not isinstance(value,dict) or set(value)!={'value','capturedAt','source'}:
            continue
        if (value.get('value') in choices and type(value.get('capturedAt')) is int
             and 0<=now-value['capturedAt']<=7*86400 and
             value.get('source') in ('degiro-app-owner-confirmed',
                                   'degiro-app-local-accessibility')):
            results[field]=dict(value)
    return results or None


def planning_context(conn,config,now=None):
    # Only missing fields get paper-only, reversible scenario assumptions.
    # No persistent config or order approval is changed here.
    effective=dict(config) if isinstance(config,dict) else None
    proof=read_account_context(conn,now)
    if effective is None or not proof:
        return effective,proof,False
    conditional=False
    if (effective.get('feeProfile','unknown')=='unknown' and
        proof.get('feeProfile',{}).get('value') in ('BASIC','ACTIVE','TRADER')):
        effective['feeProfile']='CH_STANDARD'
        conditional=True
    if (effective.get('fxMode','unknown')=='unknown' and
        proof.get('autoFx',{}).get('value')=='ON'):
        effective['fxMode']='AUTO_CHF'
        conditional=True
    # AutoFX OFF does not imply a funded foreign-currency wallet.
    return effective,proof,conditional


def context_fingerprint(config, evidence, conditional):
    """Bind a cached scenario to the exact dated account assumptions used."""
    payload = json.dumps([config, evidence, conditional], sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def read(conn):
    exists=conn.execute("SELECT to_regclass('bob_handset_planning')").fetchone()
    if not exists or not exists[0]:
        return dict(config=None, revision=0, result=None, resultFresh=False, realOrders=False)
    row = conn.execute('SELECT config,revision,result FROM bob_handset_planning WHERE id=1').fetchone()
    if not row or len(row) != 3:
        return dict(config=None, revision=0, result=None, resultFresh=False, realOrders=False)
    result = row[2]
    age = time.time()*1000-(result or {}).get('calculatedAt', 0)
    effective,account,conditional=planning_context(conn,row[0])
    context = context_fingerprint(effective, account, conditional)
    return dict(config=row[0], effectiveConfig=effective,
                accountEvidence=account, accountEvidenceConditional=conditional,
                accountIdentityConfirmedAcrossSessions=False,
                contextFingerprint=context,
                revision=row[1], result=result,
                resultFresh=bool(result and 0 <= age <= 90000
                    and result.get('configRevision') == row[1]
                    and result.get('contextFingerprint') == context), realOrders=False)


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
    rows = [x for x in report.get('items', []) if x.get('isin') and x.get('state') != 'excluded-factor'][:12]
    if not rows:
        return
    # Include displayed candidates without a phone observation: their independent
    # risk reference is either calculated or explicitly marked unavailable.
    # A missing handset proof never becomes a valid executable quotation.
    fingerprint = json.dumps([[x['isin'], (x.get('handsetObservation') or {}).get('observedAt'),
                              x.get('state')] for x in rows], sort_keys=True)
    old = state.get('result') or {}
    if (old.get('fingerprint') == fingerprint and old.get('configRevision') == state['revision']
            and state.get('contextFingerprint') is not None
            and old.get('contextFingerprint') == state['contextFingerprint']
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
                   config=state.get('effectiveConfig',state['config']),
                   accountEvidenceConditional=state.get('accountEvidenceConditional',False),
                   now=now)
    proc = evaluator_runtime.run(['node', str(Path(__file__).with_name('handset_planning.js'))],
        input=json.dumps(request, allow_nan=False), text=True, capture_output=True,
        timeout=6, check=True, priority=2)
    result = json.loads(proc.stdout)
    from handset_entry_check import assess
    for item in result.get('items', []):
        item['preEntryCheck'] = assess(item, now)
    result.update(fingerprint=fingerprint, configRevision=state['revision'],
                  contextFingerprint=state.get('contextFingerprint'),
                  listUploadedAt=report.get('listUploadedAt'))
    # Do not overwrite a newer configuration saved during this calculation.
    conn.execute('''UPDATE bob_handset_planning SET result=%s::jsonb
        WHERE id=1 AND revision=%s''', (json.dumps(result, allow_nan=False), state['revision']))


def model_plan_audit(conn, now=None):
    """Bounded current-list audit: never equate a derived number with a fill.

    Read only already stored product and calculation results. The live input
    clocks are not rewritten; stale runs are not reported as successes.
    """
    import degiro_product_audit
    now = time.time()*1000 if now is None else now
    report = degiro_product_audit.read(conn, now)
    state = read(conn)
    result = state.get('result') or {}
    uploaded = report.get('listUploadedAt')
    current = bool(state.get('resultFresh') and
        result.get('listUploadedAt') == uploaded and
        isinstance(result.get('items'), list))
    by_isin = {item.get('isin'):item for item in result.get('items', [])[:12]
               if isinstance(item, dict) and isinstance(item.get('isin'), str)}
    rows=[]
    for item in (report.get('items') or [])[:12]:
        isin = item.get('isin')
        if not isinstance(isin,str) or not isin:
            continue
        source = by_isin.get(isin, {}) if current else {}
        terminated = item.get('state') == 'terminated'
        excluded = item.get('state') == 'excluded-factor'
        suitable = (type(source.get('modelStop')) in (int,float) and
            type(source.get('modelTarget')) in (int,float) and
            math.isfinite(source['modelStop']) and source['modelStop'] > 0 and
            math.isfinite(source['modelTarget']) and source['modelTarget'] > 0)
        mode = (source.get('modelMode') if source.get('modelMode') in
            ('anchored-estimate', 'intrinsic-only') else None)
        status = ('terminated' if terminated else 'excluded-factor' if excluded else
                  'not-current' if not current else
                  'modeled-reference' if suitable and mode else
                  'observed-input-reference' if suitable and
                     source.get('planState') in ('reference-calculated','reference-target-obstacle') else
                  'unavailable')
        reason = ('Produkt beendet' if terminated else
                  'Faktorprodukt ausgeschlossen' if excluded else
                  'Kurs-/Planaufnahme noch nicht aktuell bestätigt' if not current else
                  source.get('modelEstimateReason') or
                  ((source.get('reasons') or ['Planparameter fehlen'])[0]))
        rows.append(dict(isin=isin, direction=item.get('direction'),
            status=status,mode=mode if status=='modeled-reference' else None,
            currency=source.get('modelCurrency') if suitable else None,
            modelStop=source['modelStop'] if suitable else None,
            modelTarget=source['modelTarget'] if suitable else None,
            referenceAt=source.get('modelReferenceAt') if suitable else None,
            reason=str(reason)[:240] if status not in ('modeled-reference','observed-input-reference') else None,
            planningOnly=True, tradeApproved=False, originalFillVerified=False))
    return dict(status='observed' if current else 'not-current',
        readOnly=True, realOrders=False, checkedAt=result.get('calculatedAt') if current else None,
        listUploadedAt=uploaded, listed=len(rows),
        modeled=sum(x['status']=='modeled-reference' for x in rows),
        observedInput=sum(x['status']=='observed-input-reference' for x in rows),
        blocked=sum(x['status'] in ('unavailable','not-current') for x in rows),
        excluded=sum(x['status'] in ('excluded-factor','terminated') for x in rows),
        items=rows, scope='current-screen-list-source-bound-risk-references-not-product-approval')
