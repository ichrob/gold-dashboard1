"""Public issuer observations for existing holdings, including factor products.

This module cannot approve a product, estimate a quote, or access a broker.
SG chart points remain chart observations, never executable bid/ask evidence.
"""
import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
import threading
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo
from snaptrade_portfolio import isin as valid_isin
from snaptrade_trades import decimal

BNP = 'https://derivate.bnpparibas.com/'
SG = 'https://www.sg-zertifikate.de/'
COMDIRECT = 'https://www.comdirect.de/'
MAX_AGE = 90
_IDENTITIES = {}
_LOCK = threading.Lock()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read_json(url, headers=None):
    if not url.startswith((BNP, SG)):
        raise ValueError('Unexpected source')
    request = Request(url, headers={'Accept':'application/json', 'User-Agent':'Bob public holdings observation',
                                    'Cache-Control':'no-cache', **(headers or {})})
    with build_opener(NoRedirect()).open(request, timeout=5) as response:
        body = response.read(500001)
    if len(body) > 500000:
        raise ValueError('Oversized source')
    return json.loads(body)


def stamp(value, bnp=False):
    if not isinstance(value, str) or 'T' not in value:
        return None
    try:
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if at.tzinfo is None:
            if not bnp:
                return None
            # BNP's bidDate/askDate use its German product-page local time.
            zone = ZoneInfo('Europe/Berlin')
            if at.replace(tzinfo=zone,fold=0).utcoffset()!=at.replace(tzinfo=zone,fold=1).utcoffset():
                return None
            at = at.replace(tzinfo=zone)
        return at.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def freshness(observation, now=None):
    q = copy.deepcopy(observation)
    now = now or datetime.now(timezone.utc)
    for side in ('bid', 'ask'):
        at = stamp(q.get(side+'At'))
        value = decimal(q.get(side))
        q[side+'Fresh'] = bool(at and value is not None and value > 0 and
                              0 <= (now-datetime.fromisoformat(at)).total_seconds() <= MAX_AGE)
    q['current'] = bool(q.get('identityVerified') and q.get('bidFresh') and q.get('askFresh')
                        and decimal(q['ask']) >= decimal(q['bid']) and not q.get('ended'))
    if q.get('ended'):
        q['code'] = 'ENDED'
    elif q.get('identityVerified'):
        q['code'] = 'CURRENT' if q['current'] else 'ONE_SIDED' if q['bidFresh'] or q['askFresh'] else 'STALE_OR_UNDATED'
    q['tradeApproved'] = False
    q['isDegiroQuote'] = False
    return q


def parse_bnp(data, isin, currency, now=None):
    now = now or datetime.now(timezone.utc)
    r = data['result']
    config = r['config']
    if (r.get('isin') != isin or r.get('currency', {}).get('isoCode') != currency
            or not str(r.get('issuerCompanyName', '')).startswith('BNP Paribas')):
        raise ValueError('Issuer identity mismatch')
    if any(type(config.get(k)) is not bool for k in ('isKnockedOut', 'isMaturedOrKnockOut', 'isCanceled', 'isLifeCycleEnded')):
        raise ValueError('Issuer status unknown')
    bid, ask = decimal(r.get('bid')), decimal(r.get('ask'))
    q = dict(isin=isin, currency=currency, identityVerified=True, kind='issuer-bid-ask',
             source='BNP Paribas · Depotbeobachtung', sourceUrl=BNP+'product-details/'+isin+'/',
             observedAt=now.isoformat(), bid=str(bid) if bid is not None and bid>0 else None,
             ask=str(ask) if ask is not None and ask>0 else None,
             bidAt=stamp(r.get('bidDate'), True), askAt=stamp(r.get('askDate'), True),
             ended=any(config[k] for k in ('isKnockedOut','isMaturedOrKnockOut','isCanceled','isLifeCycleEnded')))
    return freshness(q, now)


def parse_sg(product, points, isin, currency, now=None):
    now = now or datetime.now(timezone.utc)
    if (product.get('Isin') != isin or type(product.get('Id')) is not int or product['Id']<=0
            or product.get('Currency') != currency or product.get('ExchangeCode') != 'CBDE'
            or type(product.get('Status')) is not int):
        raise ValueError('Issuer identity mismatch')
    status = product['Status']
    q = dict(isin=isin, currency=currency, identityVerified=True, kind='issuer-chart',
             source='Société Générale · datierter Chartpunkt', sourceUrl=SG+'product-details/'+isin.lower(),
             observedAt=now.isoformat(), bid=None, ask=None, bidAt=None, askAt=None,
             ended=bool(status & (2|8|16|32)) or not status & 1 or
                   (product.get('ProductClassificationId') != 44100 and bool(product.get('TodayBarrierHitDate'))))
    if not isinstance(points, list) or len(points)>10000:
        raise ValueError('Invalid chart data')
    previous = None
    for point in points:
        at = stamp(point.get('Date'))
        bid, ask = decimal(point.get('Bid')), decimal(point.get('Ask'))
        if not at or bid is None or ask is None or bid<=0 or ask<bid or (previous and at<previous):
            raise ValueError('Invalid chart point')
        previous = at
    if points:
        # This is the point's original shared timestamp, not a request clock.
        q.update(bid=str(bid), ask=str(ask), bidAt=at, askAt=at)
    return freshness(q, now)


