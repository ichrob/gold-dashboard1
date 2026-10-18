"""Allowlisted technical summaries for the connected hourly KI repair watcher.

No private case IDs, product identities, prices, trades or raw payloads leave
PostgreSQL. Case-level evidence remains in the authenticated Bob report.
"""
import json
import time

KINDS=frozenset(('signal','title','exit'))
STATES=frozenset(('trying','escalated','recovered'))
REASONS=frozenset(('invalidStart','missingFollowup','signalUnavailable','noSelection',
    'missingBid','missingAsk','staleQuote','missingQuote','missingExit','source-time-skew','exit-time-skew','unknown'))
_last_at=0
_last_signature=None


def summary(conn):
    rows=conn.execute('''SELECT kind,status,count(*),min(attempts),max(attempts)
      FROM bob_test_repairs GROUP BY kind,status''').fetchall()
    groups=[]
    for kind,status,count,minimum,maximum in rows:
        groups.append(dict(kind=kind if kind in KINDS else 'unknown',
            status=status if status in STATES else 'unknown',cases=int(count),
            minAttempts=int(minimum),maxAttempts=int(maximum)))
    reasons={}
    for kind,reason,count in conn.execute("""SELECT kind,reason,count(*) FROM bob_test_repairs,
      LATERAL jsonb_array_elements_text(COALESCE(payload->'reasons','[]'::jsonb)) reason
      WHERE status='escalated' GROUP BY kind,reason""").fetchall():
        key=(kind if kind in KINDS else 'unknown',reason if reason in REASONS else 'missing-original-evidence')
        reasons[key]=reasons.get(key,0)+int(count)
    checked=conn.execute('SELECT last_at FROM bob_test_repair_control WHERE id=1').fetchone()
    return dict(version=1,workerCheckedAt=checked[0] if checked else None,groups=groups,
                reasons=[dict(kind=k,reason=r,cases=n) for (k,r),n in sorted(reasons.items())],route='hourly-chatgpt-watch',scope='technical-summary-only')


def publish(data,now=None):
    global _last_at,_last_signature
    now=time.monotonic() if now is None else now
    signature=json.dumps([data['groups'],data['reasons']],sort_keys=True)
    if signature==_last_signature and now-_last_at<600:return False
    print('BOB_TRAINING_HELP '+json.dumps(data,separators=(',',':'),sort_keys=True),flush=True)
    _last_signature=signature;_last_at=now
    return True
