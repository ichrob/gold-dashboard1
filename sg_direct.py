"""Authorized SG website import, bounded to one refresh per product / 30s.

The user confirmed SG's 7 October reply covers the requested private use.
Chart observations remain research evidence; missing clocks are never invented.
"""
import copy
import re
import threading
import time
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
import product_quotes as q
from term_series import observed_condition

_LOCK = threading.Lock()
_PRODUCT_LOCKS = {}
_CACHE = {}
_TERMS = {}
_MARKETS = {}  # Exact ISIN -> market, only after validated issuer properties.
INTERVAL = 30



def cached_verified_observation(isin):
    """Return one already-fetched SG observation; NEVER start another request.

    It can repair metadata lost during first-pass source composition, but cannot
    refresh quote, terms, leverage or request clocks, or certify execution.
    """
    with _LOCK:
        row = _CACHE.get(isin)
    if not row or not 0 <= time.monotonic() - row[0] < INTERVAL:
        return None
    evidence = row[1]
    if (not isinstance(evidence, dict) or evidence.get('isin') != isin
            or evidence.get('productVerified') is not True
            or evidence.get('sourceFailure') or evidence.get('quoteFailureCode')
            or evidence.get('metadata', {}).get('status') != 1
            or not evidence.get('metadata', {}).get('issuerExchangeCode')
            or not evidence.get('chartEvidence', {}).get('pointAt')):
        return None
    return copy.deepcopy(evidence)



def retain_last_verified_observation(previous, failed, stage):
    """Keep dated research observations through a transient provider failure.

    Do not copy prior values onto an explicitly ended product or new terms.
    Source clocks and the terms verification time must remain unchanged.
    """
    if not isinstance(previous, dict) or not previous.get('productVerified'):
        return failed
    if not previous.get('chartEvidence') or previous.get('metadata', {}).get('status') != 1:
        return failed
    if failed.get('productVerified'):
        current = failed.get('metadata') or {}
        old = previous.get('metadata') or {}
        if current.get('status') != 1:
            return failed
        for key in ('currency', 'underlying', 'direction', 'ko', 'strike',
                    'ratio', 'issuerExchangeCode', 'contract'):
            if key in current and old.get(key) != current[key]:
                return failed
        for key in ('ko', 'strike', 'ratio'):
            value = (failed.get('conditions') or {}).get(key, {}).get('value')
            if value is not None and value != (previous.get('conditions') or {}).get(key, {}).get('value'):
                return failed
    carried = copy.deepcopy(previous)
    carried.update(sourceFailure=True, quoteFailureCode='SG_SOURCE_UNAVAILABLE',
                   checkedAt=failed['checkedAt'], lastSourceAttemptAt=failed['checkedAt'],
                   lastSourceFailureStage=stage,
                   reason=failed.get('reason', 'SG-Abruf fehlgeschlagen')
                       + '; letzte bestätigte Beobachtung mit ORIGINAL-Kurszeit erhalten, '
                         'Aktualität weiterhin separat prüfen')
    # A failed request is neither a new issuer observation nor a renewal of
    # KO/strike validity. In particular, keep termsCheckedAt and pointAt.
    return carried


def refresh_evidence(result):
    result = copy.deepcopy(result)
    evidence = result.get('chartEvidence')
    if evidence:
        reference = result.get('issuerLeverageReference') or {}
        context = result.get('sharedTimeContext') or {}
        shared = (reference.get('sharedContextAt') == evidence.get('pointAt')
                  and context.get('at') == evidence.get('pointAt')
                  and context.get('isin') == result.get('isin')
                  and reference.get('value') is not None)
        leverage_note = ('Vorhandener SG-Referenzhebel mit gemeinsamem Zeitbezug der Abrufserie bestätigt; Aktualität separat prüfen.'
                         if shared else 'SG-Referenzhebel vorhanden, aber gemeinsamer Zeitbezug nicht bestätigt.'
                         if reference.get('value') is not None else 'SG-Referenzhebel von der Quelle nicht geliefert; erneuter Abruf erforderlich.')
        age = (datetime.now(timezone.utc)-q.stamp(evidence['pointAt'])).total_seconds()
        evidence.update(ageSeconds=round(age, 1), current=0 <= age <= q.MAX_AGE_SECONDS)
        if not result.get('sourceFailure') and not result.get('quoteFailureCode'):
            result['reason'] = ('SG-Direktimport aktiv (30 s): Chart Geld {:.3f} / Brief {:.3f} {}, Stand {} ({}). '
            'Stammdaten übernommen; '+('KO/Basispreis nachgewiesen; ' if (result.get('metadata', {}).get('termsDated') or result.get('metadata', {}).get('termsFixed')) else 'Basispreis/KO mit Zeitbezug der automatischen Abrufserie übernommen; ')+leverage_note+' Chartbeobachtung, kein DEGIRO-Ausführungsnachweis.').format(
                evidence['bid'], evidence['ask'], evidence['currency'], evidence['pointAt'],
                'aktuell' if evidence['current'] else 'veraltet')
    return result


