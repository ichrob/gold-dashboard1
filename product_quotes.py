"""Free issuer quotes. Fixed origin, bounded reads; never substitute fetch time for quote time."""
import json
import base64
import math
import re
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

MAX_AGE_SECONDS = 60
_CACHE = {}
_LOCK = threading.Lock()

def valid_isin(value):
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', value) or re.match(r'DE(?=[0O]{3})(?=[0O]{0,2}O)', value):
        return False
    digits = ''.join(str(ord(c)-55) if c.isalpha() else c for c in value)
    return sum((int(c)*2//10+int(c)*2%10) if i%2 else int(c) for i,c in enumerate(reversed(digits)))%10 == 0

def number(value):
    value = value.strip().replace('\xa0', '').replace(' ', '')
    if not re.fullmatch(r'\d+(?:\.\d{3})*(?:,\d+)?', value):
        raise ValueError('Ungültige Kurszahl')
    result = float(value.replace('.', '').replace(',', '.'))
    if not math.isfinite(result):
        raise ValueError('Ungültige Kurszahl')
    return result

class QuotePage(HTMLParser):
    def __init__(self, isin):
        super().__init__()
        self.isin, self.fields, self.identifiers = isin, {}, []
        self.capture = None
        self.depth = 0
        self.schema = False
        self.schema_text = ''
        self.text = []
        self.euro_fields = set()
        self.models = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('data-react-props'):
            try:
                props = json.loads(base64.b64decode(a['data-react-props']))
                model = json.loads(props.get('initialDataModel', {}).get('priceDataResponse', '{}'))
                if model.get('result', {}).get('isin') == self.isin:
                    self.models.append(model)
            except (ValueError, TypeError, AttributeError):
                pass
        if self.capture:
            self.depth += 1
        elif a.get('data-item', '').endswith(self.isin) and a.get('data-field'):
            if a['data-field'] in ('bid', 'ask') and re.search(r'€\s*$', ''.join(self.text[-3:])):
                self.euro_fields.add(a['data-field'])
            self.capture = [a['data-field'], '']
            self.depth = 1
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self.schema = True
            self.schema_text = ''
    def handle_data(self, data):
        if self.schema:
            self.schema_text += data
        elif self.capture:
            self.capture[1] += data
        self.text.append(data)
    def handle_endtag(self, tag):
        if self.capture:
            self.depth -= 1
            if self.depth == 0:
                key, value = self.capture
                self.fields.setdefault(key, []).append(value.strip())
                self.capture = None
        if tag == 'script' and self.schema:
            self.schema = False
            try:
                obj = json.loads(self.schema_text)
                if obj.get('@type') == 'FinancialProduct':
                    self.identifiers.append(obj)
            except (ValueError, AttributeError):
                pass
    def field(self, key):
        values = set(self.fields.get(key, []))
        if len(values) != 1:
            raise ValueError('Fehlende oder widersprüchliche Produktdaten: '+key)
        return values.pop()

def freshness(result, now=None):
    result = dict(result)
    now = now or datetime.now(timezone.utc)
    try:
        age = (now-datetime.fromisoformat(result['quoteAt'])).total_seconds()
        result['ageSeconds'] = round(age, 1)
        result['fresh'] = -5 <= age <= MAX_AGE_SECONDS
    except (KeyError, ValueError, TypeError):
        result['fresh'] = False
    result['eligible'] = bool(result.get('found') and result['fresh'] and result.get('marketOpen'))
    if result.get('found') and not result['eligible']:
        result['reason'] = 'Kurs veraltet, Markt geschlossen oder Zeitstempel nicht prüfbar'
    return result

def parse_bnp(html, isin, now=None):
    now = now or datetime.now(timezone.utc)
    p = QuotePage(isin)
    p.feed(html)
    identities = [x for x in p.identifiers if x.get('identifier') == isin]
    if len(identities) != 1 or 'GOLD' not in identities[0].get('name', '').upper():
        raise ValueError('Produktidentität oder Gold-Basiswert nicht bestätigt')
    name = identities[0]['name']
    if p.euro_fields != {'bid', 'ask'}:
        raise ValueError('Kurswährung EUR nicht bestätigt')
    # Only product-tagged timestamp; the underlying has its own, unrelated clock.
    quote_at = datetime.strptime(p.field('quotetime'), '%d.%m.%Y %H:%M:%S').replace(tzinfo=ZoneInfo('Europe/Berlin'))
    bid, ask, leverage = number(p.field('bid')), number(p.field('ask')), number(p.field('leverage'))
    if bid <= 0 or ask < bid or leverage < 1 or number(p.field('bidsize')) <= 0 or number(p.field('asksize')) <= 0:
        raise ValueError('Kein gültiger zweiseitiger Kurs')
    text = ' '.join(' '.join(p.text).split())
    ko = re.search(r'Knock-Out Schwelle\s*\('+re.escape(quote_at.strftime('%d.%m.%Y'))+r'\)\s*([\d.,]+)\s*USD', text)
    if ko:
        ko_value = number(ko.group(1))
    else:
        values = []
        for model in p.models:
            rows = model['result'].get('underlyingItems', [])
            if len(rows) == 1 and rows[0].get('underlyingISIN') == 'USFX00000XAU':
                stamp = datetime.fromisoformat(model['responseDate'].replace('Z', '+00:00'))
                if abs((stamp-quote_at).total_seconds()) <= 60:
                    values.append(float(rows[0]['knockOutAbsolute']))
        if not values or len(set(values)) != 1 or values[0] <= 0:
            raise ValueError('Aktuelle Knock-Out Schwelle in USD fehlt')
        ko_value = values[0]
    direction = 'LONG' if 'LONG' in name.upper() else 'SHORT' if 'SHORT' in name.upper() else ''
    if not direction:
        raise ValueError('Produktrichtung fehlt')
    result = dict(found=True, isin=isin, name=name, source='BNP Paribas · Emittent OTC',
                  sourceUrl='https://derivate.bnpparibas.com/product-details/'+isin+'/',
                  checkedAt=now.isoformat(), quoteAt=quote_at.astimezone(timezone.utc).isoformat(),
                  bid=bid, ask=ask, price=ask, leverage=leverage, ko=ko_value,
                  spread=round(ask-bid, 8), spreadPct=round((ask-bid)/ask*100, 4),
                  currency='EUR', direction=direction, marketOpen='Markt geöffnet' in text,
                  isDegiroQuote=False, maxAgeSeconds=MAX_AGE_SECONDS)
    return freshness(result, now)

def get_quote(isin):
    isin = str(isin or '').strip().upper()
    if not valid_isin(isin):
        return dict(found=False, eligible=False, fresh=False, reason='ISIN-Prüfziffer ungültig')
    with _LOCK:
        cached = _CACHE.get(isin)
        if cached and time.monotonic()-cached[0] < 15:
            return freshness(cached[1])
    # No account, key, subscription, arbitrary URL, or broker request.
    url = 'https://derivate.bnpparibas.com/product-details/'+isin+'/'
    try:
        request = Request(url, headers={'User-Agent':'Bob/1.6 public product research','Accept':'text/html'})
        with urlopen(request, timeout=12) as response:
            if not response.url.startswith('https://derivate.bnpparibas.com/'):
                raise ValueError('Unerwartete Weiterleitung')
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError('Produktseite zu groß')
        result = parse_bnp(body.decode('utf-8'), isin)
    except Exception:
        result = dict(found=False, eligible=False, fresh=False, isin=isin, source='Öffentliche Emittentenrecherche',
                      reason='Keine verlässlich datierten Kurse verfügbar (Quelle nicht unterstützt oder nicht erreichbar)',
                      checkedAt=datetime.now(timezone.utc).isoformat())
    with _LOCK:
        if len(_CACHE) >= 256:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin] = (time.monotonic(), result)
    return freshness(result)
