"""Normalize broker holdings without inventing quote clocks or trading approval."""
from datetime import datetime, timezone
import math
import re


def finite(value):
    return value if type(value) in (float, int) and math.isfinite(value) else None


def read_snapshot(api, portfolio):
    rows = portfolio.get('portfolio', {}).get('value') if isinstance(portfolio, dict) else None
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid portfolio')
    holdings = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('value'), list):
            raise ValueError('Invalid portfolio row')
        fields = {}
        for item in row['value']:
            if not isinstance(item, dict) or not isinstance(item.get('name'), str) or item['name'] in fields:
                raise ValueError('Invalid portfolio field')
            fields[item['name']] = item.get('value')
        if fields.get('positionType') != 'PRODUCT':
            if fields.get('positionType') == 'CASH':
                continue
            raise ValueError('Unknown position type')
        size = finite(fields.get('size'))
        product_id = str(row.get('id', ''))
        if size is None or not re.fullmatch(r'[1-9][0-9]{0,15}', product_id):
            raise ValueError('Invalid holding')
        if size == 0:
            continue
        holdings.append({'productId': product_id, 'quantity': size,
                         'valuationPrice': finite(fields.get('price')),
                         'valuationAmount': finite(fields.get('value'))})
    ids = list(dict.fromkeys(h['productId'] for h in holdings))
    if len(ids) != len(holdings):
        raise ValueError('Duplicate product position')
    info = {}
    for offset in range(0, len(ids), 100):
        response = api.get_products_info(product_list=[int(i) for i in ids[offset:offset+100]], raw=True)
        if not isinstance(response, dict) or not isinstance(response.get('data'), dict):
            raise ValueError('Missing product identity')
        info.update(response['data'])
    for row in holdings:
        item = info.get(row['productId'])
        if not isinstance(item, dict) or str(item.get('id')) != row['productId']:
            raise ValueError('Product identity mismatch')
        isin = item.get('isin')
        # Unknown identity stays visible as a broker product ID, never guessed.
        if not isinstance(isin, str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', isin):
            isin = None
        row.update(isin=isin, name=str(item.get('name') or '')[:160],
                   currency=str(item.get('currency') or '')[:3],
                   source='DEGIRO depot', sourceAt=None,
                   priceKind='portfolio-valuation', tradeApproved=False)
    return {'observedAt': datetime.now(timezone.utc).isoformat(), 'holdings': holdings,
            'source': 'DEGIRO', 'complete': True, 'liveQuotes': False, 'ordersEnabled': False}
