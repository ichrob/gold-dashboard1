"""Field-by-field comdirect fallback with explicit missing/conflict evidence."""
import copy
import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone
from public_product_terms import plain, ORIGIN
from term_series import observed_condition

FIELDS = ('direction', 'type', 'underlying', 'currency', 'maturity',
          'lastTradingDay', 'ratio', 'issuer', 'ko', 'strike', 'leverage',
          'koDistancePct', 'financingCosts')


def number(raw):
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?', raw):
        raise ValueError('INVALID_NUMBER')
    value = float(raw.replace('.', '').replace(',', '.'))
    if not math.isfinite(value) or value <= 0:
        raise ValueError('INVALID_NUMBER')
    return value


def parse_page(html, isin, now=None):
    from product_quotes import valid_isin
    now = now or datetime.now(timezone.utc)
    text = plain(html)
    if not valid_isin(isin) or not re.search(r'WKN:\s*'+re.escape(isin[5:11])+r'\s+ISIN:\s*'+re.escape(isin)+r'\b', text):
        raise ValueError('IDENTITY_MISMATCH')
    if 'Stammdaten ' not in text:
        raise ValueError('MISSING_TERMS')
    section = text.split('Stammdaten ', 1)[1].split('Kennzahlen ', 1)[0]
    if not re.search(r'ISIN\s+'+re.escape(isin)+r'\s+WKN\s+'+re.escape(isin[5:11])+r'\b', section):
        raise ValueError('IDENTITY_MISMATCH')
    def field(label, end):
        match = re.search(re.escape(label)+r'\s+(.+?)\s+'+re.escape(end), section)
        return match[1].strip() if match else ''
    typ = field('Typ', 'Knock Out')
    direction = 'LONG' if typ.startswith('Hebel-Bull-') else 'SHORT' if typ.startswith('Hebel-Bear-') else None
    if direction is None or 'Faktor' in typ:
        raise ValueError('UNSUPPORTED_PRODUCT')
    url = ORIGIN+'inf/zertifikate/'+isin
    values = dict(type='Knock-out Turbo', direction=direction)
    decimals = {}
    currency = field('Währung', 'Währungs\u00adgesichert')
    if currency in ('EUR', 'CHF'):
        values['currency'] = currency
    hedge = field('Währungs\u00adgesichert', 'Symbol')
    if hedge in ('Ja', 'Nein'):
        values['quanto'] = hedge == 'Ja'
    issuer = field('Emittent', 'Währung')
    if issuer and issuer != '--':
        values['issuer'] = issuer
    for key, label, end in [('ko', 'Knock Out', 'Basispreis'), ('strike', 'Basispreis', 'Laufzeitende')]:
        raw = field(label, end)
        try:
            if raw.endswith(' USD'):
                values[key] = number(raw[:-4])
                decimals[key] = len(raw[:-4].split(',')[1]) if ',' in raw[:-4] else 0
        except ValueError:
            pass
    for key, label, end in [('maturity', 'Laufzeitende', 'Letzter Handelstag'),
                             ('lastTradingDay', 'Letzter Handelstag', 'Bewert.-Tag')]:
        raw = field(label, end)
        try:
            values[key] = 'Open End' if raw == 'endlos' else datetime.strptime(raw, '%d.%m.%y').strftime('%d.%m.%Y')
        except ValueError:
            pass
    try:
        raw = field('Bez.-Verh.', 'Emittent')
        match = re.fullmatch(r'([\d.,]+)\s*:\s*1', raw)
        if match:
            values['ratio'] = 1/number(match[1])
    except ValueError:
        pass
    rows = re.findall(r'<tr\b[^>]*>\s*<th\b[^>]*>\s*Basiswert\s*</th>(.*?)</tr>', html, re.S | re.I)
    if rows and all(plain(row) == 'Gold' for row in rows) and any('goldpreis-XC0009655157' in row for row in rows):
        values['underlying'] = 'XAU/USD'
    else:
        strategy = text.split('Strategie / Bemerkung ', 1)[-1].split('Handelsplätze', 1)[0]
        future = re.search(r'Basiswert Gold Future (\d{2})/(\d{4}) \(COMEX\) USD', strategy)
        if future and 1 <= int(future[1]) <= 12:
            values['underlying'] = 'Gold Future '+future[1]+'/'+future[2]+' (COMEX) USD'
    # Kennzahlen have no field-specific date on the observed page. Keep them
    # visible as undated reference values; never borrow the LiveTrading clock.
    metrics = text.split('Kennzahlen ', 1)[-1].split('Basiswert ', 1)[0]
    leverage = re.search(r'\bHebel\s+([\d.,]+)\s', metrics)
    if leverage:
        try:
            values['leverage'] = number(leverage[1])
        except ValueError:
            pass
    distance = re.search(r'Abstand zum Knock Out\s+([\d.,]+)\s*%', metrics)
    if distance:
        try:
            values['koDistancePct'] = number(distance[1])
        except ValueError:
            pass
    observations = {key: dict(value=value, source=url, at=None,
        reviewedAt=now.isoformat(), conditionVerified=key not in ('ko', 'strike', 'leverage', 'koDistancePct'),
        timeBasis='Abrufzeit; kein separat veröffentlichter Feldzeitstempel') for key, value in values.items()}
    for key in ('ko', 'strike'):
        if key in values:
            observations[key] = observed_condition(values[key], url, isin, now.isoformat())
            observations[key]['displayDecimals'] = decimals[key]
    inactive = bool(re.search(r'Knock Out erreicht Ja\b', text))
    if values.get('maturity') not in (None, 'Open End'):
        inactive |= datetime.strptime(values['maturity'], '%d.%m.%Y').date() < now.date()
    return dict(isin=isin, observations=observations, missing=[f for f in FIELDS if f not in values],
                inactive=inactive, checkedAt=now.isoformat(), source=url)


