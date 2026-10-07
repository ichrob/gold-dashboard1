"""Public comdirect Informer product terms, with explicit source/quote separation.
No account, residency assertion or order endpoint is used. Unavailable terms
are never inferred from a product name, a historical price or another ISIN.
"""
import re
import time
import threading
from datetime import datetime, timezone
from html import unescape
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError

ORIGIN='https://www.comdirect.de/'
_CACHE={}
_LOCK=threading.Lock()
# Terminal event explicitly confirmed on the exchange product page on 2026-10-03.
# A later missing page must never reactivate an already knocked-out product.
TERMINAL={
 'DE000FG7MTA6':dict(status='knocked_out',confirmedOn='2026-10-03',
    source='Börse Stuttgart',sourceUrl='https://www.boerse-stuttgart.de/de-de/produkte/hebelprodukte/knock-out-produkte/stuttgart/fg7mta/')
}

def plain(html):
    clean=re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',html,flags=re.S|re.I)
    return ' '.join(unescape(re.sub(r'<[^>]+>',' ',clean)).split())

def parse_page(html,isin,now=None):
    now=now or datetime.now(timezone.utc)
    text=plain(html)
    if not re.search(r'WKN:\s*'+re.escape(isin[5:11])+r'\s+ISIN:\s*'+re.escape(isin)+r'\b',text):
        raise ValueError('IDENTITY_MISMATCH')
    section=text.split('Stammdaten ',1)[-1].split('Kennzahlen ',1)[0]
    def field(label,end):
        m=re.search(re.escape(label)+r'\s+(.+?)\s+'+re.escape(end),section)
        if not m:raise ValueError('MISSING_TERMS')
        return m[1].strip()
    if field('ISIN','WKN')!=isin or not re.search(r'WKN\s+'+re.escape(isin[5:11])+r'\b',section):
        raise ValueError('INCOMPLETE_IDENTITY')
    typ=field('Typ','Knock Out')
    direction='LONG' if typ.startswith('Hebel-Bull-') else 'SHORT' if typ.startswith('Hebel-Bear-') else None
    if direction is None:raise ValueError('UNKNOWN_PRODUCT_TYPE')
    def numeric(raw):
        if not re.fullmatch(r'\d[\d.]*,\d+|\d+',raw):raise ValueError('INVALID_NUMBER')
        value=float(raw.replace('.','').replace(',','.'))
        if value<=0:raise ValueError('INVALID_NUMBER')
        return value
    ratio_raw=field('Bez.-Verh.','Emittent')
    m=re.fullmatch(r'([\d.,]+)\s*:\s*1',ratio_raw)
    if not m:raise ValueError('INVALID_RATIO')
    ratio=1/numeric(m[1])
    currency=field('Währung','Währungs\u00adgesichert')
    if currency!='EUR':raise ValueError('UNKNOWN_CURRENCY')
    # Inspect only the Basiswert table row: the page navigation also links Gold.
    underlying_rows=re.findall(r'<tr\b[^>]*>\s*<th\b[^>]*>\s*Basiswert\s*</th>(.*?)</tr>',html,re.S|re.I)
    spot=any('goldpreis-XC0009655157' in row for row in underlying_rows) and all(plain(row)=='Gold' for row in underlying_rows)
    contract=None
    if spot:underlying='XAU/USD'
    else:
        strategy=text.split('Strategie / Bemerkung ',1)[-1].split('Handelsplätze',1)[0]
        future=re.search(r'Basiswert Gold Future (\d{2})/(\d{4}) \(COMEX\) USD',strategy)
        if not future or not 1<=int(future[1])<=12:raise ValueError('UNKNOWN_UNDERLYING')
        contract='GC'+'FGHJKMNQUVXZ'[int(future[1])-1]+future[2][-2:]
        underlying='Gold Future '+future[1]+'/'+future[2]+' (COMEX) USD'
    def usd(label,end):
        raw=field(label,end)
        m=re.fullmatch(r'([\d.,]+)\s+(USD|--)',raw)
        if not m or m[2]=='--' and not contract:raise ValueError('UNKNOWN_TERM_CURRENCY')
        return numeric(m[1])
    ko=usd('Knock Out','Basispreis');strike=usd('Basispreis','Laufzeitende')
    maturity=field('Laufzeitende','Letzter Handelstag')
    if maturity=='endlos':maturity='Open End'
    else:maturity=datetime.strptime(maturity,'%d.%m.%y').strftime('%d.%m.%Y')
    status_values=set(re.findall(r'Knock Out erreicht (Ja|Nein)',text))
    if len(status_values)!=1:raise ValueError('UNKNOWN_PRODUCT_STATUS')
    inactive=status_values=={'Ja'}
    if maturity!='Open End':inactive=inactive or datetime.strptime(maturity,'%d.%m.%Y').date()<now.date()
    url=ORIGIN+'inf/zertifikate/'+isin
    vals=dict(ratio=ratio,underlying=underlying,type='Knock-out Turbo',maturity=maturity,currency=currency)
    conditions={key:dict(value=value,at=None,source=url,conditionVerified=True,reviewedAt=now.isoformat()) for key,value in vals.items()}
    from term_series import observed_condition
    for key, value in (('strike', strike), ('ko', ko)):
        conditions[key] = observed_condition(value, url, isin, now.isoformat())
    if contract:conditions.pop('underlying')
    return dict(isin=isin,found=False,eligible=False,fresh=False,productVerified=True,
        source='comdirect Informer · öffentliche Produktdaten',sourceUrl=url,checkedAt=now.isoformat(),
        reason='Produkt ausgeknockt oder beendet – ausgeschlossen' if inactive else 'Produktbedingungen übernommen; aktuelle Kurszeiten und der Datenstand veränderlicher Bedingungen bleiben separat erforderlich',
        conditions=conditions,isDegiroQuote=False,
        metadata=dict(direction=direction,underlying=underlying,underlyingType='FUTURE' if contract else 'SPOT',
            contract=contract,ratio=ratio,strike=strike,ko=ko,status=2 if inactive else 1,
            tradingHalted=False,termsDated=False,observedAt=now.isoformat()),
        observedTerms=dict(strike=strike,ko=ko,contract=contract,underlying=underlying,source=url,effectiveAt=None))

