"""Explicit, expiring, single-attempt metric compaction; never deletes live rows."""
import datetime as dt
import json
import os
import threading
import time

M = 1_000_000
TABLE = 'public.bob_metric_checks'
INDEXES = ('public.bob_metric_checks_pkey', 'public.bob_metric_checked')


def connect():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, connect_timeout=10,
        application_name='bob_metric_compaction', options='-c statement_timeout=30000 '
        '-c lock_timeout=1000 -c maintenance_work_mem=16384 -c work_mem=4096')


def size(conn):
    return conn.execute("SELECT pg_total_relation_size('public.bob_metric_checks')").fetchone()[0]


def compact(conn, budget):
    """One index at a time, then rewrite only when conservatively budgeted.

    Budget is a fresh operator-observed free-space lower bound, not DB allocation
    minus pg_database_size. Estimates cannot measure WAL recycling or filesystem
    overhead; reserve 50 MB and budget two copies of the expanded live footprint.
    Every command has the dedicated connection's 30s timeout and 1s lock timeout.
    """
    before = size(conn)
    if before > 120*M:
        return {'status': 'table-too-large', 'relationBytesBefore': before}
    operations = []
    for index in INDEXES:
        row = conn.execute('''SELECT pg_relation_size(i.indexrelid) FROM pg_index i
            WHERE i.indexrelid=to_regclass(%s) AND i.indrelid=to_regclass(%s)
            AND i.indisvalid''', (index, TABLE)).fetchone()
        if not row or 3*row[0]+50*M > budget:
            continue
        try:
            conn.execute('REINDEX INDEX ' + index)
            operations.append({'index': index, 'status': 'completed'})
        except Exception as exc:
            operations.append({'index': index, 'status': 'deferred', 'errorType': type(exc).__name__})
            # Do not follow a failed rewrite with another, more expensive one.
            return {'status': 'deferred', 'operations': operations,
                    'relationBytesBefore': before, 'relationBytesAfter': size(conn)}
    # Include tuple/line-pointer/page overhead and the current indexes. pg_column_size
    # of JSONB alone would dangerously understate the rewrite's storage footprint.
    row = conn.execute('''SELECT coalesce(sum(pg_column_size(t)+32),0),count(*)
        FROM public.bob_metric_checks t''').fetchone()
    indexes = conn.execute("SELECT pg_indexes_size('public.bob_metric_checks')").fetchone()[0]
    estimate = int(row[0]*1.5)+indexes
    result = {'relationBytesBefore': before, 'estimatedRewriteBytes': estimate,
              'observedBudgetBytes': budget, 'operations': operations}
    if 2*estimate+50*M > budget:
        result['status'] = 'rewrite-budget-insufficient'
    else:
        try:
            conn.execute('VACUUM (FULL) ONLY public.bob_metric_checks')
            result['status'] = 'completed'
        except Exception as exc:
            result.update(status='deferred', errorType=type(exc).__name__)
    result['relationBytesAfter'] = size(conn)
    result['observedRelationBytesDecrease'] = max(0, before-result['relationBytesAfter'])
    # A database relation decrease is not a measured whole-volume free-space value.
    result['diskBytesFreed'] = None
    return result


def run_once(config, factory=connect, now=None):
    now = time.time() if now is None else now
    if not isinstance(config, dict) or not isinstance(config.get('id'), str):
        return {'status': 'invalid-configuration'}
    observed = config.get('observedAt', 0)
    if not isinstance(observed, (int,float)) or not 0 <= now-observed <= 3600:
        return {'status': 'observation-expired'}
    budget = config.get('freeBytes', 0)
    baseline = config.get('databaseBytes', 0)
    if type(budget) is not int or not 100*M <= budget <= 200*M or type(baseline) is not int or baseline<=0:
        return {'status': 'invalid-budget'}
    if __import__('archive_worker').status().get('status') == 'running':
        return {'status': 'archive-running'}
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError('Dedicated autocommit connection required')
        for key in ('bob_storage_maintenance_v1', 'bob_cold_metrics_v1'):
            if not conn.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (key,)).fetchone()[0]:
                return {'status': 'busy'}
        proof = conn.execute('''SELECT receipt FROM bob_archive_attempts WHERE status='verified'
            AND updated_at>now()-interval '24 hours' ORDER BY updated_at DESC LIMIT 1''').fetchone()
        receipt = (proof[0] or {}).get('receipt', {}) if proof else {}
        if receipt.get('restoreVerified') is not True or receipt.get('remoteDownloadVerified') is not True:
            return {'status': 'verified-backup-required'}
        current = conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        # Account for growth since the measured free-space observation. Never add
        # supposed savings before WAL/filesystem reclamation has been measured.
        budget -= max(0, current-baseline)
        conn.execute('''CREATE TABLE IF NOT EXISTS bob_metric_compaction_attempts (
            id TEXT PRIMARY KEY, attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(), result JSONB NOT NULL)''')
        claimed = conn.execute('''INSERT INTO bob_metric_compaction_attempts(id,result)
            VALUES(%s,'{"status":"started"}') ON CONFLICT DO NOTHING RETURNING id''', (config['id'],)).fetchone()
        if not claimed:
            return {'status': 'already-attempted'}
        try:
            result = compact(conn, budget)
        except Exception as exc:
            result = {'status': 'deferred', 'errorType': type(exc).__name__}
        conn.execute('UPDATE bob_metric_compaction_attempts SET result=%s::jsonb WHERE id=%s',
                     (json.dumps(result),config['id']))
        return result


def start():
    raw = os.environ.get('BOB_METRIC_COMPACTION_ONCE')
    if not raw:
        return
    def work():
        time.sleep(120)
        try:
            result = run_once(json.loads(raw))
        except Exception as exc:
            result = {'status': 'deferred', 'errorType': type(exc).__name__}
        print('BOB_METRIC_COMPACTION ' + json.dumps(result, sort_keys=True), flush=True)
    threading.Thread(target=work, name='bob-metric-compaction', daemon=True).start()
