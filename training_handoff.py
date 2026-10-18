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
    return dict(version=2,problemGroups=problem_groups(conn),workerCheckedAt=checked[0] if checked else None,groups=groups,
                reasons=[dict(kind=k,reason=r,cases=n) for (k,r),n in sorted(reasons.items())],route='hourly-chatgpt-watch',scope='technical-summary-only')


def publish(data,now=None):
    global _last_at,_last_signature
    now=time.monotonic() if now is None else now
    signature=json.dumps([(g['id'],g['status'],g.get('episode')) for g in data['problemGroups']],sort_keys=True)
    if signature==_last_signature and now-_last_at<600:return False
    data=dict(data,messageType='problem-change' if data.get('events') else 'status-snapshot')
    print('BOB_TRAINING_HELP '+json.dumps(data,separators=(',',':'),sort_keys=True),flush=True)
    _last_signature=signature;_last_at=now
    return True

LABELS={
 'invalidStart':'Ungültiger ursprünglicher Startnachweis',
 'missingFollowup':'Original-Folgekurs im Prüfzeitfenster fehlt',
 'source-time-skew':'Zeitversatz der ursprünglichen Produktkurse',
 'exit-time-skew':'Zeitversatz der ursprünglichen Ausstiegskurse',
 'missing-original-evidence':'Ursprüngliche Produkt-/Ausstiegsnachweise fehlen',
 'unknown':'Technischer Testbefund benötigt Ursachenprüfung',
}


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_training_problem_groups (
      id TEXT PRIMARY KEY,active BOOLEAN NOT NULL,episode INTEGER NOT NULL,
      first_at BIGINT NOT NULL,last_at BIGINT NOT NULL,cases INTEGER NOT NULL)''')


def problem_groups(conn):
    # One normalized diagnosis per case. Never group by private IDs or publish them.
    rows=conn.execute('''SELECT kind,
      CASE WHEN payload->'reasons' ? 'invalidStart' THEN 'invalidStart'
           WHEN payload->'reasons' ? 'missingFollowup' THEN 'missingFollowup'
           WHEN payload->'reasons' ? 'source-time-skew' THEN 'source-time-skew'
           WHEN payload->'reasons' ? 'exit-time-skew' THEN 'exit-time-skew'
           WHEN kind IN ('title','exit') THEN 'missing-original-evidence'
           ELSE 'unknown' END AS reason,
      CASE WHEN status='escalated' AND attempts>0
           AND jsonb_array_length(COALESCE(payload->'history','[]'::jsonb))>0
           THEN 'escalated' ELSE 'trying' END AS state,
      count(*),min(attempts),max(attempts)
      FROM bob_test_repairs WHERE status IN ('trying','escalated')
      GROUP BY 1,2,3 ORDER BY 1,2,3''').fetchall()
    groups={}
    for kind,reason,state,count,minimum,maximum in rows:
        kind=kind if kind in KINDS else 'unknown'
        reason=reason if reason in LABELS else 'unknown'
        key='test:'+kind+':'+reason
        group=groups.setdefault(key,dict(id=key,kind=kind,reason=reason,type=LABELS[reason],
            status='trying',cases=0,trying=0,escalated=0,minAttempts=int(minimum),maxAttempts=0))
        group['cases']+=int(count);group[state]+=int(count)
        group['minAttempts']=min(group['minAttempts'],int(minimum))
        group['maxAttempts']=max(group['maxAttempts'],int(maximum))
        if state=='escalated':group['status']='escalated'
    return sorted(groups.values(),key=lambda g:g['id'])


def sync_groups(conn,data):
    """Stable episodes survive restarts/count changes. Trying is not recovery."""
    now=data['workerCheckedAt']
    if not isinstance(now,int):return
    conn.execute('SELECT pg_advisory_xact_lock(68431030)')
    old={key:(active,episode) for key,active,episode in conn.execute(
        'SELECT id,active,episode FROM bob_training_problem_groups').fetchall()}
    current={g['id'] for g in data['problemGroups']}
    events=[]
    for group in data['problemGroups']:
        key=group['id'];previous=old.get(key)
        # Do not dispatch a new problem while Bob is still trying.
        if group['status']!='escalated':continue
        new=not previous or not previous[0]
        episode=(previous[1]+1 if previous else 1) if new else previous[1]
        conn.execute('''INSERT INTO bob_training_problem_groups VALUES(%s,TRUE,%s,%s,%s,%s)
          ON CONFLICT(id) DO UPDATE SET active=TRUE,episode=EXCLUDED.episode,
          first_at=CASE WHEN bob_training_problem_groups.active THEN bob_training_problem_groups.first_at ELSE EXCLUDED.first_at END,
          last_at=EXCLUDED.last_at,cases=EXCLUDED.cases''',(key,episode,now,now,group['cases']))
        group['episode']=episode;group['dispatchKey']=key+':'+str(episode)
        if new:events.append(dict(id=key,episode=episode,event='opened'))
    for key,(active,episode) in old.items():
        if active and key not in current:
            conn.execute('UPDATE bob_training_problem_groups SET active=FALSE,last_at=%s,cases=0 WHERE id=%s',(now,key))
            events.append(dict(id=key,episode=episode,event='resolved'))
    data['events']=events