def _quanto_flag(raw):
    """Recognize only an explicit issuer boolean, never missing/ambiguous data."""
    if type(raw) is bool:
        return raw
    if type(raw) is int and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        normalized = raw.strip().casefold()
        if normalized in ('nein', 'no', 'false', '0'):
            return False
        if normalized in ('ja', 'yes', 'true', '1'):
            return True
    return None


def _quanto_status(product, attrs):
    """Corroborate issuer fields; disagreements fail closed."""
    fields = (
        ('AllProperties.IsQuanto', attrs.get('IsQuanto', {}).get('Value')),
        ('AllProperties.Quanto', attrs.get('Quanto', {}).get('Value')),
        ('Products.IsQuanto', product.get('IsQuanto')),
    )
    flags = [(name, _quanto_flag(value)) for name, value in fields if value is not None]
    confirmed = [(name, flag) for name, flag in flags if flag is not None]
    if any(flag is None for _, flag in flags) or len({flag for _, flag in confirmed}) > 1:
        return 'unknown', None, 'SG-Felder unklar oder widersprüchlich'
    if not confirmed:
        return 'unknown', None, 'Kein ausdrückliches SG-Quanto-Merkmal'
    is_quanto = confirmed[0][1]
    return ('quanto' if is_quanto else 'non-quanto'), ', '.join(name for name, _ in confirmed), None


def conditions(product, properties, result):
    attrs = {p['Name']: p for p in properties}
    values = {'underlying': result['metadata']['underlying'], 'currency': product['Currency']}
    quanto_state, quanto_source, quanto_issue = _quanto_status(product, attrs)
    result['metadata']['simpleTurbo'] = product.get('ProductClassificationId') in (43,45,47)
    result['metadata']['classificationId'] = product.get('ProductClassificationId')
    result['metadata']['quantoState'] = quanto_state
    result['metadata']['quantoProof'] = dict(
        confirmed=quanto_source is not None, source=quanto_source, issue=quanto_issue)
    result['metadata']['simpleNonQuantoTurbo'] = (result['metadata']['simpleTurbo']
        and quanto_state == 'non-quanto')
    # The SG AllProperties indicative leverage has no authenticated market
    # clock. Keep it as reference-only; do NOT populate live leverage/At.
    # CH publishes the same current_leverage field under Gearing, DE under
    # CurrentLeverage. Preserve the actual property name and shared context.
    references = []
    for name in ('CurrentLeverage', 'Gearing'):
        prop = attrs.get(name, {})
        if name == 'Gearing' and prop.get('RealtimeFieldName') != 'current_leverage':
            continue
        indicated = prop.get('Value')
        try:
            if isinstance(indicated, str) and re.fullmatch(r'[0-9]{1,4}(?:[.,][0-9]{1,4})?', indicated.strip()):
                value = float(indicated.strip().replace(',', '.'))
            else:
                value = q.number(indicated) if indicated is not None else 0
        except (ValueError, TypeError):
            value = 0
        if not isinstance(indicated, bool) and 0 < value <= 10000:
            references.append((name, value))
    if references and len({value for _, value in references}) == 1:
        name, value = references[0]
        result['issuerLeverageReference'] = dict(
            value=value, source='SG · AllProperties.'+name,
            sourceAt=None, retrievedAt=result.get('termsCheckedAt'),
            dated=False, eligible=False,
            note='Undatierter SG-Referenzhebel; keine Kurszeit, kein Handelsnachweis')
    elif references:
        result['leverageReferenceIssue'] = 'Widersprüchliche SG-Hebelwerte'
    ratio = attrs.get('Ratio', {})
    if ratio.get('Suffix', '').strip() == ':1':
        units = q.number(ratio['Value'])
        if units > 0:
            values['ratio'] = 1/units
    typ = attrs.get('ClassificationName', {}).get('Value')
    if product.get('ProductClassificationId') in (43, 45, 47) and isinstance(typ, str):
        values['type'] = typ
        if product.get('MaturityDate') is None and ('Open-End' in typ or product.get('ExchangeCode') == 'CBSW' and product.get('ProductClassificationId') == 47 or product.get('ProductClassificationId') == 45 and 'Unlimited' in typ):
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
    # Keep a successfully read number visible even if SG omits its validity
    # date. This is observed evidence, never a dated condition or clearance.
    for key in ('ko', 'strike'):
        if key in observed:
            result['conditions'][key] = observed_condition(observed[key], result['sourceUrl'],
                result['isin'], result.get('termsCheckedAt', result['checkedAt']))
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


