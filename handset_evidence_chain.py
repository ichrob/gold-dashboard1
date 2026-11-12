"""Bounded research projection of stored handset originals; never market inputs.

Reproducible quote references and missing-field plans share the existing reader
report. A two-observation calculation is illustrative, not a strategy trade.
No source timezone is inferred from the phone's locale or receipt timestamp.
"""
import hashlib
import json
import math
from datetime import datetime

LIMIT = 50
FIELDS = ('Geld', 'Brief', 'Anzeigezeit', 'Hebel', 'KO-Schwelle', 'Basispreis', 'Bv', 'Währung')


def clock(value):
    try:
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return at.timestamp() if at.tzinfo else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def number(value):
    try:
        v = float(value.replace(',', '.')) if isinstance(value, str) else None
        return v if v is not None and math.isfinite(v) and v > 0 else None
    except (ValueError, OverflowError):
        return None


def display_interval(start, end):
    """Compare displayed clocks without inventing their missing timezone.

    Minute precision allows up to 120s difference from capture intervals.
    This rejects frozen/reversed clocks, not a proof of absolute freshness.
    """
    try:
        a = datetime.strptime(start['displayTime'], '%d/%m/%Y %H:%M')
        b = datetime.strptime(end['displayTime'], '%d/%m/%Y %H:%M')
        elapsed = (b-a).total_seconds()
        return elapsed if elapsed > 0 and abs(elapsed-(end['at']-start['at'])) <= 120 else None
    except (TypeError, ValueError):
        return None


def cost_replay(start, end):
    """One hypothetical unit, using the existing paper ledger's assumptions.

    Never create a paper trade or debit an account. EUR fees cannot silently
    be applied to CHF observations without dated FX evidence.
    """
    if start['currency'] != 'EUR':
        return dict(status='missing-dated-fx', quantity=1, modelNetEur=None,
                    brokerNetVerified=False, ledgerUpdated=False)
    from paper_costs import evaluate
    from paper_ledger_costs import MODEL
    case = dict(status='closed', productReturnKnown=True, pendingUnits=0,
        remainingUnits=0, quantity=1, allocated=start['ask'], cashReleased=end['bid'],
        startedAt=start['at']*1000, closedAt=end['at']*1000,
        events=[dict(units=1, quote=dict(bid=end['bid']))])
    values = evaluate(case, MODEL)
    return dict(status='illustrative-one-unit-model', quantity=1,
                assumptions=dict(MODEL), **values, brokerNetVerified=False,
                ledgerUpdated=False, note='Ein hypothetisches Stück; bestehende Beispielkosten, keine bestätigten Brokertarife. Spread bereits enthalten.')


def project(runs):
    groups, latest, seen = {}, {}, set()
    for run in runs[:LIMIT]:
        if not isinstance(run, dict):
            continue
        received = clock(run.get('receivedAt'))
        if received is None:
            continue
        for row in run.get('results', [])[:12]:
            isin = row.get('isin')
            if not isinstance(isin, str) or isin not in run.get('isins', []):
                continue
            obs = row.get('observation') or {}
            fields = obs.get('fields') or {}
            requested = row.get('requestedFields') or FIELDS
            if isin not in latest or received > latest[isin][0]:
                latest[isin] = (received, row, fields, requested)
            at = clock(obs.get('observedAt'))
            bid, ask = number(fields.get('Geld')), number(fields.get('Brief'))
            if (at is None or at > received + 60 or obs.get('staleAtReceipt') or
                    bid is None or ask is None or bid > ask or
                    fields.get('Währung') not in ('EUR', 'CHF')):
                continue
            # Same original appearing in multiple revisions is one observation.
            original = {k: obs.get(k) for k in ('isin', 'observedAt', 'fields', 'raw')}
            digest = hashlib.sha256(json.dumps(original, sort_keys=True,
                ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            groups.setdefault(isin, []).append(dict(
                originalHash=digest, batchId=run.get('batchId'), revision=run.get('revision'),
                observedAt=obs.get('observedAt'), displayTime=fields.get('Anzeigezeit'),
                currency=fields.get('Währung'), venue=fields.get('Handelsplatz'),
                bid=bid, ask=ask, at=at))
    products = []
    for isin, (_, row, fields, requested) in latest.items():
        observations = sorted(groups.get(isin, []), key=lambda x: (x['at'], x['originalHash']))
        missing = [k for k in FIELDS if k in requested and k not in fields]
        retry = dict(isin=isin, requestedFields=missing, automaticExecution=False,
                     reason='missing-fields' if missing else 'complete-read')
        retry['deviceRetryPolicy'] = 'existing-bounded-two-attempt-reader'
        retry['attemptsObserved'] = row.get('attempts')
        if missing == ['Hebel'] and fields:
            retry.update(reason='issuer-leverage-recovery', requestedFields=[],
                         note='Existing reader intentionally avoids another visit solely for an absent leverage label.')
        elif row.get('attempts', 0) >= 2 and missing:
            retry.update(reason='device-attempt-budget-exhausted', requestedFields=[])
        if row.get('code') in ('NO_QUOTES', 'QUOTES_UNAVAILABLE'):

            retry.update(reason='check-product-status-before-reread', requestedFields=[],
                         note='No blind repeated quote requests; distinguish missing display from inactive product.')
        pair = None
        # Latest same-venue/currency pair within the user's intraday horizon.
        # Only source-labelled originals qualify for this illustrative replay.
        for end in reversed(observations):
            for start in reversed(observations):
                duration = end['at'] - start['at']
                if (1800 <= duration <= 18000 and start['currency'] == end['currency']
                        and start['venue'] and start['venue'] == end['venue']
                        and start['displayTime'] and end['displayTime']
                        and display_interval(start, end) is not None):
                    pair = dict(entryHash=start['originalHash'], exitHash=end['originalHash'],
                        entrySide='ask', exitSide='bid', currency=start['currency'],
                        grossPerUnit=round(end['bid']-start['ask'], 8),
                        grossReturnPct=round((end['bid']/start['ask']-1)*100, 6),
                        captureIntervalSeconds=duration, displayIntervalSeconds=display_interval(start, end),
                        costsIncluded=False, netResult=None, costModelReplay=cost_replay(start, end),
                        performanceEligible=False, strategyDecisionVerified=False)
                    break
            if pair:
                break
        products.append(dict(isin=isin, observationCount=len(observations),
            originals=[{k:v for k,v in x.items() if k not in ('bid','ask','at')}
                       for x in observations], repairPlan=retry, illustrativeReplay=pair,
            simulationBlockers=['screen-recognition-not-independently-verified',
                'source-timezone-unconfirmed', 'original-entry-exit-decisions-missing',
                'actual-broker-costs-unverified'] + (['dated-fx-missing'] if pair and pair['currency'] != 'EUR' else []) + ([] if pair else ['second-compatible-intraday-observation-missing'])))
    return dict(version=2, scope='handset-originals-research-not-strategy-performance',
        sampledRuns=min(len(runs), LIMIT), fullHistoryRead=False, products=products,
        realOrders=False, marketInputsUpdated=False, netProductReturnsVerified=False)
