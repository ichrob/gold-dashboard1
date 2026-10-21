"""Read-only portfolio arithmetic and bounded journal; never trading evidence."""
from decimal import Decimal
import hashlib
import re


def identity(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def isin(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', value):
        return None
    digits = ''.join(str(ord(c)-55) if c.isalpha() else c for c in value)
    total = sum((int(c)*2//10+int(c)*2%10) if i%2 else int(c) for i,c in enumerate(reversed(digits)))
    return value if total % 10 == 0 else None


def enrich_position(row, item, number, text):
    instrument = row['instrument']
    item['positionKey'] = identity(instrument.get('id') or (instrument.get('kind'), instrument.get('symbol'), instrument.get('raw_symbol')))
    item['costBasis'] = number(row.get('cost_basis'))
    item['cashEquivalent'] = row.get('cash_equivalent') is True
    item['exchange'] = text(instrument.get('exchange'), 32)
    figi = instrument.get('figi_instrument') or {}
    item['figi'] = text(figi.get('figi_code'), 32) if isinstance(figi, dict) else ''
    # Exact provider symbol only. Never extract identifiers from descriptions.
    item['isin'] = isin(instrument.get('raw_symbol')) or isin(instrument.get('symbol'))
    item['identityVerified'] = False
    item['marketValue'] = item['unrealizedPnl'] = item['unrealizedPercent'] = None
    # No guessed contract multipliers for options/futures/CFDs/bonds/unknown.
    unit_priced = item['kind'] in ('stock', 'adr', 'etf', 'cef', 'mutualfund', 'crypto', 'tokenized_asset')
    item['valuationNote'] = 'Berechnung je Stück' if unit_priced else 'Produktmultiplikator nicht bestätigt'
    if unit_priced and item['units'] is not None and item['valuationPrice'] is not None:
        units, price = Decimal(item['units']), Decimal(item['valuationPrice'])
        item['marketValue'] = str(units * price)
        if item['costBasis'] is not None:
            basis = Decimal(item['costBasis'])
            item['unrealizedPnl'] = str(units * (price-basis))
            if units and basis > 0:
                item['unrealizedPercent'] = str((price-basis)/basis*100*(1 if units > 0 else -1))
    return item


def journal_rows(data, category, number, text):
    result = []
    for row in data:
        symbol = row.get('universal_symbol' if category == 'orders' else 'symbol') or {}
        if not isinstance(symbol, dict): symbol = {}
        currency = row.get('currency') if category == 'activities' else symbol.get('currency')
        if isinstance(currency, dict): currency = currency.get('code')
        key = row.get('brokerage_order_id' if category == 'orders' else 'id')
        if not isinstance(key, str) or not key:
            raise ValueError('Missing journal identifier')
        item = dict(key=identity(key), name=text(symbol.get('description') or symbol.get('symbol') or row.get('description')),
                    symbol=text(symbol.get('symbol')), currency=text(currency, 3),
                    type=text(row.get('action' if category == 'orders' else 'type'), 40),
                    status=text(row.get('status'), 40),
                    date=text(row.get('time_executed') or row.get('time_placed') if category == 'orders' else row.get('trade_date'), 40),
                    quantity=number(row.get('filled_quantity' if category == 'orders' else 'units')),
                    price=number(row.get('execution_price' if category == 'orders' else 'price')),
                    amount=number(row.get('amount')), fee=number(row.get('fee')),
                    stop=number(row.get('stop_price')), limit=number(row.get('limit_price')),
                    orderType=text(row.get('order_type'), 40))
        result.append(item)
    return result


def record(history, snapshot):
    """Track source snapshots; value differences deliberately are not profits."""
    previous = history[-1] if history else None
    account_set = sorted(a['accountKey'] for a in snapshot['accounts'])
    point = {'at': snapshot['observedAt'], 'complete': snapshot['completeConnections'], 'accounts': []}
    for a in snapshot['accounts']:
        point['accounts'].append(dict(accountKey=a['accountKey'], netValue=a['netValue'],
            sourceAt=a['positionsSourceAt'], cash=a['cash'],
            positions=[{'key':p['positionKey'], 'units':p['units'], 'name':p['name']} for p in a['positions']]))
    changes = []
    if previous and previous['complete'] and point['complete'] and account_set == sorted(a['accountKey'] for a in previous['accounts']):
        for account in point['accounts']:
            old = next(a for a in previous['accounts'] if a['accountKey'] == account['accountKey'])
            if not account['sourceAt'] or not old['sourceAt'] or account['sourceAt'] <= old['sourceAt']: continue
            old_map = {p['key']:p for p in old['positions']}
            new_map = {p['key']:p for p in account['positions']}
            # A quantity change is an observation, not proof of a buy/sell.
            for key in sorted(old_map.keys() | new_map.keys()):
                before, after = old_map.get(key), new_map.get(key)
                if (before or {}).get('units') != (after or {}).get('units'):
                    changes.append({'at':point['at'], 'name':(after or before)['name'],
                                    'before':before['units'] if before else None, 'after':after['units'] if after else None})
    # One point per provider snapshot, not per UI status request.
    if not previous or point['accounts'] != previous['accounts'] or point['complete'] != previous['complete']:
        history.append(point)
    del history[:-1008]
    return changes
