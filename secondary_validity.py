"""Bounded secondary term research. Only field-local dates establish validity."""
import copy
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import unescape
from zoneinfo import ZoneInfo
from urllib.request import Request
from public_product_terms import open_public_page

TTL = 300
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='term-evidence')
_LOCK = threading.Lock()
_CACHE = {}
_PENDING = set()


def plain(html):
    return ' '.join(unescape(re.sub('<[^>]+>', ' ', html)).split())


def sources(isin):
    return [('comdirect', 'https://www.comdirect.de/inf/zertifikate/'+isin),
            ('finanzen.ch', 'https://www.finanzen.ch/derivate/'+isin.lower())]


def parse_page(html, isin, provider, url, now=None):
    now = now or datetime.now(timezone.utc)
    html = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', html, flags=re.S|re.I)
    text = plain(html)
    headers = ' '.join(plain(x) for x in re.findall(r'<h[12]\b[^>]*>(.*?)</h[12]>', html, re.S|re.I))
    if isin not in headers and not re.search(r'WKN:\s*'+isin[5:11]+r'\s+ISIN:\s*'+isin+r'\b', text):
        raise ValueError('Produktidentität nicht bestätigt')
    # Only term label/value pairs in table rows are considered. A quote clock,
    # issue date or page timestamp outside that pair can never date the terms.
    observations = {}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.S|re.I):
        cells = [plain(c) for c in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', row, re.S|re.I)]
        for i in range(0, len(cells)-1, 2):
            label, raw = cells[i:i+2]
            key = 'strike' if re.match(r'^(Basispreis|Strike)\b', label, re.I) else 'ko' if re.match(r'^(Knock[ -]?Out(?:-Barriere)?|Knockout-Barriere|Stoppschwelle)\b', label, re.I) else None
            if not key or re.search(r'Abstand|erreicht|Zeit|Prozent|%', label, re.I):
                continue
            if not ('USD' in label+' '+raw or provider == 'finanzen.ch' and re.search(r'Gold\s*\(USD\)', headers)):
                continue
            number = re.match(r"^([0-9][0-9.,'’]*)\b", raw)
            if not number:
                continue
            token = number[1]
            if provider == 'comdirect':
                if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?', token):
                    continue
                token = token.replace('.', '').replace(',', '.')
            else:
                if not re.fullmatch(r"(?:\d+|\d{1,3}(?:['’]\d{3})+)(?:\.\d+)?", token):
                    continue
                token = token.replace("'", '').replace('’', '')
            try:
                value = Decimal(token)
                if not value.is_finite() or value <= 0:
                    continue
            except InvalidOperation:
                continue
            # Accept only an explicitly labelled effective date or date appended
            # in parentheses to this field label, never arbitrary row dates.
            date = re.search(r'(?:gültig (?:am|ab)|Stand(?: vom)?|Gültigkeitsdatum)\s*:?\s*(\d{2}\.\d{2}\.\d{4})', label+' '+raw, re.I)
            if not date:
                date = re.search(r'\((\d{2}\.\d{2}\.\d{4})\)\s*$', label)
            date_text = date[1] if date else None
            try:
                dated = bool(date_text and datetime.strptime(date_text, '%d.%m.%Y').date() == now.astimezone(ZoneInfo('Europe/Zurich')).date())
            except ValueError:
                dated = False
            item = dict(value=float(value), currency='USD', displayDecimals=max(0, -value.as_tuple().exponent),
                        dateText=date_text, at=None, source=url, reviewedAt=now.isoformat(),
                        conditionVerified=dated, validityUnconfirmed=not dated, secondary=True)
            if key in observations and observations[key] != item:
                item.update(conflict=True, conditionVerified=False)
            observations[key] = item
    return dict(provider=provider, source=url, isin=isin, checkedAt=now.isoformat(),
                state='observed' if observations else 'unavailable', terms=observations)


def fetch(isin, provider, url):
    try:
        req = Request(url, headers={'User-Agent':'Bob public product research', 'Accept':'text/html'})
        with open_public_page(req, timeout=6) as response:
            if not response.url.startswith(url.split('/')[0]+'//'+url.split('/')[2]+'/'):
                raise ValueError('Unerwartete Weiterleitung')
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('Antwort zu groß')
        return parse_page(data.decode('utf-8'), isin, provider, url)
    except Exception:
        return dict(provider=provider, source=url, isin=isin, state='unavailable', terms={},
                    checkedAt=datetime.now(timezone.utc).isoformat())


def _refresh(isin):
    try:
        rows = [fetch(isin, provider, url) for provider, url in sources(isin)]
        with _LOCK:
            if len(_CACHE) >= 128:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[isin] = (time.monotonic(), rows)
    finally:
        with _LOCK:
            _PENDING.discard(isin)


def get_evidence(isin):
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < TTL:
            return copy.deepcopy(cached[1])
        if isin not in _PENDING and len(_PENDING) < 8:
            _PENDING.add(isin)
            _POOL.submit(_refresh, isin)
    return [dict(provider=name, source=url, isin=isin, state='checking', terms={}) for name, url in sources(isin)]


def current(term, now):
    try:
        return (term.get('conditionVerified') is True and not term.get('conflict') and not term.get('revoked')
                and datetime.strptime(term['dateText'], '%d.%m.%Y').date() == now.astimezone(ZoneInfo('Europe/Zurich')).date()
                and 0 <= (now-datetime.fromisoformat(term['reviewedAt'])).total_seconds() <= 86400)
    except (KeyError, ValueError, TypeError):
        return False


def matches(term, value):
    try:
        if value is None:
            return False
        digits = term['displayDecimals']
        return 0 <= digits <= 8 and Decimal(str(value)).quantize(Decimal(10)**-digits) == Decimal(str(term['value']))
    except (KeyError, TypeError, InvalidOperation):
        return False


def apply(result, isin, now=None):
    now = now or datetime.now(timezone.utc)
    meta = result.get('metadata', {})
    if (result.get('isin') != isin or not result.get('productVerified') or meta.get('status') != 1
            or meta.get('termsDated') is not False or meta.get('termsFixed')):
        return result
    out = copy.deepcopy(result)
    rows = get_evidence(isin)
    out['secondaryValidity'] = dict(sources=rows, state='checking' if any(r['state']=='checking' for r in rows) else 'open', refreshSeconds=TTL)
    accepted = []
    for key in ('strike', 'ko'):
        baseline = meta.get(key) or out.get('conditions', {}).get(key, {}).get('value')
        candidates = []
        conflicts = []
        for row in rows:
            term = row.get('terms', {}).get(key)
            if not term:
                continue
            if not matches(term, baseline):
                term['assessment'] = 'Abweichender Wert; nicht übernommen'
                if current(term, now):
                    conflicts.append(term)
            elif current(term, now):
                term['assessment'] = 'Datierter Wert stimmt mit Produktquelle überein'
                candidates.append(term)
            else:
                term['assessment'] = 'Wert verglichen; gültiger Datenstand fehlt'
        if candidates and not conflicts:
            out.setdefault('conditions', {})[key] = copy.deepcopy(candidates[0])
            accepted.append(key)
    if accepted:
        out['secondaryValidity'].update(state='confirmed' if len(accepted)==2 else 'partial', confirmedFields=accepted)
    if len(accepted) == 2:
        out['metadata'].update(termsDated=True, termsDate=out['conditions']['ko']['dateText'])
        out['termsSource'] = 'Sekundärquelle · '+out['conditions']['ko']['source']
        out['termsSourceUrl'] = out['conditions']['ko']['source']
        out['reason'] = result.get('reason', '')+' · Basispreis und KO durch datierte Sekundärquelle bestätigt'
    return out
