"""Explicit, expiring, single-attempt metric compaction; never deletes live rows."""
import json
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

M = 1_000_000
TABLE = 'public.bob_metric_checks'
INDEXES = ('public.bob_metric_checks_pkey', 'public.bob_metric_checked')
TARGETS = {
    'metric': (TABLE, INDEXES, 120*M),
    'diagnostic': ('public.bob_diagnostic_history', tuple('public.bob_diagnostic_history'+suffix
        for suffix in ('_pkey','_time','_stage','_source_window','_trace')), 200*M),
    # A previously verified 47MB TOAST-bloat source. A one-table FULL rebuild
    # uses less scratch than pg_repack but requires a quiet exclusive lock.
    'improvement': ('public.bob_improvement_observations', (), 80*M),
}
# Reserved worker startup: archive 60s, observations 90s, metric offload 240s.
# Only explicitly enabled compaction starts here, after the archive gate but
# before the long-running observation worker can take its advisory lock.
COMPACTION_START_DELAY_SECONDS = 75
LOCKS = (
    ('maintenance', 'bob_storage_maintenance_v1'),
    ('cold-metrics', 'bob_cold_metrics_v1'),
    ('cold-analysis', 'bob_cold_analysis_v1'),
    ('cold-observations', 'bob_cold_observations_v1'),
)


def connect():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'], autocommit=True, connect_timeout=10,
        application_name='bob_metric_compaction', options='-c statement_timeout=30000 '
        '-c lock_timeout=1000 -c maintenance_work_mem=16384 -c work_mem=4096')



def _improvement_quiet(now):
    clock=datetime.fromtimestamp(now, ZoneInfo('Europe/Zurich'))
    return clock.hour>=22 or clock.hour<7


def _improvement_volume(now):
    """Separate provider physical volume, NOT pg_database_size arithmetic."""
    import render_disk_metrics
    v=render_disk_metrics.report()
    observed=v.get('observedAt')
    if (v.get('status')!='observed' or
            v.get('resource')!='dpg-datjno1srm7s738vv500-a' or
            v.get('unit')!='bytes' or
            type(observed) not in (int,float) or
            not 0<=now-observed<=300 or
            type(v.get('diskUsage')) is not int or
            v['diskUsage']>725_000_000):
        return None
    return v['diskUsage']


def _improvement_wal_rate(conn):
    """Recent WAL write rate only; headroom comes from physical reserve."""
    try:
        a=conn.execute('SELECT wal_bytes::numeric,stats_reset FROM pg_stat_wal').fetchone()
        time.sleep(2)
        b=conn.execute('SELECT wal_bytes::numeric,stats_reset FROM pg_stat_wal').fetchone()
        if (not a or not b or a[0] is None or b[0] is None or
                a[1] != b[1] or not 0<=int(b[0]-a[0])<=4_000_000):
            return False
        return True
    except Exception:
        return False


def _improvement_bloat():
    """Current rollback-only measurement; no trusted caller-supplied flag."""
    try:
        proof=__import__('storage_repack_bloat_probe').inspect_once()
    except Exception:
        return False
    return (proof.get('table')=='public.bob_improvement_observations' and
        proof.get('rollbackVerified') is True and
        proof.get('databaseRowsModified') is False and
        type(proof.get('combinedDeadAndApproxFreeBytes')) is int and
        proof['combinedDeadAndApproxFreeBytes']>=30_000_000)


def _improvement_sample(conn):
    """At most 32 source row hashes; never log keys or original evidence."""
    q='SELECT campaign,slot,md5(payload::text) FROM public.bob_improvement_observations '
    return set(conn.execute(q+'ORDER BY campaign,slot LIMIT 16').fetchall()+
               conn.execute(q+'ORDER BY campaign DESC,slot DESC LIMIT 16').fetchall())


def size(conn, target='metric'):
    return conn.execute('SELECT pg_total_relation_size(%s)', (TARGETS[target][0],)).fetchone()[0]


