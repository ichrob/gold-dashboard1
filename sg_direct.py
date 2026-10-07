"""Authorized SG website import, bounded to one refresh per product / 30s.

The user confirmed SG's 7 October reply covers the requested private use.
Chart observations remain research evidence; missing clocks are never invented.
"""
import copy
import threading
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
import product_quotes as q

_LOCK = threading.Lock()
_PRODUCT_LOCKS = {}
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
            'Stammdaten übernommen; '+('KO/Basispreis nachgewiesen; ' if (result.get('metadata', {}).get('termsDated') or result.get('metadata', {}).get('termsFixed')) else 'datierter KO-/Basispreisnachweis fehlt; ')+'datierter Hebel weiterhin erforderlich.').format(
                evidence['bid'], evidence['ask'], evidence['pointAt'],
                'aktuell' if evidence['current'] else 'veraltet')
    return result


def conditions(product, properties, result):
    attrs = {p['Name']: p for p in properties}
    values = {'underlying': result['metadata']['underlying'], 'currency': 'EUR'}
    quanto = attrs.get('IsQuanto', {}).get('Value')
    result['metadata']['simpleTurbo'] = product.get('ProductClassificationId') in (43,45,47)
    result['metadata']['quantoState'] = ('non-quanto' if quanto is False or quanto in ('Nein','No')
        else 'quanto' if quanto is True or quanto in ('Ja','Yes') else 'unknown')
    result['metadata']['simpleNonQuantoTurbo'] = (result['metadata']['simpleTurbo']
        and result['metadata']['quantoState'] == 'non-quanto')
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
        elif product.get('MaturityDate'):
            values['maturity'] = datetime.fromisoformat(product['MaturityDate']).strftime('%d.%m.%Y')
    if result['metadata'].get('contract'):
        values['contract'] = result['metadata']['contract']
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
    # SG explicitly dates changes to strike AND barrier. Retain only its
    # calendar date; do not invent a timezone, intraday time or quote clock.
    evidence = result['metadata'].get('koEvidence')
    if evidence and 'strike' in observed:
        updated = datetime.fromisoformat(evidence['updatedAtRaw'].replace('Z', '+00:00'))
        today = datetime.now(ZoneInfo('Europe/Zurich')).date()
        if updated.date() == today:
            date_text = updated.strftime('%d.%m.%Y')
            for key in ('ko', 'strike'):
                result['conditions'][key] = dict(value=observed[key], at=None,
                    dateText=date_text, source=result['sourceUrl'], conditionVerified=True,
                    sourceField='StrikeBarrierUpdateTime', sourceTimeRaw=evidence['updatedAtRaw'],
                    reviewedAt=result['checkedAt'])
            result['metadata'].update(termsDated=True, termsDate=date_text)
    # SG's product brochure identifies Classic strike/barrier as constant.
    # Store that contract evidence without inventing a daily effective date.
    if (product.get('ProductClassificationId') == 43 and typ == 'Classic Turbo-Optionsscheine'
            and product.get('AssetNMP') == 'XAUUSD' and product.get('MaturityDate')
            and observed.get('strike') == observed['ko']):
        expiry = datetime.fromisoformat(product['MaturityDate']).date()
        if expiry > datetime.now(ZoneInfo('Europe/Zurich')).date():
            for key in ('ko', 'strike'):
                result['conditions'][key] = dict(value=observed[key], at=None,
                    source=result['sourceUrl'], conditionVerified=True, fixed=True,
                    validUntil=expiry.isoformat(), reviewedAt=result['checkedAt'],
                    policySource=q.SG_ORIGIN+'contentmgmt/media/c5bihw1s/bro_turbo-optionsscheine.pdf')
            result['metadata']['termsFixed'] = True
    result['metadata'].update({key: values[key] for key in ('ratio',) if key in values})
    if 'strike' in observed:
        result['metadata']['strike'] = observed['strike']


def get_quote(isin, terms_only=False):
    if isin not in q.SG_DIRECT_PRODUCTS:
        return q.sg_disabled(isin)
    # Serialize per product; a slow source for one ISIN must not block all others.
    with _LOCK:
        product_lock = _PRODUCT_LOCKS.setdefault(isin, threading.Lock())
    with product_lock:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < INTERVAL:
            return refresh_evidence(cached[1])
        result = dict(found=False, eligible=False, fresh=False, productVerified=False,
                      isin=isin, source='Société Générale · Direktimport',
                      sourceUrl=q.SG_ORIGIN+'product-details/'+isin.lower(),
                      importActive=True, refreshIntervalSeconds=INTERVAL, analysisMaxAgeSeconds=300,
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
                        or product.get('ProductClassificationId') not in (43, 45, 47, 44100)):
                    raise ValueError('SG-Produktidentität nicht bestätigt')
                if product['ProductClassificationId'] == 44100:
                    if q.sg_future_contract(product, isin) is None or product.get('Currency') != 'EUR' or product.get('AssetCurrency') != 'USD' or product.get('ExchangeCode') != 'CBDE':
                        raise ValueError('SG-Faktorproduktidentität nicht bestätigt')
                    result.update(productVerified=True, excluded=True, name=product.get('Name'),
                        metadata=dict(name=product.get('Name'), status=1, underlyingType='FUTURE',
                                      contract=product['AssetRic'], productType='FACTOR'),
                        conditions={}, reason='Faktorprodukt ausgeschlossen – keine weiteren Daten erforderlich')
                    _CACHE[isin] = (time.monotonic(), copy.deepcopy(result))
                    return result
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
            elif terms_only:
                result['reason'] = 'SG-Stammdaten übernommen; Kurs- und Hebelabruf folgen separat'
                return result
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
