"""Rebuild a read-only FIFO journal from broker activities, never from holdings.

Derived amounts are accounting calculations, not tax statements or strategy
training inputs. Rebuilding from the current activity set avoids double imports
when the provider corrects or reissues transaction IDs.
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

SCHEMA = 4
NON_INVENTORY = {'DIVIDEND', 'SUBSTITUTE_DIVIDEND', 'INTEREST', 'FEE', 'TAX',
                 'CONTRIBUTION', 'WITHDRAWAL'}
UNIT_KINDS = {'cs', 'et', 'etf', 'stock', 'adr', 'cef', 'mutualfund', 'crypto'}
CONTRACT_KINDS = {'op', 'option', 'future', 'future_option', 'cfd', 'bond', 'bnd'}


def decimal(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and abs(result) < Decimal('1e30') else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def transaction_time(value):
    try:
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if at.tzinfo is None:
            # Date-only brokerage records retain day precision, not a fake time.
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                return None
            at = at.replace(tzinfo=timezone.utc)
        return at
    except (ValueError, TypeError, AttributeError):
        return None


def trade_value(row):
    """Recognized unit prices, or an explicit cash/units/price cross-check.

Never guess option, futures or bond multipliers. FX price and fee must share
their documented transaction currency. Null fees remain unknown, not zero.
"""
    units, price, amount, fee = (decimal(row.get(k)) for k in ('quantity', 'price', 'amount', 'fee'))
    # Activities represent an asset outflow with negative SELL units. Keep the
    # original signed quantity in the source journal; FIFO uses its magnitude.
    if row.get('type') == 'SELL' and units is not None:
        units = abs(units)
    kind = row.get('securityKind', '').lower()
    if row.get('optionType') or kind in CONTRACT_KINDS:
        return None
    if units is None or units <= 0 or price is None or price <= 0:
        return None
    if not re.fullmatch('[A-Z]{3}', row.get('currency') or ''):
        return None
    if fee is not None and fee < 0:
        return None
    gross = units * price
    sign = -1 if row['type'] == 'BUY' else 1
    cash_ok = amount is not None and (abs(amount - sign*gross) <= Decimal('.005')
                or fee is not None and abs(amount - (sign*gross-fee)) <= Decimal('.005'))
    if amount is not None and not cash_ok:
        return None
    # A known stock kind alone is insufficient for cross-currency quotes.
    currencies_match = row.get('securityCurrency') == row.get('currency') and not row.get('fxRate')
    if not cash_ok and not (kind in UNIT_KINDS and currencies_match):
        return None
    return units, gross, fee


def build(journal):
    activities = journal.get('activities') or {}
    rows = activities.get('rows') or []
    result = dict(schemaVersion=SCHEMA, sourceAt=activities.get('checkedAt'),
                  sourceAvailable=activities.get('code') == 'READ_OK',
                  historyComplete=activities.get('complete') is True,
                  events=[], realized=[], unresolved=[], totals=[],
                  separateCharges=[], cashMovements=[], learningEligible=False)
    groups = defaultdict(list)
    inventory_changes, unknown_inventory = set(), False
    for row in rows:
        kind = row.get('type', '').upper()
        if kind in ('FEE', 'TAX'):
            result['separateCharges'].append(row)
        if kind in ('CONTRIBUTION', 'WITHDRAWAL'):
            result['cashMovements'].append(row)
        security = ('isin:'+row['isin']) if row.get('isin') else row.get('securityKey')
        if kind not in NON_INVENTORY | {'BUY','SELL'}:
            if security:
                inventory_changes.add(security)
            else:
                unknown_inventory = True
        if kind in ('BUY', 'SELL'):
            result['events'].append(row)
            if not security:
                result['unresolved'].append(dict(key=row['key'], name=row['name'], reason='Wertpapierkennung fehlt.'))
        if security:
            groups[(security, row.get('currency'))].append(row)
    for (security, currency), group in groups.items():
        trades = [r for r in group if r.get('type') in ('BUY', 'SELL')]
        if not trades:
            continue
        reason = None
        if not result['historyComplete']:
            reason = 'Anbieterhistorie unvollständig; keine FIFO-Ergebnisrechnung.'
        elif unknown_inventory or security in inventory_changes:
            reason = 'Übertrag, Kapitalmaßnahme oder unbekannte Bestandsänderung vorhanden.'
        values = {r['key']: trade_value(r) for r in trades}
        times = {r['key']: transaction_time(r.get('date')) for r in trades}
        if not reason and (any(v is None for v in values.values()) or any(t is None for t in times.values())):
            reason = 'Stücknotierung, Währung, Kurs, Menge oder Transaktionsdatum nicht ausreichend belegt.'
        # Day-only dates and midnight timestamps cannot establish same-day order.
        by_day = defaultdict(list)
        for r in trades:
            t = times[r['key']]
            if t:
                by_day[t.date()].append(t)
        if not reason and any(len(ts)>1 and (len(set(ts))<len(ts) or any(t.time().isoformat().startswith('00:00:00') for t in ts)) for ts in by_day.values()):
            reason = 'Reihenfolge mehrerer Transaktionen am selben Tag nicht eindeutig.'
        lots, closed = deque(), []
        # Fees with a separate broker reference may duplicate inline fees. Keep
        # them visible but never silently double-count or claim all-in profit.
        extra_fees = {r.get('externalReference') for r in rows if r.get('type') in ('FEE', 'TAX') and r.get('externalReference')}
        if not reason:
            for row in sorted(trades, key=lambda r: times[r['key']]):
                units, gross, fee = values[row['key']]
                if row.get('externalReference') in extra_fees:
                    fee = None
                if row['type'] == 'BUY':
                    lots.append(dict(units=units, gross=gross, fee=fee, row=row))
                    continue
                if sum((l['units'] for l in lots), Decimal(0)) < units:
                    reason = 'Verkauf ohne vollständig belegte vorherige Käufe; keine Short- oder Einstandsannahme.'
                    break
                remaining, cost, buy_fee = units, Decimal(0), Decimal(0)
                buy_keys = []
                while remaining:
                    lot = lots[0]
                    take = min(remaining, lot['units'])
                    share = take / lot['units']
                    part = lot['gross']*share
                    part_fee = lot['fee']*share if lot['fee'] is not None else None
                    cost += part
                    buy_fee = buy_fee+part_fee if buy_fee is not None and part_fee is not None else None
                    buy_keys.append(lot['row']['key'])
                    lot['gross'] -= part
                    if lot['fee'] is not None:
                        lot['fee'] -= part_fee
                    lot['units'] -= take
                    remaining -= take
                    if not lot['units']:
                        lots.popleft()
                fees = buy_fee+fee if buy_fee is not None and fee is not None else None
                closed.append(dict(key=row['key'], name=row['name'], isin=row.get('isin'), date=row['date'],
                    currency=currency, quantity=str(units), buyKeys=buy_keys, cost=str(cost), proceeds=str(gross),
                    grossPnl=str(gross-cost), fees=str(fees) if fees is not None else None,
                    netPnl=str(gross-cost-fees) if fees is not None else None,
                    openQuantityAfter=str(sum((l['units'] for l in lots), Decimal(0)))))
        if reason:
            result['unresolved'].append(dict(key=security, name=trades[0]['name'], reason=reason))
        else:
            result['realized'].extend(closed)
    totals = defaultdict(list)
    for row in result['realized']:
        totals[row['currency']].append(row)
    for currency, closed in totals.items():
        result['totals'].append(dict(currency=currency, sales=len(closed),
            grossPnl=str(sum((Decimal(r['grossPnl']) for r in closed), Decimal(0))),
            netPnl=str(sum((Decimal(r['netPnl']) for r in closed), Decimal(0))) if all(r['netPnl'] is not None for r in closed) else None))
    result['realized'].sort(key=lambda r: r['date'], reverse=True)
    return result
