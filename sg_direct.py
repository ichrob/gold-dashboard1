"""Authorized SG website import, bounded to one refresh per product / 30s.

The user confirmed SG's 7 October reply covers the requested private use.
Chart observations remain research evidence; missing clocks are never invented.
"""
import copy
import threading
import time
from datetime import datetime, timezone
import product_quotes as q

_LOCK = threading.Lock()
_CACHE = {}
_TERMS = {}
INTERVAL = 30


def refresh_evidence(result):
    result = copy.deepcopy(result)
    evidence = result.get('chartEvidence')
    if evidence:
        age = (datetime.now(timezone.utc)-q.stamp(evidence['pointAt'])).total_seconds()
        evidence.update(ageSeconds=round(age, 1), current=0 <= age <= q.MAX_AGE_SECONDS)
        result['reason'] = ('SG-Direktimport aktiv (30 s): Chart Geld {:.3f} / Brief {:.3f} EUR, Stand {} ({}). '
            'Stammdaten übernommen; datierter Hebel und gültiger KO-/Basispreisnachweis weiterhin erforderlich.').format(
                evidence['bid'], evidence['ask'], evidence['pointAt'],
                'aktuell' if evidence['current'] else 'veraltet')
    return result


def conditions(product, properties, result):
    attrs = {p['Name']: p for p in properties}
    values = {'underlying': result['metadata']['underlying'], 'currency': 'EUR'}
    ratio = attrs.get('Ratio', {})
    if ratio.get('Suffix', '').strip() == ':1':
        units = q.number(ratio['Value'])
        if units > 0:
            values['ratio'] = 1/units
    typ = attrs.get('ClassificationName', {}).get('Value')
    if product.get('ProductClassificationId') in (43, 45, 47) and isinstance(typ, str):
        values['type'] = typ
        if product.get('MaturityDate') is None and 'Open-End' in typ:
            values['maturity'] = 'Open End'
    result['conditions'] = {key: dict(value=value, at=None, source=result['sourceUrl'],
        reviewedAt=result['checkedAt'], conditionVerified=True) for key, value in values.items()}
    # These observations do not gain an effective time from our request time.
    result['metadata']['termsDated'] = False
    strike = attrs.get('Strike', {})
    observed = dict(ko=result['metadata']['ko'], source=result['sourceUrl'],
                    effectiveAt=None, updatedAtRaw=attrs.get('StrikeBarrierUpdateTime', {}).get('Value'))
    if strike.get('Suffix', '').strip() == 'USD':
        value = q.number(strike['Value'])
        if value > 0:
            observed['strike'] = value
    result['observedTerms'] = observed


def get_quote(isin):
    if isin not in q.SG_DIRECT_PRODUCTS:
        return q.sg_disabled(isin)
    # Serialize source work across callers so overlapping browser/background
    # requests cannot duplicate requests or bypass the failure cooldown.
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < INTERVAL:
            return refresh_evidence(cached[1])
        result = dict(found=False, eligible=False, fresh=False, productVerified=False,
                      isin=isin, source='Société Générale · Direktimport',
                      sourceUrl=q.SG_ORIGIN+'product-details/'+isin.lower(),
                      importActive=True, refreshIntervalSeconds=INTERVAL,
                      checkedAt=datetime.now(timezone.utc).isoformat())
        stage = 'identity'
        try:
            terms = _TERMS.get(isin)
            if terms and time.monotonic()-terms[0] < 300:
                product, properties = terms[1:]
            else:
                base = q.SG_ORIGIN+'EmcWebApi/api/'
                product = q.issuer_json(base+'Products/'+isin, q.SG_ORIGIN, timeout=12)
                if (product.get('Isin') != isin or type(product.get('Id')) is not int
                        or product['Id'] != q.SG_DIRECT_PRODUCTS[isin]
                        or product.get('ProductClassificationId') not in (43, 45, 47)):
                    raise ValueError('SG-Produktidentität nicht bestätigt')
                stage = 'properties'
                properties = q.issuer_json(base+'Products/AllProperties/'+str(product['Id']), q.SG_ORIGIN, timeout=12)
                q.parse_sg(product, properties, isin)
                _TERMS[isin] = (time.monotonic(), product, properties)
            result.update(q.parse_sg(product, properties, isin))
            # UI uses normalized 1=active / 2=ended, not SG's bit flags (65).
            result['metadata']['sgStatus'] = product['Status']
            result['metadata']['status'] = (2 if product['Status'] & (2|8|16|32)
                or not product['Status'] & 1 or product.get('TodayBarrierHitDate') else 1)
            conditions(product, properties, result)
            if product['Status'] & (2|8|16|32) or not product['Status'] & 1 or product.get('TodayBarrierHitDate'):
                result['reason'] = 'SG-Produkt beendet oder ausgeknockt – ausgeschlossen'
            else:
                stage = 'dated-quotes'
                points = q.issuer_json(q.SG_ORIGIN+'EmcWebApi/api/Prices/Live?productId='+str(product['Id']), q.SG_ORIGIN, timeout=12)
                chart = q.parse_sg_chart_research(product, points, isin)
                result['chartEvidence'] = chart['chartEvidence']
                result['reason'] = ('SG-Direktimport aktiv (30 s): Stammdaten übernommen; '
                    'Geld/Brief als datierter Chartnachweis. Separat datierter Hebel und gültiger KO-/Basispreisnachweis fehlen weiterhin.')
        except Exception as exc:
            result.update(sourceFailure=not result['productVerified'],
                          quoteFailureCode='SG_SOURCE_UNAVAILABLE', reason=q.sg_source_error(exc, stage))
        # Time starts after completion; errors are also rate-limited.
        _CACHE[isin] = (time.monotonic(), copy.deepcopy(result))
        return refresh_evidence(result)