def parse_comdirect(html, isin, currency, issuer, now=None):
    """Separate holdings reader: never loosen the gold KO product parser."""
    from public_product_terms import plain
    now = now or datetime.now(timezone.utc)
    text = plain(html)
    section = text.split('Stammdaten ',1)[-1].split('Kennzahlen ',1)[0]
    if (currency!='EUR' or not re.search(r'WKN:\s*'+re.escape(isin[5:11])+r'\s+ISIN:\s*'+re.escape(isin)+r'\b',text)
            or not re.search(r'ISIN\s+'+re.escape(isin)+r'\s+WKN\s+'+re.escape(isin[5:11])+r'\b',section)
            or not re.search(r'Emittent\s+'+re.escape(issuer)+r'\s+Währung\s+EUR\b',section)):
        raise ValueError('Secondary identity mismatch')
    venue = {'Société Générale':'LT Societe Generale','BNP Paribas':'LT BNP Paribas'}[issuer]
    found = []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',html,re.S|re.I):
        cells = {}
        for label,value in re.findall(r'<t[dh]\b[^>]*data-label="([^"]+)"[^>]*>(.*?)</t[dh]>',row,re.S|re.I):
            if label in cells:
                raise ValueError('Ambiguous quote row')
            cells[label]=plain(value)
        if cells.get('LiveTrading')!=venue:
            continue
        prices=[]
        for side in ('Geld','Brief'):
            raw=cells.get(side,'')
            if not re.fullmatch(r'Realtime Kurs (?:\d+|\d{1,3}(?:\.\d{3})+),\d{1,6}',raw):
                raise ValueError('Missing quote side')
            prices.append(Decimal(raw.removeprefix('Realtime Kurs ').replace('.','').replace(',','.')))
        at=datetime.strptime(cells['Datum']+' '+cells['Zeit'],'%d.%m.%y %H:%M')
        zone=ZoneInfo('Europe/Berlin')
        if at.replace(tzinfo=zone,fold=0).utcoffset()!=at.replace(tzinfo=zone,fold=1).utcoffset() or not 0<prices[0]<=prices[1]:
            raise ValueError('Ambiguous time or quote')
        found.append(dict(isin=isin,currency=currency,identityVerified=True,kind='secondary-issuer-row',
            source='comdirect · '+venue,sourceUrl=COMDIRECT+'inf/zertifikate/'+isin,
            observedAt=now.isoformat(),bid=str(prices[0]),ask=str(prices[1]),
            bidAt=at.replace(tzinfo=zone).isoformat(),askAt=at.replace(tzinfo=zone).isoformat(),ended=False))
    if len(found)!=1:
        raise ValueError('Missing or ambiguous issuer row')
    return freshness(found[0],now)


def secondary(position, primary):
    if primary.get('current') or primary.get('ended') or position.get('currency')!='EUR':
        return primary
    from public_product_terms import open_public_page
    name=(position.get('name') or '').upper()
    issuer='BNP Paribas' if name.startswith('BNP ') else 'Société Générale' if name.startswith(('SG ','SOCIÉTÉ GÉNÉRALE','SOCIETE GENERALE')) else None
    if not issuer:
        return primary
    try:
        request=Request(COMDIRECT+'inf/zertifikate/'+position['isin'],headers={'User-Agent':'Bob public holdings observation','Accept':'text/html'})
        with open_public_page(request,timeout=5) as response:
            if not response.url.startswith(COMDIRECT):
                raise ValueError('Unexpected secondary redirect')
            body=response.read(2000001)
        if len(body)>2000000:
            raise ValueError('Oversized secondary response')
        value=parse_comdirect(body.decode('utf-8'),position['isin'],position['currency'],issuer)
        if value['current']:
            return value
    except Exception:
        pass
    return primary


def get_observation(position, get=read_json):
    isin, currency = position.get('isin'), position.get('currency')
    q = dict(isin=isin, currency=currency, code='UNSUPPORTED', identityVerified=False,
             current=False, observedAt=datetime.now(timezone.utc).isoformat())
    if not valid_isin(isin) or not re.fullmatch('[A-Z]{3}', currency or ''):
        return q
    name = (position.get('name') or '').upper()
    try:
        # Names select a reader only. The issuer response must prove the ISIN.
        if name.startswith('BNP '):
            data = get(BNP+'apiv2/api/v1/product/header/'+isin+'?_='+str(int(time.time()//30)*30000),
                       {'clientid':'0', 'languageid':'de'})
            return secondary(position,parse_bnp(data, isin, currency))
        if name.startswith(('SG ', 'SOCIÉTÉ GÉNÉRALE', 'SOCIETE GENERALE')) and currency=='EUR':
            with _LOCK:
                cached = _IDENTITIES.get((isin,currency))
            cache_valid = cached and time.monotonic()-cached[0]<300
            product = cached[1] if cache_valid else get(SG+'EmcWebApi/api/Products/'+isin)
            # Validate before constructing the quote URL from the issuer's ID.
            parse_sg(product, [], isin, currency)
            if not cache_valid:
                with _LOCK:
                    if len(_IDENTITIES)>=256:
                        _IDENTITIES.pop(next(iter(_IDENTITIES)))
                    _IDENTITIES[(isin,currency)] = (time.monotonic(), product)
            points = get(SG+'EmcWebApi/api/Prices/Live?productId='+str(product['Id']))
            return secondary(position,parse_sg(product, points, isin, currency))
    except Exception:
        q['code'] = 'SOURCE_UNAVAILABLE'
    return secondary(position,q)
