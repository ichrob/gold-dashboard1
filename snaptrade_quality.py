"""Cached diagnostics for the SnapTrade reader."""

QUALITY_VERSION = 1

def evidence_gaps(account):
    """Count blocked provider observations, without raw holdings."""
    journal = account.get('journal') or {}
    orders = (journal.get('orders') or {}).get('rows') or []
    activities = (journal.get('activities') or {}).get('rows') or []
    counts = dict(orderRows=len(orders), positiveFills=0,
                  noPositiveFill=0, missingExecutionTime=0,
                  missingVerifiedIsin=0, missingPrice=0,
                  activityTrades=0, activityMissingFees=0)
    for row in orders:
        if not isinstance(row, dict): continue
        try: qty = float(row.get('quantity') or 0)
        except (TypeError, ValueError): qty = 0
        if not 0 < qty < 1e30:
            counts['noPositiveFill'] += 1
            continue
        counts['positiveFills'] += 1
        if not row.get('executedAt'): counts['missingExecutionTime'] += 1
        if not row.get('isin'): counts['missingVerifiedIsin'] += 1
        if not row.get('price'): counts['missingPrice'] += 1
    for row in activities:
        if isinstance(row,dict) and row.get('type') in ('BUY','SELL'):
            counts['activityTrades'] += 1
            if row.get('fee') is None: counts['activityMissingFees'] += 1
    return counts
