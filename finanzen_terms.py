"""Missing SG gold terms from finanzen.ch; never import its quotes or clocks.

The public page attributes terms to dp Derivative Partners. Its underlying
quote can be years old, so quote/ratio/leverage fields are deliberately ignored.
"""
import copy
import re
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from public_product_terms import plain
from term_series import observed_condition

ORIGIN = 'https://www.finanzen.ch/'
FIELDS = ('type', 'underlying', 'currency', 'maturity', 'ko', 'strike')
_CACHE = {}
_LOCK = threading.Lock()


def parse_page(html, isin, now=None):
    from product_quotes import valid_isin
    if not valid_isin(isin):
        raise ValueError('INVALID_ISIN')
    now = now or datetime.now(timezone.utc)
    text = plain(html)
    if 'Quelle: dp Derivative Partners' not in text:
        raise ValueError('SOURCE_MISSING')
    terms = text.split('Stammdaten Name ', 1)[-1].split('Anzeige', 1)[0]
    def field(label, end):
        match = re.search(re.escape(label)+r'\s+(.+?)\s+'+re.escape(end), terms)
        if not match:
            raise ValueError('MISSING_TERMS')
        return match[1].strip()
    if (field('ISIN', 'Art') != isin
            or field('Art', 'Typ') != 'Warrant with Knock-Out'
            or not re.search(r'Emittent Société Générale(?:\s|$)', terms)
            or not re.search(r'Basiswerte Name ISIN Gold \(USD\) XD0002747026\b', text)):
        raise ValueError('IDENTITY_MISMATCH')
    side = field('Typ', 'Ausübungsstil')
    currency = field('Währung', 'Währungssicherheit')
    if side not in ('Bear', 'Bull') or currency not in ('CHF', 'EUR'):
        raise ValueError('UNSUPPORTED_PRODUCT')
    maturity = field('Fälligkeitstag', 'Rückzahlungsdatum')
    datetime.strptime(maturity, '%d.%m.%Y')
    section = text.split('Wichtige Stammdaten und Kennzahlen ', 1)[-1].split('Basiswert:', 1)[0]
    def number(label):
        match = re.search(r'\b'+re.escape(label)+r'\s+(\d{1,3}(?:[’\']\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?=\s)', section)
        if not match:
            raise ValueError('MISSING_NUMBER')
        value = float(match[1].replace('’', '').replace("'", ''))
        if value <= 0:
            raise ValueError('INVALID_NUMBER')
        return value
    url = ORIGIN+'derivate/'+isin.lower()
    values = dict(type='Knock-out Warrant', underlying='XAU/USD', currency=currency,
                  maturity=maturity, ko=number('Knock-Out'), strike=number('Strike'))
    conditions = {key: dict(value=value, at=None, source=url,
                           conditionVerified=True, reviewedAt=now.isoformat())
                  for key, value in values.items()}
    for key in ('ko', 'strike'):
        conditions[key] = observed_condition(values[key], url, isin, now.isoformat())
    return dict(isin=isin, direction='SHORT' if side == 'Bear' else 'LONG',
                currency=currency, conditions=conditions, sourceUrl=url,
                source='finanzen.ch · dp Derivative Partners', checkedAt=now.isoformat())


def fetch(isin):
    # Serialize and cache successes/failures: no repeated polling per screen.
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic() < cached[0]:
            return copy.deepcopy(cached[1])
        try:
            request = Request(ORIGIN+'derivate/'+isin.lower(), headers={
                'User-Agent': 'Bob public product research', 'Accept': 'text/html'})
            with urlopen(request, timeout=8) as response:
                if not response.url.startswith(ORIGIN):
                    raise ValueError('UNEXPECTED_REDIRECT')
                body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError('RESPONSE_TOO_LARGE')
            result = dict(state='available', **parse_page(body.decode('utf-8'), isin))
        except Exception as exc:
            code = ('HTTP_'+str(exc.code) if isinstance(exc, HTTPError)
                    else str(exc) if isinstance(exc, ValueError) and re.fullmatch('[A-Z_]+', str(exc))
                    else 'SOURCE_UNAVAILABLE')
            result = dict(state='unavailable', code=code, source='finanzen.ch')
        if len(_CACHE) >= 256:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin] = (time.monotonic()+900, result)
        return copy.deepcopy(result)


def apply(primary, isin):
    from product_quotes import valid_isin
    meta = primary.get('metadata') or {}
    conditions = primary.get('conditions') or {}
    missing = [key for key in FIELDS if not (conditions.get(key) or {}).get('value')]
    if (not valid_isin(isin) or primary.get('isin') != isin
            or not primary.get('productVerified') or primary.get('sourceDisabled')
            or meta.get('status') != 1 or meta.get('underlyingType') != 'SPOT'
            or meta.get('issuerExchangeCode') not in ('CBSW', 'CBDE')
            or primary.get('eligible') or not missing):
        return primary
    backup = fetch(isin)
    out = copy.deepcopy(primary)
    out['termsBackup'] = {key: backup[key] for key in
                          ('state', 'code', 'source', 'sourceUrl', 'checkedAt') if key in backup}
    if backup.get('state') != 'available':
        return out
    currency = meta.get('currency') or (conditions.get('currency') or {}).get('value')
    if backup['direction'] != meta.get('direction') or backup['currency'] != currency:
        out['termsBackup'].update(state='rejected', code='IDENTITY_MISMATCH')
        return out
    # Existing issuer values always win, including their effective dates.
    out.setdefault('conditions', {})
    for key in missing:
        out['conditions'][key] = backup['conditions'][key]
    out['termsBackup'].update(state='active', filledFields=missing)
    return out
