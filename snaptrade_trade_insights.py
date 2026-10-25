"""Read-only SnapTrade execution observations for Bob's DEGIRO panel.

An order with a non-zero *filled* quantity is evidence of an execution reported
by the intermediary, not a live order permission, realized P/L, or evidence of
DEGIRO product tradability. No market signal is generated here.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re
import snaptrade_portfolio as portfolio


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


def match_provider_executions(fills, journal, limit=100):
    """Read-only evidence comparison, strictly one order to one activity.

    The two SnapTrade endpoints are views of the same broker, not independent
    exchange confirmations. Matching does not establish net profit, tax lots,
    or complete historical order coverage.
    """
    orders = journal.get('orders') or {}
    activities = journal.get('activities') or {}
    out = {
        'status':'available' if orders.get('code') == activities.get('code') == 'READ_OK' else 'unavailable',
        'pairs':[], 'candidatePairs':0, 'ambiguousGroups':0,
        'orderFillsWithoutExactActivity':0, 'activityTradesWithoutExactOrder':0,
        'missingEvidence':0, 'reportedMatchedFeesByCurrency':[],
        'accountHistoryComplete':activities.get('complete') is True,
        'netProfitVerified':False,'learningEligible':False, 'ordersEnabled':False,
        'note':'Nur eindeutige Übereinstimmungen im begrenzten Anbieterfenster; '
               'kein vollständiger Echtgeld-Trade oder berechneter Nettogewinn.'
    }
    if out['status'] != 'available':
        return out

    def order_signature(fill):
        if fill.get('side') not in ('BUY','SELL') or not portfolio.isin(fill.get('isin')):
            return None
        qty, price = decimal(fill.get('filledQuantity')), decimal(fill.get('executionPrice'))
        stamp = fill.get('executedAt')
        if qty is None or qty <= 0 or price is None or price <= 0 or not stamp:
            return None
        try:
            day = datetime.fromisoformat(stamp).date().isoformat()
        except (ValueError,TypeError):
            return None
        if not re.fullmatch(r'[A-Z]{3}', fill.get('currency') or ''):
            return None
        return (fill['isin'],fill['side'],fill['currency'],qty,price,day)

    def activity_signature(row):
        if row.get('type') not in ('BUY','SELL') or not portfolio.isin(row.get('isin')):
            return None
        if row.get('fxRate') or row.get('optionType'):
            return None
        currency=row.get('currency')
        if not re.fullmatch(r'[A-Z]{3}',currency or ''):
            return None
        if row.get('securityCurrency') and row['securityCurrency'] != currency:
            return None
        qty, price = decimal(row.get('quantity')), decimal(row.get('price'))
        if qty is None or not qty or price is None or price <= 0:
            return None
        if row['type'] == 'BUY' and qty < 0:
            return None
        day=row.get('date')
        if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):
            return None
        return (row['isin'],row['type'],currency,abs(qty),price,day)

    by_order, by_activity = defaultdict(list), defaultdict(list)
    for fill in fills:
        key=order_signature(fill)
        if key:
            by_order[key].append(fill)
        else:
            out['missingEvidence'] += 1
    for activity in (activities.get('rows') or []):
        if not isinstance(activity,dict) or activity.get('type') not in ('BUY','SELL'):
            continue
        key=activity_signature(activity)
        if key:
            by_activity[key].append(activity)
    fees=defaultdict(lambda:{'amount':Decimal(0),'entries':0,'missing':0})
    for signature, match_orders in by_order.items():
        match_activities=by_activity.get(signature, [])
        if len(match_orders) == 1 and len(match_activities) == 1:
            if len(out['pairs']) >= limit:
                out['missingEvidence'] += 1
                continue
            fill, activity=match_orders[0],match_activities[0]
            fee=decimal(activity.get('fee'))
            currency=signature[2]
            if fee is None:
                fees[currency]['missing'] += 1
            else:
                fees[currency]['amount'] += fee
                fees[currency]['entries'] += 1
            out['pairs'].append({
                'isin':signature[0], 'side':signature[1],
                'currency':currency, 'quantity':str(signature[3]),
                'price':str(signature[4]), 'executionDay':signature[5],
                'reportedActivityFee':str(fee) if fee is not None else None,
                'evidence':'order-activity-same-provider-consistent',
                'realizedProfit':None,'netProfit':None, 'productApproval':False
            })
        elif match_activities and (len(match_orders) > 1 or len(match_activities) > 1):
            out['ambiguousGroups'] += 1
        else:
            out['orderFillsWithoutExactActivity'] += len(match_orders)
    out['activityTradesWithoutExactOrder']=sum(len(values) for k,values in by_activity.items()
                                                   if k not in by_order)
    out['candidatePairs']=len(out['pairs'])
    out['reportedMatchedFeesByCurrency']=[{
        'currency':k, 'sumAsReported':str(v['amount']),
        'entries':v['entries'],'missingFeeEntries':v['missing'],
        'coverage':'matched-provider-activities-only-not-total-fees'}
        for k,v in sorted(fees.items())]
    return out


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
        # Only the provider's actual time_executed proves the execution
        # instant; a fallback placement time is not an execution timestamp.
        at = execution_time(row.get('executedAt'))
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
        'reconciliation': match_provider_executions(fills,journal),
        'note': 'Ausgeführte Mengen laut SnapTrade; nicht zwingend zeitnah. Keine automatische MyTrade-Erfassung oder Lernregeländerung. Gebührensummen sind Anbieterfelder ohne Vorzeichenkorrektur, keine vollständige Kosten-/Gewinnrechnung.'
    }