def open_public_page(request, timeout=12):
    # Public CIF redirect uses an ordinary anonymous session cookie.
    # A fresh, isolated jar is discarded after this one request.
    return build_opener(HTTPCookieProcessor(CookieJar())).open(request, timeout=timeout)

def get_product(isin):
    from product_quotes import valid_isin
    if not valid_isin(isin) or not isin.startswith('DE000'):
        return dict(isin=isin,found=False,eligible=False,fresh=False,productVerified=False)
    if isin in TERMINAL:
        r=TERMINAL[isin]
        return dict(isin=isin,found=False,eligible=False,fresh=False,productVerified=True,
                    source=r['source'],sourceUrl=r['sourceUrl'],checkedAt=None,
                    conditions={},observedTerms={},reason='Bestätigtes Knock-out: Produkt dauerhaft ausgeschlossen',
                    metadata=dict(status=2,tradingHalted=True,termsDated=False,
                        direction='LONG',underlying='XAU/USD',underlyingType='SPOT',
                        ko=4143.437,strike=4143.437,ratio=.1,contract=None),terminalEvidence=r)
    with _LOCK:
        item=_CACHE.get(isin)
        if item and time.monotonic()-item[0]<900:return item[1]
    url=ORIGIN+'inf/zertifikate/'+isin
    try:
        req=Request(url,headers={'User-Agent':'Bob public product research','Accept':'text/html'})
        with open_public_page(req,timeout=12) as response:
            if not response.url.startswith(ORIGIN):raise ValueError('UNEXPECTED_REDIRECT')
            data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('RESPONSE_TOO_LARGE')
        result=parse_page(data.decode('utf-8'),isin)
    except Exception as exc:
        code='HTTP_'+str(exc.code) if isinstance(exc,HTTPError) else 'CONNECTION' if isinstance(exc,(URLError,OSError)) else str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z_]+',str(exc)) else 'INVALID_RESPONSE'
        result=dict(isin=isin,found=False,eligible=False,fresh=False,productVerified=False,
            source='comdirect Informer',sourceUrl=url,sourceFailure=True,sourceFailureCode=code,
            reason='Produktrecherche nicht verfügbar ('+code+'); vorhandene datierte Nachweise bleiben erforderlich')
    with _LOCK:
        if len(_CACHE)>=256:_CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin]=(time.monotonic(),result)
    return result
