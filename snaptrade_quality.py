"""Cached diagnostics for the SnapTrade reader."""

QUALITY_VERSION = 1

def evidence_gaps(account):
    return {'orderRows':len((account.get('journal') or {}).get('orders',{}).get('rows') or [])}
