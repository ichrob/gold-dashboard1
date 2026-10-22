"""Passive seven-day Gold-API archive proximity check for paper gap events.

It asks whether an ORIGINAL spot timestamp was stored near an observed gap.
It cannot reconstruct the historical intragap path, quote product bids,
confirm an order or convert an inconclusive paper trade into a filled trade.
"""
import math
import time
from decimal import Decimal

STREAM = 'gold-api-xau-usd-v1'
WINDOW_MS = 90000
RETENTION_MS = 7 * 86400000
MAX_EVENTS = 12

_SQL = """SELECT (extract(epoch FROM quote_at)*1000)::double precision
FROM bob_spot_observations
WHERE stream=%s AND quote_at BETWEEN to_timestamp(%s)
    AND to_timestamp(%s)
ORDER BY ABS(extract(epoch FROM quote_at)*1000-%s)
LIMIT 1"""


def _times(accounts):
    """Exact recorded event clocks only, from bounded sanitized cases."""
    seen=set()
    for account in accounts[:10]:
        if not isinstance(account,dict):
            continue
        journal=account.get('recentCases')
        if not isinstance(journal,dict) or journal.get('status')!='observed':
            continue
        for case in (journal.get('items') or [])[:5]:
            if not isinstance(case,dict) or case.get('status')!='inconclusive':
                continue
            for event in (case.get('events') or [])[-40:]:
                if not isinstance(event,dict) or event.get('kind')!='data-gap':
                    continue
                at=event.get('recordedAt')
                if type(at) in (int,float) and math.isfinite(at) and at>0:
                    seen.add(at)
    return sorted(seen)


def report(conn, accounts, now_ms=None):
    now_ms=time.time()*1000 if now_ms is None else now_ms
    if not isinstance(now_ms,(int,float)) or not math.isfinite(now_ms):
        return {'status':'unavailable','reason':'invalid-observation-time','readOnly':True}
    if not isinstance(accounts,list):
        return {'status':'unavailable','reason':'account-samples-unavailable','readOnly':True}
    all_times=_times(accounts)
    times=all_times[-MAX_EVENTS:]
    if not times:
        return {'status':'unavailable','reason':'no-recorded-gap-clocks','readOnly':True}
    observations=[]
    counts={'nearbyOriginal':0,'notObservedNearEvent':0,
            'outsideRetention':0,'queryUnavailable':0}
    for at in times:
        item={'eventAt':at,'state':None,'nearestSourceAt':None,
              'deltaSeconds':None,'timeRelation':None}
        if at < now_ms-RETENTION_MS or at > now_ms:
            item['state']='outside-retention-or-future'
            counts['outsideRetention']+=1
        else:
            try:
                # A savepoint isolates temporary read failures, without writing.
                with conn.transaction():
                    row=conn.execute(_SQL,(STREAM,(at-WINDOW_MS)/1000,
                        (at+WINDOW_MS)/1000,at)).fetchone()
                if (row and type(row[0]) in (int,float,Decimal) and
                        math.isfinite(float(row[0]))):
                    source_ms=float(row[0])
                    item.update(state='nearby-original-observed',
                        nearestSourceAt=source_ms,
                        deltaSeconds=round(abs(source_ms-at)/1000,3),
                        timeRelation='before-or-at-event' if source_ms<=at else 'after-event')
                    counts['nearbyOriginal']+=1
                else:
                    item['state']='no-original-observed-in-90s-window'
                    counts['notObservedNearEvent']+=1
            except Exception:
                item['state']='archive-query-unavailable'
                counts['queryUnavailable']+=1
        observations.append(item)
    return {
        'status':'partial' if counts['queryUnavailable'] or len(times)<len(all_times)
                        else 'observed',
        'readOnly':True,'realOrders':False,
        'source':'Gold-API-original-spot-archive',
        'windowSeconds':90,'sampledDistinctClocks':len(times),
        'totalDistinctClocks':len(all_times),
        'truncated':len(times)<len(all_times),
        'counts':counts,'items':observations,
        'note':'Proximity to a *recorded gap event*, not to the complete missing price interval. '
               'Absence in this single seven-day Gold-API archive does not prove that other '
               'market feeds had no data. A later timestamp is not an earlier fill.'
    }