def associate_shared_observation(result):
    """Record a common *observation context*, never an invented issuer clock.

    The properties and SG chart are separate endpoints. Associate their values
    only when the same verified ISIN was read in one recent, coherent cycle.
    The chart point time remains a chart time, NOT a dated issuer leverage.
    """
    reference = result.get('issuerLeverageReference')
    chart = result.get('chartEvidence') or {}
    at = chart.get('pointAt')
    terms_at = result.get('termsCheckedAt')
    if not (at and terms_at and result.get('productVerified')):
        return
    try:
        source = q.stamp(at)
        observed = q.stamp(terms_at)
    except (ValueError, TypeError, KeyError):
        return
    seconds = (observed - source).total_seconds()
    # A chart point can be a few seconds newer than the properties response
    # even within the same verified ISIN collection. Preserve that shared
    # observation context, without turning it into a leverage source clock.
    if not (-5 <= seconds <= 90):
        return
    # One observation series dates *every value actually read* in this cycle.
    # A separately published/effective timestamp remains authoritative and
    # must never be replaced by the chart time.
    observations = {}
    def observed(name, value, source_at=None, source_date=None):
        if value is not None and value != '':
            observations[name] = dict(value=value, contextAt=at,
                contextKind='issuer-collection', sourceAt=source_at,
                sourceDate=source_date, isin=result['isin'])
    observed('ISIN', result['isin'])
    observed('Geld', chart.get('bid'), at)
    observed('Brief', chart.get('ask'), at)
    for key in ('name', 'direction', 'currency', 'underlying',
                'underlyingType', 'status', 'ko', 'strike', 'ratio',
                'contract'):
        observed(key, result.get('metadata', {}).get(key))
    for key, condition in result.get('conditions', {}).items():
        # An observed term has a shared *observation* clock; an explicit
        # condition/effective time is retained separately.
        observed(key, condition.get('value'), condition.get('at'),
                 condition.get('dateText'))
        if condition.get('value') is not None:
            condition.update(contextAt=at, contextKind='issuer-collection')
    if reference:
        observed('Referenzhebel', reference.get('value'), reference.get('sourceAt'))
        reference.update(sharedContextAt=at,
                         sharedContextKind='issuer-collection',
                         sharedContextNote='Im selben SG-Abruf beobachtet; Chartquellenzeit, keine eigene Hebelquellenzeit.')
    result['sharedValueObservations'] = observations
    result['sharedTimeContext'] = dict(
        at=at, kind='issuer-collection', isin=result['isin'],
        timeOrigin='SG-Chartzeit aus derselben Emittenten-Abrufserie',
        timeDistanceSeconds=round(seconds, 1),
        fields=list(observations),
        note='Alle tatsächlich beobachteten Werte derselben ISIN teilen diesen Beobachtungszeitbezug. Eigene Quellen- und Gültigkeitszeiten bleiben erhalten; keine DEGIRO-Ausführung.')


