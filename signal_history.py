"""Bounded SELECT-only access to original signal evidence, without account data."""
from datetime import datetime, timedelta, timezone
from bob_diagnostics import project, shape

SCHEMA = shape('direction','baseDirection','shadowDirection','ruleVersion','build','origin',
    'barAt','priceAt','price','reason','marketEvaluable','startEvidenceStatus',
    gateReasons=[None],
    earlyImpulse=shape('available','direction','barAt','reason','extensionRisk','comparisonOnly','affectsApproval'),
    minuteEntry=shape('available','direction','barAt','reason'),
    trendContext=shape('available','direction','intact','reason'))
MAX_ROWS = 5000
PAGE_SIZE = 100


def arguments(value, now=None):
    if not isinstance(value, dict) or set(value)-{'start','end','offset'}:
        raise ValueError('Only start, end and offset are supported')
    now = now or datetime.now(timezone.utc)
    def parse(key, default):
        raw = value.get(key)
        if raw is None:
            if key in value: raise ValueError('Timestamp must be a string')
            return default
        if not isinstance(raw,str) or len(raw)>40: raise ValueError('Invalid timestamp')
        at = datetime.fromisoformat(raw.replace('Z','+00:00'))
        if at.tzinfo is None: raise ValueError('Timezone required')
        return at.astimezone(timezone.utc)
    end = parse('end', now)
    start = parse('start', end-timedelta(hours=4))
    offset = value.get('offset',0)
    if type(offset) is not int or not 0<=offset<MAX_ROWS: raise ValueError('Invalid offset')
    if not timedelta(0)<end-start<=timedelta(hours=24): raise ValueError('Window must be at most 24 hours')
    return {'start':start.isoformat(),'end':end.isoformat(),'offset':offset}


def report(conn, value=None):
    args=arguments({} if value is None else value)
    # Fixed projection: never read portfolio, subscriptions, orders or arbitrary payloads.
    pairs=','.join("'%s',payload->'%s'" % (key,key) for key in SCHEMA)
    rows=conn.execute('SELECT id,recorded_at,jsonb_build_object('+pairs+''')
        FROM bob_decision_audit WHERE recorded_at >= %s AND recorded_at < %s
        ORDER BY recorded_at,id LIMIT 5001''',(args['start'],args['end'])).fetchall()
    truncated=len(rows)>MAX_ROWS
    rows=rows[:MAX_ROWS]
    records=[{'id':str(key),'recordedAt':at.isoformat(),**project(payload,SCHEMA)} for key,at,payload in rows]
    transitions=[]; previous={}; counts={}
    for row in records:
        source=(row['origin'],row['ruleVersion'])
        state=(row['direction'],row['earlyImpulse']['direction'],row['earlyImpulse']['available'])
        counts[row['direction'] or 'unknown']=counts.get(row['direction'] or 'unknown',0)+1
        if previous.get(source)!=state:
            transitions.append(row)
        previous[source]=state
    offset=args['offset']; page=records[offset:offset+PAGE_SIZE]
    return {'status':'partial' if truncated else 'observed' if records else 'empty',
        'readOnly':True,'timezone':'Europe/Zurich','window':args,'records':page,
        'recordsInWindow':None if truncated else len(records),'scannedRecords':len(records),
        'nextOffset':offset+PAGE_SIZE if offset+PAGE_SIZE<len(records) else None,
        'scanTruncated':truncated,'counts':counts,'transitions':transitions[:100],
        'transitionsTruncated':len(transitions)>100,'observedAt':datetime.now(timezone.utc).isoformat(),
        'limitations':['Original recorded decisions, never retrospectively recomputed.',
            'First transition is the first observation in this window, not necessarily signal onset.',
            'Browser and background streams and rule versions are separate; gaps remain unknown.',
            'No evidence of product approval, executed orders or push delivery.',
            'If scanTruncated, narrow the time window. Use returned window bounds for stable pagination.']}
