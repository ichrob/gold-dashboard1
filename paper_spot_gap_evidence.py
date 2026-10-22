"""Read-only original Gold-API spot archive coverage near recorded paper data gaps.

A saved spot before/after an event is NOT a complete 1m/5m price path,
KO certification, or a reproducible executable product quote.
"""
import math
import time

STREAM = 'gold-api-xau-usd-v1'
WINDOW_MS = 5 * 60 * 1000
RETENTION_MS = 7 * 24 * 60 * 60 * 1000
MAX_INSTANTS = 10
MAX_ACCOUNTS = 10
MAX_CASES = 5


def _valid(at):
    return type(at) in (int, float) and math.isfinite(at) and at > 0


def _nearest(conn, at, before):
    low, high = (at-WINDOW_MS, at) if before else (at, at+WINDOW_MS)
    order = 'DESC' if before else 'ASC'
    # Both bounds use the code-owned stream and primary-key index. Never writes.
    row = conn.execute(
        "SELECT extract(epoch from quote_at)*1000 FROM bob_spot_observations "
        "WHERE stream=%s AND quote_at BETWEEN to_timestamp(%s/1000.0) "
        "AND to_timestamp(%s/1000.0) ORDER BY quote_at " + order + " LIMIT 1",
        (STREAM, low, high)).fetchone()
    if not row or not _valid(row[0]):
        return None
    return round(float(row[0]), 3)


def snapshot(conn, accounts, now_ms=None):
    """Sample at most 10 distinct recorded error clocks from 5 recent cases/account.

    One clock shared across profiles is queried once. Missing archived points
    explicitly stay missing. Histories outside seven-day retention are unknown.
    """
    now_ms = time.time()*1000 if now_ms is None else now_ms
    if not _valid(now_ms) or not isinstance(accounts,list):
        return {'status':'unavailable','readOnly':True,
                'reason':'invalid-request-or-account-snapshot'}
    unique = {}
    sample_complete = True
    for account in accounts[:MAX_ACCOUNTS]:
        if not isinstance(account,dict):
            sample_complete = False
            continue
        recent = account.get('recentCases')
        if not isinstance(recent,dict) or recent.get('status')!='observed' or not isinstance(recent.get('items'),list):
            sample_complete = False
            continue
        for case in recent['items'][:MAX_CASES]:
            if not isinstance(case,dict) or case.get('status')!='inconclusive':
                continue
            for event in (case.get('events') or [])[-40:]:
                if not isinstance(event,dict) or event.get('kind')!='data-gap':
                    continue
                at=event.get('recordedAt')
                if _valid(at):
                    unique[at]=unique.get(at,0)+1
                else:
                    sample_complete=False
    instants = sorted(unique)[-MAX_INSTANTS:]
    probes=[]
    for at in instants:
        if at < now_ms-RETENTION_MS or at > now_ms+60000:
            probes.append({'recordedAt':at,'affectedVirtualCases':unique[at],
                           'state':'outside-archive-retention','originalBeforeAt':None,
                           'originalAfterAt':None})
            continue
        before = _nearest(conn, at, True)
        after = _nearest(conn, at, False)
        state = ('bracketed-original-observations' if before is not None and after is not None
                 else 'one-sided-original-observation' if before is not None or after is not None
                 else 'no-original-observation-within-five-minutes')
        probes.append({'recordedAt':at,'affectedVirtualCases':unique[at],
                       'state':state,'originalBeforeAt':before,'originalAfterAt':after})
    return {'status':'observed','readOnly':True,'realOrders':False,
            'source':STREAM,'archiveWindowSeconds':300,
            'sampledDistinctGapClocks':len(instants),
            'moreClocksOmitted':len(unique)>MAX_INSTANTS,
            'caseObservationsComplete':sample_complete,
            'instants':probes,
            'scope':'indexed-original-spot-presence-only-near-recorded-error-clock',
            'note':'Original timestamps but no prices. No full price path, '
                   'trade-fill, risk-order, or proof that missing market coverage was repaired.'}
