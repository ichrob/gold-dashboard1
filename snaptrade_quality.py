"""Cached diagnostics for the SnapTrade reader."""

QUALITY_VERSION = 1

def evidence_gaps(account):
    """Count blocked provider observations, without raw holdings."""
    journal = account.get('journal') or {}
    orders = (journal.get('orders') or {}).get('rows') or []
    activities = (journal.get('activities') or {}).get('rows') or []
    proved = {item.get('key'):item for item in (account.get('tradeInsights') or {}).get('executions', [])}
    counts = dict(orderRows=len(orders), positiveFills=0,
                  noPositiveFill=0, filledQuantityMissing=0,
                  filledQuantityZero=0, filledQuantityInvalid=0,
                  missingExecutionTime=0, missingVerifiedIsin=0,
                  missingPrice=0, activityTrades=0, activityMissingFees=0)
    for row in orders:
        if not isinstance(row, dict): continue
        raw = row.get('quantity')
        qty = None
        if raw is not None and raw != '' and not isinstance(raw, bool):
            try:
                from decimal import Decimal, InvalidOperation
                qty = Decimal(str(raw))
            except (ValueError, TypeError, InvalidOperation):
                pass
        if qty is None:
            counts['noPositiveFill'] += 1
            counts['filledQuantityMissing' if raw is None or raw == '' else 'filledQuantityInvalid'] += 1
            continue
        if not qty.is_finite() or not 0 < qty < Decimal('1e30'):
            counts['noPositiveFill'] += 1
            counts['filledQuantityZero' if qty.is_finite() and qty == 0 else 'filledQuantityInvalid'] += 1
            continue
        counts['positiveFills'] += 1
        if not row.get('executedAt'): counts['missingExecutionTime'] += 1
        if not proved.get(row.get('key'), {}).get('isin'): counts['missingVerifiedIsin'] += 1
        if not row.get('price'): counts['missingPrice'] += 1
    for row in activities:
        if isinstance(row,dict) and row.get('type') in ('BUY','SELL'):
            counts['activityTrades'] += 1
            if row.get('fee') is None: counts['activityMissingFees'] += 1
    return counts

def connection_watch(status):
    """Deduplicated cached observations. No push, mail or provider reads."""
    issues = []
    if not status.get('configured'): issues.append('NOT_CONFIGURED')
    elif not status.get('running'): issues.append('READER_STOPPED')
    if status.get('configured') and status.get('code') not in ('READY','CHECKING','READ_OK'):
        issues.append('PROVIDER_READ_NOT_CONFIRMED')
    if status.get('code') == 'READ_OK' and not status.get('fresh'):
        issues.append('SOURCE_CLOCK_NOT_FRESH')
    for account in (status.get('snapshot') or {}).get('accounts',[]):
        journal = account.get('journal') or {}
        if journal.get('orders',{}).get('code') != 'READ_OK':
            issues.append('ORDER_JOURNAL_NOT_CONFIRMED')
        if journal.get('activities',{}).get('code') != 'READ_OK':
            issues.append('ACTIVITY_JOURNAL_NOT_CONFIRMED')
        elif journal['activities'].get('complete') is not True:
            issues.append('ACTIVITY_HISTORY_PARTIAL')
    return dict(codes=list(dict.fromkeys(issues)),readOnly=True,
                pushesSent=0, emailsSent=0,
                note='Quelle und Originalzeit getrennt prüfen; alte Daten sind kein Verbindungsabbruch.')

def profit_review(account):
    """Readiness only: no financial returns calculated from partial histories."""
    journal = account.get('journal') or {}
    activity = journal.get('activities') or {}
    trades = account.get('tradeJournal') or {}
    insight = account.get('tradeInsights') or {}
    match = insight.get('reconciliation') or {}
    return dict(
        accountHistoryComplete=activity.get('complete') is True,
        activityReadable=activity.get('code') == 'READ_OK',
        tradeRows=len(trades.get('events') or []),
        fifoVerifiedSales=len(trades.get('realized') or []),
        unresolvedLots=len(trades.get('unresolved') or []),
        strictReviewPairs=match.get('candidatePairs') or 0,
        unmatchedOrUnverifiedEvidence=(
            (match.get('missingEvidence') or 0) +
            (match.get('orderFillsWithoutExactActivity') or 0)),
        netProfitVerified=False, taxProfitVerified=False,
        canChangeTradeRules=False, readOnly=True,
    )
