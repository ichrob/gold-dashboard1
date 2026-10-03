"""Bounded public exchange research. Retrieval time is never a market timestamp."""
import re
import time
import threading
from html import unescape
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ORIGIN = 'https://www.boerse-stuttgart.de/'
_CACHE = {}
_LOCK = threading.Lock()
TTL = 900

def parse_page(html, isin, now=None):
    now = now or datetime.now(timezone.utc)
    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', html, flags=re.S|re.I)
    text = ' '.join(unescape(re.sub(r'<[^>]+>', ' ', text)).split())
    section = text.split('Stammdaten ', 1)[-1].split('Produktbeschreibung', 1)[0]
    def field(label, end):
        m = re.search(re.escape(label)+r'\s+(.+?)\s+'+re.escape(end), section)
        if not m:
            raise ValueError('Produktfeld fehlt: '+label)
        return m[1].strip()
    if field('ISIN', 'Symbol') != isin or field('WKN', 'ISIN') != isin[5:11]:
        raise ValueError('Produktidentität stimmt nicht überein')
    def number(label, end):
        raw = field(label, end)
        m = re.fullmatch(r'([\d.,]+)(?: \[USD\])?', raw)
        if not m:
            raise ValueError('Ungültiges Zahlenfeld')
        value = float(m[1].replace('.', '').replace(',', '.'))
        if value <= 0:
            raise ValueError('Nichtpositives Zahlenfeld')
        return value
    underlying = field('Basiswert', 'Basispreis in [Währung]')
    contract = None
    if underlying == 'Gold Spot':
        underlying = 'XAU/USD'
    else:
        m = re.fullmatch(r'Gold Future (\d{2})/(\d{4}) \(COMEX\) USD', underlying)
        if not m or not 1 <= int(m[1]) <= 12:
            raise ValueError('Gold-Basiswert nicht eindeutig')
        contract = 'GC'+'FGHJKMNQUVXZ'[int(m[1])-1]+m[2][-2:]
    side = field('Optionsart', 'Basiswert').lower()
    if side not in ('put', 'call') or field('Nominalwährung', 'Abwicklungswährung') != 'EUR':
        raise ValueError('Richtung oder Währung nicht bestätigt')
    strike_raw = field('Basispreis in [Währung]', 'Knockout-Barriere')
    ko_raw = field('Knockout-Barriere', 'Cap in [Währung]')
    if not strike_raw.endswith('[USD]') or not ko_raw.endswith('[USD]'):
        raise ValueError('Basispreis-/KO-Währung fehlt')
    strike = number('Basispreis in [Währung]', 'Knockout-Barriere')
    ko = number('Knockout-Barriere', 'Cap in [Währung]')
    ratio = number('Bezugsverhältnis', 'Ausübungsart')
    maturity = field('Letzter Bewertungstag', 'Zahltag')
    last_day = field('Letzter Börsenhandelstag', 'Handelszeit')
    inactive = 'Das Wertpapier wurde ausgeknockt.' in text
    expired = False
    if last_day != 'Endlos':
        expired = datetime.strptime(last_day, '%d.%m.%Y').date() < now.date()
    halted = 'Ein Handel ist zur Zeit nicht möglich.' in text
    url = ORIGIN+'de-de/produkte/hebelprodukte/knock-out-produkte/stuttgart/'+isin[5:11].lower()+'/'
    values = dict(ratio=ratio, underlying=underlying, type='Knock-out Turbo',
                  maturity='Open End' if maturity == 'Endlos' else maturity, currency='EUR')
    # Dynamic strike, barrier and contract have no labelled effective timestamp
    # in this HTML. Keep them visible, never turn retrieval into validity proof.
    conditions = {k:dict(value=v, source=url, at=None, conditionVerified=True,
                         reviewedAt=now.isoformat()) for k,v in values.items()}
    if contract:
        conditions.pop('underlying')  # Rolled futures require a dated contract proof.
    reason = ('Produkt ausgeknockt – ausgeschlossen' if inactive else
              'Produkt beendet – ausgeschlossen' if expired else
              'Produktbedingungen abgerufen; datierte Geld-/Briefkurse und Stand der veränderlichen Bedingungen fehlen')
    return dict(isin=isin, found=False, eligible=False, fresh=False, productVerified=True,
                source='Börse Stuttgart', sourceUrl=url, checkedAt=now.isoformat(),
                reason=reason, conditions=conditions,
                metadata=dict(direction='SHORT' if side=='put' else 'LONG',
                              underlying=underlying, underlyingType='FUTURE' if contract else 'SPOT',
                              contract=contract, ko=ko, strike=strike, ratio=ratio,
                              status=2 if inactive or expired else 1,
                              tradingHalted=halted, lastTradingDay=last_day,
                              termsDated=False, observedAt=now.isoformat()),
                observedTerms=dict(strike=strike, ko=ko, contract=contract,
                                   underlying=underlying, source=url, effectiveAt=None),
                isDegiroQuote=False)

def get_product(isin):
    from product_quotes import valid_isin
    if not valid_isin(isin) or not isin.startswith('DE000'):
        return dict(isin=isin, found=False, productVerified=False, eligible=False, fresh=False)
    with _LOCK:
        item = _CACHE.get(isin)
        if item and time.monotonic()-item[0] < TTL:
            return item[1]
    url = ORIGIN+'de-de/produkte/hebelprodukte/knock-out-produkte/stuttgart/'+isin[5:11].lower()+'/'
    try:
        req = Request(url, headers={'User-Agent':'Bob public product research', 'Accept':'text/html'})
        with urlopen(req, timeout=12) as response:
            if not response.url.startswith(ORIGIN):
                raise ValueError('Unerwartete Weiterleitung')
            body = response.read(2_000_001)
        if len(body)>2_000_000:
            raise ValueError('Antwort zu groß')
        result = parse_page(body.decode('utf-8'), isin)
    except Exception:
        result = dict(isin=isin, found=False, productVerified=False, eligible=False, fresh=False,
                      source='Börse Stuttgart', sourceUrl=url, sourceFailure=True,
                      reason='Börse-Stuttgart-Produktdaten nicht erreichbar oder nicht eindeutig zugeordnet')
    with _LOCK:
        if len(_CACHE)>=256:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin]=(time.monotonic(), result)
    return result
