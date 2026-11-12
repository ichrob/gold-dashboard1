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
                        and start['displayTime'] != end['displayTime']):
                    pair = dict(entryHash=start['originalHash'], exitHash=end['originalHash'],
                        entrySide='ask', exitSide='bid', currency=start['currency'],
                        grossPerUnit=round(end['bid']-start['ask'], 8),
                        grossReturnPct=round((end['bid']/start['ask']-1)*100, 6),
                        captureIntervalSeconds=duration, costsIncluded=False, netResult=None,
                        performanceEligible=False, strategyDecisionVerified=False)
                    break
            if pair:
                break
        products.append(dict(isin=isin, observationCount=len(observations),
            originals=[{k:v for k,v in x.items() if k not in ('bid','ask','at')}
                       for x in observations], repairPlan=retry, illustrativeReplay=pair,
            simulationBlockers=['screen-recognition-not-independently-verified',
                'source-timezone-unconfirmed', 'original-entry-exit-decisions-missing',
                'cost-model-not-linked'] + ([] if pair else ['second-compatible-intraday-observation-missing'])))
    return dict(version=1, scope='handset-originals-research-not-strategy-performance',
        sampledRuns=min(len(runs), LIMIT), fullHistoryRead=False, products=products,
        realOrders=False, marketInputsUpdated=False, netProductReturnsVerified=False)