def display_equivalent(key, primary, item):
    """Compare printed precision only; never replace the exact issuer term."""
    digits = item.get('displayDecimals')
    if key not in ('ko', 'strike') or type(digits) is not int or not 4 <= digits <= 8:
        return False
    try:
        a, b = Decimal(str(primary)), Decimal(str(item['value']))
        return a.is_finite() and b.is_finite() and a > 0 and b > 0 and a.quantize(
            Decimal(10) ** -digits, rounding=ROUND_HALF_UP) == b
    except (ValueError, TypeError, KeyError, InvalidOperation):
        return False


def apply(result, isin):
    from product_quotes import valid_isin
    from comdirect_quotes import get_observation
    if not valid_isin(isin) or result.get('isin') not in (None, isin) or result.get('sourceDisabled'):
        return result
    meta = result.get('metadata') or {}
    if meta.get('status') == 2 or result.get('terminated'):
        return result
    evidence = get_observation(isin)
    out = copy.deepcopy(result)
    fields = evidence.get('fields')
    out['comdirectFieldsBackup'] = dict(state=evidence['state'], filledFields=[], conflicts=[])
    report = out['comdirectFieldsBackup']
    if not fields:
        return out
    report.update(copy.deepcopy(fields))
    if fields['isin'] != isin:
        report['state'] = 'rejected'
        return out
    if fields['inactive']:
        report['state'] = 'inactive'
        out.update(found=False, eligible=False, fresh=False)
        return out
    observations = fields['observations']
    # Explicit primary identity contradictions prohibit all replacement.
    for key in ('direction', 'currency', 'underlying'):
        existing = meta.get(key) or result.get(key) or (result.get('conditions', {}).get(key) or {}).get('value')
        observed = observations.get(key, {}).get('value')
        if existing and observed and existing != observed:
            report['conflicts'].append(key)
    if report['conflicts']:
        report['state'] = 'conflict'
        return out
    out.setdefault('conditions', {})
    for key, item in observations.items():
        existing = (out['conditions'].get(key) or {}).get('value')
        primary_value = meta.get(key)
        if primary_value is None and key == 'strike':
            primary_value = meta.get('basisPrice') or result.get('basisPrice')
        if primary_value is None and key in ('ko', 'ratio'):
            primary_value = result.get(key)
        if existing in (None, '') and primary_value not in (None, '') and primary_value != item['value'] and not display_equivalent(key, primary_value, item):
            report['conflicts'].append(key)
            continue
        if existing is None or existing == '':
            if key in ('leverage', 'koDistancePct'):
                continue  # An undated portal metric is not the issuer leverage.
            out['conditions'][key] = copy.deepcopy(item)
            report['filledFields'].append(key)
        elif existing != item['value'] and not display_equivalent(key, existing, item):
            equivalent_turbo = (key == 'type' and meta.get('simpleTurbo') is True
                and item['value'] == 'Knock-out Turbo'
                and (existing == 'Unlimited '+('Long' if meta.get('direction') == 'LONG' else 'Short')
                     or existing == 'BEST Turbo-Optionsscheine (Open-End)' and meta.get('classificationId') == 47)
                and observations.get('direction', {}).get('value') == meta.get('direction'))
            if not equivalent_turbo:
                report['conflicts'].append(key)
    report['state'] = 'conflict' if report['conflicts'] else 'active'
    return out
