"""Experimental broker evidence collection; never grants trading approval."""
import re
from datetime import datetime, timezone

FIELDS = ('id', 'isin', 'name', 'currency', 'exchangeId', 'vwdId', 'vwdIdentifierType',
          'bid', 'ask', 'bidPrice', 'askPrice', 'bidTime', 'askTime', 'lastTime',
          'lastPrice', 'quality', 'tradable', 'isTradable', 'tradingStatus')


def validate_isins(values):
    if not isinstance(values, list) or len(values) > 3:
        raise ValueError('Provide at most three ISINs')
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', v) for v in values):
        raise ValueError('Invalid ISIN')
    return list(dict.fromkeys(values))


def evidence(raw):
    # Preserve named source fields without interpreting undocumented semantics.
    return {k: v for k, v in raw.items() if k in FIELDS and
            (type(v) in (bool, int, float) or isinstance(v, str) and len(v) <= 256)}


def collect(api, session, isins, user_token=None):
    from degiro_connector.trading.models.product_search import LookupRequest
    reports = []
    for isin in validate_isins(isins):
        raw = api.product_search(product_request=LookupRequest(search_text=isin, limit=10), raw=True)
        matches = [p for p in (raw or {}).get('products', []) if p.get('isin') == isin]
        items = []
        for product in matches[:3]:
            item = {'product': evidence(product), 'quote': {}, 'source': 'DEGIRO product search'}
            pid = str(product.get('id', ''))
            if pid.isdigit():
                info = api.get_products_info(product_list=[int(pid)], raw=True)
                detail = (info or {}).get('data', {}).get(pid, {})
                if detail.get('isin') == isin:
                    item['product'].update(evidence(detail))
                    ident, kind = detail.get('vwdId'), detail.get('vwdIdentifierType')
                    if user_token and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', str(ident or '')) and kind in ('issueid', 'vwdkey'):
                        series = f'{kind}:{ident}'
                        response = session.get('https://charting.vwdservices.com/hchart/v1/deGiro/data.js',
                            params={'series': series, 'userToken': user_token, 'format': 'json', 'period': 'P1D',
                                    'resolution': 'PT1M', 'tz': 'Europe/Amsterdam'})
                        response.raise_for_status()
                        for row in response.json().get('series', []):
                            if row.get('id') == series and isinstance(row.get('data'), dict):
                                item['quote'] = evidence(row['data'])
            item['approval'] = 'UNVERIFIED'
            item['note'] = 'Raw fields only; chart prices and listing do not establish executable broker quotes or account eligibility.'
            items.append(item)
        reports.append({'isin': isin, 'matches': items, 'status': 'OBSERVED' if items else 'NOT_FOUND'})
    return {'products': reports, 'observedAt': datetime.now(timezone.utc).isoformat(),
            'liveOrdersEnabled': False, 'approval': 'UNVERIFIED'}
