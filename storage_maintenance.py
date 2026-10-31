"""Bounded reuse of dead-row space; never delete or rewrite live evidence."""
import json
import os
import threading
import time

_THREAD = None
_LOCK = threading.Lock()
# Fixed SQL identifiers: never interpolate user input or catalog names.
_TABLES = ('bob_diagnostic_history', 'bob_android_list_images', 'bob_metric_checks')


def connect():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True,
        connect_timeout=10, application_name='bob_storage_maintenance',
        options='-c statement_timeout=60000 -c lock_timeout=1000 '
                '-c vacuum_cost_delay=10 -c vacuum_cost_limit=100 '
                '-c maintenance_work_mem=16384')


def run_once(factory=connect):
    """A dedicated autocommit connection, at most three time-limited vacuums.

    No FULL or truncation: avoid table rewrites and exclusive truncation locks.
    Completed VACUUM is not proof of freed disk bytes (or all tuples removable).
    PostgreSQL autovacuum remains enabled and responsible for general upkeep.
    """
    results = []
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError('Dedicated autocommit connection required')
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('bob_storage_maintenance_v1'))").fetchone()[0]:
            return {'status': 'busy', 'tables': []}
        # Closing this dedicated connection releases the session advisory lock.
        for table in _TABLES:
            row = conn.execute('''SELECT n_dead_tup FROM pg_stat_user_tables
                WHERE schemaname='public' AND relname=%s
                AND n_dead_tup>0
                AND (last_vacuum IS NULL OR last_vacuum<now()-interval '6 hours')
                AND (last_autovacuum IS NULL OR last_autovacuum<now()-interval '6 hours')''', (table,)).fetchone()
            if not row:
                continue
            try:
                # Names are fixed above. ONLY excludes unexpected child tables.
                conn.execute('VACUUM (SKIP_LOCKED, TRUNCATE FALSE, PARALLEL 0) ONLY public.' + table)
                results.append({'table': table, 'status': 'command-completed'})
            except Exception as exc:
                results.append({'table': table, 'status': 'deferred', 'errorType': type(exc).__name__})
    return {'status': 'checked', 'tables': results, 'evidenceDeleted': False,
            'diskBytesFreed': None, 'purpose': 'reuse-dead-row-space'}


def start():
    global _THREAD
    if not os.environ.get('DATABASE_URL') or os.environ.get('BOB_STORAGE_MAINTENANCE_DISABLED') == '1':
        return
    with _LOCK:
        if _THREAD is not None:
            return
        def loop():
            time.sleep(180)
            while True:
                try:
                    if __import__('archive_worker').status().get('status') == 'running':
                        result = {'status': 'archive-running'}
                    else:
                        result = run_once()
                except Exception as exc:
                    result = {'status': 'deferred', 'errorType': type(exc).__name__}
                # Error types only: never DSNs, credentials or database payloads.
                print('BOB_STORAGE_MAINTENANCE ' + json.dumps(result, sort_keys=True), flush=True)
                time.sleep(3600)
        _THREAD = threading.Thread(target=loop, name='bob-storage-maintenance', daemon=True)
        _THREAD.start()
