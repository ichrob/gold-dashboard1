"""Fixed, private PostgreSQL metadata probes; never accepts user SQL.

Called inside the existing authenticated read-only storage report. No original
payloads, query text, credentials, client addresses, mutations or ANALYZE.
"""
import math
import time

TABLES = ('bob_diagnostic_history', 'bob_candle_evidence', 'bob_candle_checkpoints')
TABLE_METRICS = ('estimatedLiveRows', 'estimatedDeadRows', 'lastAnalyzeAt',
                 'lastAutoanalyzeAt', 'lastAutovacuumAt', 'changesSinceAnalyze',
                 'insertsSinceVacuum', 'sequentialScans', 'indexScans',
                 'vacuumCount', 'autovacuumCount')
ACTIVITY_METRICS = ('sessions', 'active', 'waitingOnLock', 'idleInTransaction',
                    'waitingOnIO', 'idleInTransactionAborted', 'visibilityUnknown',
                    'oldestActiveSeconds', 'oldestTransactionSeconds')
NODES = frozenset(('Aggregate', 'Limit', 'Seq Scan', 'Index Scan',
                  'Index Only Scan', 'Bitmap Heap Scan', 'Bitmap Index Scan',
                  'Gather', 'Gather Merge', 'Sort', 'Result', 'Subquery Scan'))


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**15 else None


def project(data):
    data = data if type(data) is dict else {}
    out = {'status': data.get('status') if data.get('status') in
           ('observed', 'unavailable', 'read-only-required') else 'unavailable',
           'readOnly': True, 'observedAt': number(data.get('observedAt')),
           'scope': 'fixed-metadata-and-estimated-plan-not-query-execution',
           'tables': [], 'activity': {}, 'capCountPlan': []}
    tables = data.get('tables') if type(data.get('tables')) is list else []
    for row in tables[:3]:
        if type(row) is dict and row.get('table') in TABLES:
            out['tables'].append({'table': row['table'], **{key: number(row.get(key))
                for key in TABLE_METRICS}})
    activity = data.get('activity') if type(data.get('activity')) is dict else {}
    out['activity'] = {key: number(activity.get(key)) for key in
                       ACTIVITY_METRICS}
    plans = data.get('capCountPlan') if type(data.get('capCountPlan')) is list else []
    for node in plans[:12]:
        if type(node) is dict and node.get('node') in NODES:
            out['capCountPlan'].append({'node': node['node'],
                'estimatedRows': number(node.get('estimatedRows')),
                'estimatedCost': number(node.get('estimatedCost'))})
    return out


def report(conn):
    result = {'status': 'unavailable', 'observedAt': None}
    try:
        with conn.transaction():
            if conn.execute('SHOW transaction_read_only').fetchone()[0] != 'on':
                return project({'status': 'read-only-required'})
            previous = conn.execute('SHOW statement_timeout').fetchone()[0]
            conn.execute("SET LOCAL statement_timeout='750ms'")
            rows = conn.execute('''SELECT relname,n_live_tup,n_dead_tup,
                extract(epoch FROM last_analyze),extract(epoch FROM last_autoanalyze),
                extract(epoch FROM last_autovacuum),n_mod_since_analyze,
                n_ins_since_vacuum,seq_scan,idx_scan,vacuum_count,autovacuum_count
                FROM pg_stat_user_tables
                WHERE schemaname=current_schema() AND relname=ANY(%s::text[])
                ORDER BY relname LIMIT 3''', (list(TABLES),)).fetchall()
            activity = conn.execute('''SELECT count(*),
                count(*) FILTER (WHERE state='active'),
                count(*) FILTER (WHERE wait_event_type='Lock'),
                count(*) FILTER (WHERE state='idle in transaction'),
                count(*) FILTER (WHERE wait_event_type='IO'),
                count(*) FILTER (WHERE state='idle in transaction (aborted)'),
                count(*) FILTER (WHERE state IS NULL),
                max(GREATEST(0,extract(epoch FROM clock_timestamp()-query_start)))
                    FILTER (WHERE state='active'),
                max(GREATEST(0,extract(epoch FROM clock_timestamp()-xact_start)))
                    FILTER (WHERE xact_start IS NOT NULL)
                FROM pg_stat_activity WHERE datid=(
                    SELECT oid FROM pg_database WHERE datname=current_database())
                    AND pid<>pg_backend_pid()''').fetchone()
            # Same bounded count as retention; EXPLAIN never executes the count.
            from diagnostic_history import _PRUNE_MAX_EVENTS, _PRUNE_CAP_BATCH_SIZE
            plan = conn.execute('''EXPLAIN (FORMAT JSON)
                SELECT count(*) FROM (SELECT 1 FROM bob_diagnostic_history
                LIMIT %s) AS bounded_history''',
                (_PRUNE_MAX_EVENTS + _PRUNE_CAP_BATCH_SIZE,)).fetchone()[0]
            nodes, pending = [], [plan[0]['Plan']]
            while pending and len(nodes) < 12:
                node = pending.pop(0)
                nodes.append({'node': node.get('Node Type'),
                    'estimatedRows': node.get('Plan Rows'), 'estimatedCost': node.get('Total Cost')})
                pending.extend(node.get('Plans', [])[:12])
            # Cumulative counters are not rates or reclaimable-byte estimates.
            # NULL ages mean no visible matching session; unknown state counts
            # disclose restricted pg_stat_activity visibility.
            result.update(status='observed', observedAt=time.time(), tables=[{
                'table': row[0], **{key: float(value) if value is not None else None
                                   for key, value in zip(TABLE_METRICS, row[1:])}}
                for row in rows], activity={key: float(value) if value is not None else None
                    for key, value in zip(ACTIVITY_METRICS, activity)}, capCountPlan=nodes)
            conn.execute("SELECT set_config('statement_timeout',%s,true)", (previous,))
    except Exception:
        # Savepoint rollback restores the caller's timeout and transaction.
        # Do not expose SQL, exception messages, endpoints or credentials.
        return project({'status': 'unavailable'})
    return project(result)