def get_quote(isin, terms_only=False):
    market = _MARKETS.get(isin, q.sg_market(isin))
    origin = market[0]
    if isin not in q.SG_DIRECT_PRODUCTS and isin not in q.SG_DISCOVERY_PRODUCTS and not q.sg_on_demand_candidate(isin):
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
                      sourceUrl=origin+'product-details/'+isin.lower(),
                      importActive=True, refreshIntervalSeconds=INTERVAL, analysisMaxAgeSeconds=300,
                      checkedAt=datetime.now(timezone.utc).isoformat())
        stage = 'identity'
        try:
            terms = _TERMS.get(isin)
            if terms and time.monotonic()-terms[0] < INTERVAL:
                product, properties, observed_at, market = terms[1:]
                origin = market[0]
            else:
                origin = market[0]
                base = origin+'EmcWebApi/api/'
                try:
                    product = q.issuer_json(base+'Products/'+isin, origin, timeout=12)
                except HTTPError as exc:
                    # Only a missing identity permits one other public market.
                    # Never retry access denials or accept a wrong-channel reply.
                    known = isin in q.SG_DIRECT_PRODUCTS or isin in q.SG_DISCOVERY_PRODUCTS
                    if exc.code != 404 or known or market[1] != 'CBDE':
                        raise
                    market = ('https://www.sg-zertifikate.ch/', 'CBSW', 'CHF')
                    origin = market[0]
                    base = origin+'EmcWebApi/api/'
                    product = q.issuer_json(base+'Products/'+isin, origin, timeout=12)
                expected_id = q.SG_DIRECT_PRODUCTS.get(isin)
                if (product.get('Isin') != isin or type(product.get('Id')) is not int
                        or product['Id'] <= 0
                        or (expected_id is not None and product['Id'] != expected_id)
                        or product.get('ProductClassificationId') not in (43, 45, 47, 44100)):
                    raise ValueError('SG-Produktidentität nicht bestätigt')
                if product['ProductClassificationId'] == 44100:
                    if q.sg_future_contract(product, isin) is None or product.get('Currency') != 'EUR' or product.get('AssetCurrency') != 'USD' or product.get('ExchangeCode') != 'CBDE':
                        raise ValueError('SG-Faktorproduktidentität nicht bestätigt')
                    result.update(productVerified=True, excluded=True, name=product.get('Name'),
                        metadata=dict(name=product.get('Name'), status=1, underlyingType='FUTURE',
                                      contract=product['AssetRic'], type='FACTOR', productType='FACTOR'),
                        conditions={}, reason='Faktorprodukt ausgeschlossen – keine weiteren Daten erforderlich')
                    _CACHE[isin] = (time.monotonic(), copy.deepcopy(result))
                    return result
                stage = 'properties'
                properties = q.issuer_json(base+'Products/AllProperties/'+str(product['Id']), origin, timeout=12)
                q.parse_sg(product, properties, isin, market=market)
                if len(_MARKETS) >= 256 and isin not in _MARKETS:
                    _MARKETS.pop(next(iter(_MARKETS)))
                _MARKETS[isin] = market
                observed_at = datetime.now(timezone.utc).isoformat()
                _TERMS[isin] = (time.monotonic(), product, properties, observed_at, market)
            result.update(q.parse_sg(product, properties, isin, market=market))
            # UI uses normalized 1=active / 2=ended, not SG's bit flags (65).
            result['metadata']['sgStatus'] = product['Status']
            result['metadata']['status'] = (2 if product['Status'] & (2|8|16|32)
                or not product['Status'] & 1 or product.get('TodayBarrierHitDate') else 1)
            result['termsCheckedAt'] = observed_at
            conditions(product, properties, result)
            if product['Status'] & (2|8|16|32) or not product['Status'] & 1 or product.get('TodayBarrierHitDate'):
                result['reason'] = 'SG-Produkt beendet oder ausgeknockt – ausgeschlossen'
            elif terms_only:
                result['reason'] = 'SG-Stammdaten übernommen; Kurs- und Hebelabruf folgen separat'
                return result
            else:
                stage = 'dated-quotes'
                points = q.issuer_json(origin+'EmcWebApi/api/Prices/Live?productId='+str(product['Id']), origin, timeout=12)
                chart = q.parse_sg_chart_research(product, points, isin,
                    verified_id=product['Id'] if (isin in q.SG_DISCOVERY_PRODUCTS or q.sg_on_demand_candidate(isin)) else None, market=market)
                result['chartEvidence'] = chart['chartEvidence']
                associate_shared_observation(result)
                result['reason'] = ('SG-Direktimport aktiv (30 s): Stammdaten übernommen; '
                    'Geld/Brief als datierter Chartnachweis. Basispreis/KO verwenden den Zeitbezug der automatischen Abrufserie; Hebelnachweise werden separat geprüft.')
        except Exception as exc:
            result.update(sourceFailure=not result['productVerified'],
                          quoteFailureCode='SG_SOURCE_UNAVAILABLE', reason=q.sg_source_error(exc, stage))
            result = retain_last_verified_observation(cached[1] if cached else None, result, stage)
        # Time starts after completion; errors are also rate-limited.
        # User-supplied ISINs can change daily. Bound cached failed searches
        # and discovered terms; original observation clocks are preserved.
        if len(_CACHE) >= 256 and isin not in _CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        if len(_TERMS) >= 256:
            _TERMS.pop(next(iter(_TERMS)))
        _CACHE[isin] = (time.monotonic(), copy.deepcopy(result))
        return refresh_evidence(result)
