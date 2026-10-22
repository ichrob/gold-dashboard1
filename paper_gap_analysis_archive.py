"""Passive read-only correlation with 7-day, timestamped analysis observations.

Presence of another analyzer near a paper data gap does not establish that the
paper worker had that bundle, a valid issuer bid or a completed trade. No SQL
writes, market fetches, signal computation, or trade-state mutation.
"""
import math
import time
from decimal import Decimal
from paper_gap_archive import _times, WINDOW_MS, RETENTION_MS, MAX_EVENTS

# Fixed, indexed, allowlisted stage and timeframe. Read the status only.
_SQL = """SELECT observed_at, payload->'result'->>'ready',
    payload->'result'->>'priceFresh', payload->'result'->>'dataAt'
FROM bob_diagnostic_history
WHERE stage='analysis'
AND payload->>'timeframe'='15m'
AND observed_at BETWEEN %s AND %s
ORDER BY ABS(observed_at-%s)
LIMIT 1"""


def _yes_no(value):
    return True if value is True or value == 'true' else (
        False if value is False or value == 'false' else None)


def _source_age(value, observed_at):
    try:
        source_at=float(value)
        if not math.isfinite(source_at) or source_at<=0:
            return None
        age=observed_at*1000-source_at
        return round(age/1000,3) if math.isfinite(age) else None
    except (TypeError, ValueError, OverflowError):
        return None


def report(conn, accounts, now_ms=None):
    now_ms=time.time()*1000 if now_ms is None else now_ms
    if type(now_ms) not in (int,float) or not math.isfinite(now_ms):
        return {'status':'unavailable','reason':'invalid-observation-time','readOnly':True}
    if not isinstance(accounts,list):
        return {'status':'unavailable','reason':'account-samples-unavailable','readOnly':True}
    original=_times(accounts)
    times=original[-MAX_EVENTS:]
    if not times:
        return {'status':'unavailable','reason':'no-recorded-gap-clocks','readOnly':True}
    counts={'nearby15mAnalysis':0,'readyFresh15mAnalysis':0,
            'no15mAnalysisInWindow':0,'outsideRetention':0,
            'queryUnavailable':0}
    items=[]
    for at in times:
        item={'eventAt':at,'state':'unavailable','analysisAt':None,
              'timeRelation':None,'deltaSeconds':None,
              'ready':None,'priceFresh':None,
              'sourceAgeAtAnalysisSeconds':None}
        if at<now_ms-RETENTION_MS or at>now_ms:
            item['state']='outside-retention-or-future'
            counts['outsideRetention']+=1
        else:
            try:
                with conn.transaction():
                    row=conn.execute(_SQL,((at-WINDOW_MS)/1000,
                                          (at+WINDOW_MS)/1000,at/1000)).fetchone()
                if row and type(row[0]) in (int,float,Decimal) and math.isfinite(float(row[0])):
                    observed_at=float(row[0])
                    ready=_yes_no(row[1])
                    fresh=_yes_no(row[2])
                    item.update(state='nearby-15m-analysis-observed',
                        analysisAt=observed_at*1000,
                        timeRelation='before-or-at-event' if observed_at*1000<=at else 'after-event',
                        deltaSeconds=round(abs(observed_at*1000-at)/1000,3),
                        ready=ready,priceFresh=fresh,
                        sourceAgeAtAnalysisSeconds=_source_age(row[3],observed_at))
                    counts['nearby15mAnalysis']+=1
                    if ready is True and fresh is True:
                        counts['readyFresh15mAnalysis']+=1
                else:
                    item['state']='no-15m-analysis-in-90s-window'
                    counts['no15mAnalysisInWindow']+=1
            except Exception:
                item['state']='analysis-history-query-unavailable'
                counts['queryUnavailable']+=1
        items.append(item)
    return {
        'status':'partial' if counts['queryUnavailable'] or len(times)<len(original)
                 else 'observed',
        'readOnly':True,'realOrders':False,
        'sampledDistinctClocks':len(times),
        'totalDistinctClocks':len(original),
        'windowSeconds':90,
        'truncated':len(times)<len(original),
        'counts':counts,'items':items,
        'scope':'nearby-15m-analysis-observation-not-paper-input-confirmation',
        'note':'A nearby 15m result may come from another worker. It does not prove '
               'that the paper account saw that data or that a safe exit was possible. '
               'No original product prices or outcomes are inferred.'
    }