def compact(conn, budget, *, resume=False, target='metric'):
    """One index at a time, then rewrite only when conservatively budgeted.

    Budget is a fresh operator-observed free-space lower bound, not DB allocation
    minus pg_database_size. Estimates cannot measure WAL recycling or filesystem
    overhead; reserve 50 MB and budget two copies of the expanded live footprint.
    Ordinary commands have a 30s timeout and 1s lock timeout. An explicitly
    resumed, proven timed-out FULL gets 90s; successful indexes are not rebuilt.
    """
    if target not in TARGETS:
        return {'status':'invalid-target'}
    table, allowed_indexes, maximum = TARGETS[target]
    before = size(conn, target)
    source_sample=_improvement_sample(conn) if target=='improvement' else None
    source_count=(conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
                  if target=='improvement' else None)
    if before > maximum:
        return {'status': 'table-too-large', 'relationBytesBefore': before}
    operations = []
    for index in (() if resume else allowed_indexes):
        row = conn.execute('''SELECT pg_relation_size(i.indexrelid) FROM pg_index i
            WHERE i.indexrelid=to_regclass(%s) AND i.indrelid=to_regclass(%s)
            AND i.indisvalid''', (index, table)).fetchone()
        if not row or 3*row[0]+50*M > budget:
            continue
        try:
            conn.execute('REINDEX INDEX ' + index)
            operations.append({'index': index, 'status': 'completed'})
            # Charge fresh index writes twice for unrecycled WAL/temporary space;
            # never credit index shrink as measured whole-volume free space.
            written = conn.execute('SELECT pg_relation_size(%s)', (index,)).fetchone()[0]
            budget -= 2*written
        except Exception as exc:
            operations.append({'index': index, 'status': 'deferred', 'errorType': type(exc).__name__})
            # Do not follow a failed rewrite with another, more expensive one.
            return {'status': 'deferred', 'operations': operations,
                    'target': target, 'relationBytesBefore': before, 'relationBytesAfter': size(conn, target)}
    # Include tuple/line-pointer/page overhead and the current indexes. pg_column_size
    # of JSONB alone would dangerously understate the rewrite's storage footprint.
    row = conn.execute('SELECT coalesce(sum(pg_column_size(t)+32),0),count(*) FROM ' + table + ' t').fetchone()
    indexes = conn.execute('SELECT pg_indexes_size(%s)', (table,)).fetchone()[0]
    toast = conn.execute('''SELECT coalesce(pg_total_relation_size(nullif(reltoastrelid,0)),0)
        FROM pg_class WHERE oid=to_regclass(%s)''', (table,)).fetchone()[0]
    # Whole-row sizing must never accidentally omit externally stored values.
    # Count the complete TOAST relation too, even if this double-counts bytes.
    estimate = int(row[0]*1.5)+indexes+toast
    result = {'target': target, 'relationBytesBefore': before, 'estimatedRewriteBytes': estimate,
              'observedBudgetBytes': budget, 'toastRelationBytes': toast, 'operations': operations}
    if 2*estimate+50*M > budget:
        result['status'] = 'rewrite-budget-insufficient'
    else:
        try:
            if resume or target == 'diagnostic':
                conn.execute("SET statement_timeout = '90s'")
            conn.execute('VACUUM (FULL) ONLY ' + table)
            result['status'] = 'completed'
        except Exception as exc:
            result.update(status='deferred', errorType=type(exc).__name__)
    result['relationBytesAfter'] = size(conn, target)
    if target=='improvement' and result['status']=='completed':
        new_count=conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
        if new_count<source_count or _improvement_sample(conn)!=source_sample:
            result['status']='source-verification-mismatch'
        result['sourceRowsVerified']=(result['status']=='completed')
    result['observedRelationBytesDecrease'] = max(0, before-result['relationBytesAfter'])
    # A database relation decrease is not a measured whole-volume free-space value.
    result['diskBytesFreed'] = None
    return result


def resumable(result, target='metric'):
    return (target in TARGETS and isinstance(result, dict) and result.get('target','metric') == target
            and result.get('status') == 'deferred'
            and result.get('errorType') == 'QueryCanceled'
            and result.get('operations') == [
                {'index': index, 'status': 'completed'} for index in TARGETS[target][1]])


