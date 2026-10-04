"""Display-only Investing.com Gold CFD; never a GCZ26 exchange quote."""
import json
import math
import re
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

URL = 'https://de.investing.com/commodities/gold'


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse(body, now=None):
    now = time.time() if now is None else now
    match = re.search(r'<script\b[^>]*\bid="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not match:
        raise ValueError('Investing.com Kursdaten fehlen')
    store = json.loads(match[1])['props']['pageProps']['state']['commodityStore']
    instrument = store['instrument']
    base, quote = instrument['base'], instrument['price']
    if (str(store['instrumentId']) != '8830' or str(base['id']) != '8830'
            or base['path'] != '/commodities/gold' or base['isCfd'] is not True
            or base['isActive'] is not True or quote['currency'] != 'USD'
            or instrument['commodityData']['unit'] != '_instr_unit_troy_ounce'):
        raise ValueError('Gold-CFD Identität nicht bestätigt')
    raw = str(quote['lastUpdateTime'])
    if not re.fullmatch(r'\d{13}', raw):
        raise ValueError('CFD Quellenzeit fehlt')
    epoch = int(raw) / 1000
    price = quote['last']
    if not numeric(price) or price <= 0 or epoch > now + 5:
        raise ValueError('CFD Kurs oder Quellenzeit ungültig')
    fresh = 0 <= now - epoch <= 120
    realtime = fresh and base.get('isOpen') is True and quote.get('isDelayed') is False
    note = ('Echtzeit CFD · laut Investing.com' if realtime else
            'Markt geschlossen · letzter CFD-Kurs' if base.get('isOpen') is False else
            'CFD-Kurs verzögert' if quote.get('isDelayed') is True else
            'CFD-Kurs nicht aktuell' if not fresh else 'CFD · Echtzeitstatus unbestätigt')
    return dict(price=price, at=datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
                changePct=quote.get('changePcr') if numeric(quote.get('changePcr')) else None,
                change=quote.get('change') if numeric(quote.get('change')) else None,
                symbol='Gold CFD', source='Investing.com', sourceUrl=URL, kind='cfd',
                note=note, realtimeCfd=realtime, isExchangeRealtime=False,
                changeLabel='zum Vortagesschluss')


def fetch():
    request = Request(URL, headers={'User-Agent': 'Mozilla/5.0 (Bob gold cards)',
                                   'Accept': 'text/html', 'Cache-Control': 'no-cache'})
    with urlopen(request, timeout=6) as response:
        if response.url != URL:
            raise ValueError('Unerwartete CFD-Weiterleitung')
        body = response.read(2000001)
        if len(body) > 2000000:
            raise ValueError('CFD Seite zu groß')
        return parse(body.decode('utf-8'))
