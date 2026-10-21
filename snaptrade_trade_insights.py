"""Read-only SnapTrade execution observations for Bob's DEGIRO panel.

An order with a non-zero *filled* quantity is evidence of an execution reported
by the intermediary, not a live order permission, realized P/L, or evidence of
DEGIRO product tradability. No market signal is generated here.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re


def decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and abs(result.adjusted()) < 30 else None
    except (ValueError, InvalidOperation):
        return None


def execution_time(raw):
    """Do not convert an undated order or a date-only activity to an instant."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    except (ValueError, OverflowError):
        return None
    return value.isoformat() if value.tzinfo is not None else None


def read_account(account, limit=100):
    journal = account.get('journal') or {}
    orders = journal.get('orders') or {}
    activities = journal.get('activities') or {}
    # A symbol can be reused across venues. A currency and exactly one verified
    # position mapping are mandatory; never match by product name or quantity.
    by_symbol = {}
    for p in account.get('positions') or []:
        isin = p.get('isin')
        if not p.get('csvEvidence') or not isinstance(isin, str):
            continue
        symbol, currency = p.get('symbol'), p.get('currency')
        if symbol and re.fullmatch(r'[A-Z]{3}', currency or ''):
            by_symbol.setdefault((symbol, currency), set()).add(isin)

    fills = []
    seen = set()
    for row in (orders.get('rows') or [])[:1000]:
        if not isinstance(row, dict):
            continue
        qty = decimal(row.get('quantity'))
        # 'filled_quantity' is normalized by snaptrade_portfolio, distinct from
        # order's requested quantity. Canceled/partially filled orders may have
        # valid executions when filled_quantity is positive.
        if qty is None or qty <= 0 or not row.get('key') or row['key'] in seen:
            continue
        seen.add(row['key'])
        currency, symbol = row.get('currency'), row.get('symbol')
        found = by_symbol.get((symbol, currency), set())
        isin = next(iter(found)) if len(found) == 1 else None
        at = execution_time(row.get('date'))
        fills.append({
            'key': row['key'], 'symbol': symbol or '', 'name': row.get('name') or '',
            'isin': isin, 'currency': currency or '', 'side': row.get('type') or '',
            'filledQuantity': str(qty), 'executionPrice': str(decimal(row.get('price'))) if decimal(row.get('price')) is not None else None,
            'executedAt': at, 'reportedTime': row.get('date') or '',
            'providerStatus': row.get('status') or '',
            'evidence': 'snaptrade-order-filled-quantity',
            'matching': 'verified-held-position' if isin else 'identifier-unresolved',
            'reviewReady': bool(isin and at and decimal(row.get('price')) is not None),
            'realizedProfit': None, 'productApproval': False, 'automaticTrade': False,
        })
        if len(fills) == limit:
            break

    by_currency = {}
    if activities.get('code') == 'READ_OK':
        for row in (activities.get('rows') or []):
            if not isinstance(row, dict):
                continue
            fee = decimal(row.get('fee'))
            currency = row.get('currency')
            if fee is None or not re.fullmatch(r'[A-Z]{3}', currency or ''):
                continue
            entry = by_currency.setdefault(currency, {'currency': currency, 'reportedFeeSum': Decimal(0), 'entries': 0})
            entry['reportedFeeSum'] += fee
            entry['entries'] += 1
    fees = [{'currency': v['currency'], 'reportedFeeSum': str(v['reportedFeeSum']), 'entries': v['entries']}
            for v in sorted(by_currency.values(), key=lambda x: x['currency'])]
    return {
        'executions': fills, 'executionsCount': len(fills),
        'readyForHistoricalComparison': sum(x['reviewReady'] for x in fills),
        'feesByCurrency': fees, 'activitiesComplete': bool(activities.get('complete') and activities.get('code') == 'READ_OK'),
        'ordersAvailable': orders.get('code') == 'READ_OK',
        'ordersCheckedAt': orders.get('checkedAt'),
        'activitiesCheckedAt': activities.get('checkedAt'),
        'note': 'Ausgeführte Mengen laut SnapTrade; nicht zwingend zeitnah. Keine automatische MyTrade-Erfassung oder Lernregeländerung. Gebührensummen sind Anbieterfelder ohne Vorzeichenkorrektur, keine vollständige Kosten-/Gewinnrechnung.'
    }
