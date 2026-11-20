"""Bounded reuse of dead-row space; never delete or rewrite live evidence."""
import json
import os
import threading
import time

_THREAD = None
_LOCK = threading.Lock()
# Fixed SQL identifiers: never interpolate user input or catalog names.
# Keep the existing hourly worker unchanged. Large decision-audit TOAST/index
# maintenance is an explicit one-table operator action only, not a fifth
# recurring vacuum and never a table rewrite.
_AUTO_TABLES = ('bob_diagnostic_history', 'bob_android_list_images', 'bob_metric_checks', 'bob_improvement_observations')
_MANUAL_ONLY_TABLES = ('bob_decision_audit',)
_TABLES = _AUTO_TABLES + _MANUAL_ONLY_TABLES


def connect():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True,
        connect_timeout=10, application_name='bob_storage_maintenance',
        options='-c statement_timeout=60000 -c lock_timeout=1000 '
                '-c vacuum_cost_delay=10 -c vacuum_cost_limit=100 '
                '-c maintenance_work_mem=16384')


@__import__("ocr_workload_priority").maintenance
def run_once(factory=connect, *, reclaim_metric_tail=False, reclaim_analysis_tail=False,
             reclaim_observation_tail=False, reclaim_image_tail=False, target_table=None,
             manual_decision_audit=False):
    """A dedicated autocommit connection, at most four time-limited vacuums.

    bob_decision_audit requires target_table plus an explicit manual_decision_audit=True
    flag, and is never scheduled.

    No FULL: never rewrite tables. After cold offload, cold-table tail truncation
    may briefly lock the table; the whole command is limited to ten seconds.
    Completed VACUUM is not proof of freed disk bytes (or all tuples removable).
    PostgreSQL autovacuum remains enabled and responsible for general upkeep.
    """
    # Only the fixed allowlist is ever used in SQL; never accept dynamic names.
    if target_table is not None and target_table not in _TABLES:
        raise ValueError('Unapproved maintenance target')
    # A plain target_table argument must never silently expand the old allowlist.
    # Preserve the pre-existing hard rejection before any connection or SQL.
    if target_table in _MANUAL_ONLY_TABLES and manual_decision_audit is not True:
        raise ValueError('Manual decision audit confirmation required')
    if manual_decision_audit is not False and not (
            manual_decision_audit is True and target_table in _MANUAL_ONLY_TABLES):
        raise ValueError('Manual flag requires the exact approved target')
    # No automatic extra checks for the original four hourly targets.
    # The large manual-only decision audit must also have fresh Render
    # PostgreSQL RAM headroom BEFORE opening a database connection.
    if manual_decision_audit is True:
        ram = __import__('render_memory_guard').report()
        if ram.get('status') != 'memory-headroom-observed':
            return {'status': ('deferred-memory-pressure' if
                    ram.get('status') == 'memory-pressure' else
                    'deferred-memory-proof-unavailable'), 'tables': [],
                    'evidenceDeleted': False, 'diskBytesFreed': None}
    results = []
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError('Dedicated autocommit connection required')
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('bob_storage_maintenance_v1'))").fetchone()[0]:
            return {'status': 'busy', 'tables': []}
        # Closing this dedicated connection releases the session advisory lock.
        for table in ((target_table,) if target_table is not None else _AUTO_TABLES):
            row = conn.execute('''SELECT n_dead_tup FROM pg_stat_user_tables
                WHERE schemaname='public' AND relname=%s
                AND n_dead_tup>0
                AND (last_vacuum IS NULL OR last_vacuum<now()-interval '6 hours')
                AND (last_autovacuum IS NULL OR last_autovacuum<now()-interval '6 hours')''', (table,)).fetchone()
            reclaim = ((reclaim_metric_tail and table == 'bob_metric_checks')
                       or (reclaim_analysis_tail and table == 'bob_diagnostic_history')
                       or (reclaim_observation_tail and table == 'bob_improvement_observations')
                       or (reclaim_image_tail and table == 'bob_android_list_images'))
            if not row and not reclaim:
                continue
            try:
                # Names are fixed above. ONLY excludes unexpected child tables.
                before = None
                conn.execute("SET statement_timeout = '60s'")
                if reclaim:
                    conn.execute("SET statement_timeout = '10s'")
                    before = conn.execute('SELECT pg_total_relation_size(%s)', ('public.' + table,)).fetchone()[0]
                truncate = 'TRUE' if reclaim else 'FALSE'
                conn.execute('VACUUM (SKIP_LOCKED, TRUNCATE ' + truncate + ', PARALLEL 0) ONLY public.' + table)
                result = {'table': table, 'status': 'command-completed'}
                if reclaim:
                    after = conn.execute('SELECT pg_total_relation_size(%s)', ('public.' + table,)).fetchone()[0]
                    result.update(relationBytesBefore=before, relationBytesAfter=after,
                                  observedRelationBytesDecrease=max(0, before-after))
                results.append(result)
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
                        # Optional single-table tail reclaim: disabled by default,
                        # weekend-only, independently backed up, durably claimed.
                        # Not an archive writer, SQL rewrite or startup hook.
                        import storage_tail_once
                        if storage_tail_once.configuration() is not None:
                            result['tailReclaimOnce'] = storage_tail_once.run_once()
                except Exception as exc:
                    result = {'status': 'deferred', 'errorType': type(exc).__name__}
                # Error types only: never DSNs, credentials or database payloads.
                print('BOB_STORAGE_MAINTENANCE ' + json.dumps(result, sort_keys=True), flush=True)
                time.sleep(3600)
        _THREAD = threading.Thread(target=loop, name='bob-storage-maintenance', daemon=True)
        _THREAD.start()