def run_once(config, factory=connect, now=None):
    now = time.time() if now is None else now
    if not isinstance(config, dict) or not isinstance(config.get('id'), str):
        return {'status': 'invalid-configuration'}
    target = config.get('target','metric')
    if target not in TARGETS:
        return {'status':'invalid-target'}
    # Never acquire a database connection during Bobs active trading window.
    if target=='improvement' and not _improvement_quiet(now):
        return {'status':'market-hours-deferred'}
    observed = config.get('observedAt', 0)
    if not isinstance(observed, (int,float)) or not 0 <= now-observed <= 3600:
        return {'status': 'observation-expired'}
    budget = config.get('freeBytes', 0)
    baseline = config.get('databaseBytes', 0)
    if type(budget) is not int or not 100*M <= budget <= 250*M or type(baseline) is not int or baseline<=0:
        return {'status': 'invalid-budget'}
    if __import__('archive_worker').status().get('status') == 'running':
        return {'status': 'archive-running'}
    volume = _improvement_volume(now) if target=='improvement' else None
    if target=='improvement' and volume is None:
        return {'status':'fresh-volume-proof-unavailable'}
    if target=='improvement' and not _improvement_bloat():
        return {'status':'verified-bloat-proof-unavailable'}
    with factory() as conn:
        if not conn.autocommit:
            raise ValueError('Dedicated autocommit connection required')
        for label, key in LOCKS:
            if not conn.execute('SELECT pg_try_advisory_lock(hashtext(%s))', (key,)).fetchone()[0]:
                # Fixed labels only; no SQL text, database credentials or data.
                # No attempt claim has been written, so an operator can decide
                # whether a new fresh-observation run is safe.
                return {'status': 'busy', 'blockedBy': label}
        proof = conn.execute('''SELECT receipt FROM bob_archive_attempts WHERE status='verified'
            AND updated_at>now()-interval '24 hours' ORDER BY updated_at DESC LIMIT 1''').fetchone()
        receipt = (proof[0] or {}).get('receipt', {}) if proof else {}
        if receipt.get('restoreVerified') is not True or receipt.get('remoteDownloadVerified') is not True:
            return {'status': 'verified-backup-required'}
        if target=='improvement':
            relation=size(conn,target)
            # Provider physical unused space covers both copies plus separate
            # 120MB WAL/scratch buffer; max fixed relation size is 80MB.
            if (relation>80*M or
                    1_000_000_000-volume-2*relation<=120*M or
                    not _improvement_wal_rate(conn)):
                return {'status':'improvement-reserve-or-wal-proof-unavailable'}
        current = conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        # Account for growth since the measured free-space observation. Never add
        # supposed savings before WAL/filesystem reclamation has been measured.
        budget -= max(0, current-baseline)
        conn.execute('''CREATE TABLE IF NOT EXISTS bob_metric_compaction_attempts (
            id TEXT PRIMARY KEY, attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(), result JSONB NOT NULL)''')
        resume = False
        if config.get('resumeFrom'):
            previous = conn.execute('SELECT result FROM bob_metric_compaction_attempts WHERE id=%s',
                                    (config['resumeFrom'],)).fetchone()
            if not previous or not resumable(previous[0], target):
                return {'status': 'resume-proof-required'}
            resume = True
        claimed = conn.execute('''INSERT INTO bob_metric_compaction_attempts(id,result)
            VALUES(%s,'{"status":"started"}') ON CONFLICT DO NOTHING RETURNING id''', (config['id'],)).fetchone()
        if not claimed:
            return {'status': 'already-attempted'}
        try:
            result = compact(conn, budget, resume=resume, target=target)
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
        time.sleep(COMPACTION_START_DELAY_SECONDS)
        try:
            result = run_once(json.loads(raw))
        except Exception as exc:
            result = {'status': 'deferred', 'errorType': type(exc).__name__}
        print('BOB_METRIC_COMPACTION ' + json.dumps(result, sort_keys=True), flush=True)
    threading.Thread(target=work, name='bob-metric-compaction', daemon=True).start()
