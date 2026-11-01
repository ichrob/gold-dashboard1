"""Bounded read-only PostgreSQL allocation and writer-counter forensics.

Only fixed public schema relation names and numeric sizes/counters. Never selects
raw audit, simulation, price, or account values. No page sampling, pgstattuple,
table rewrite, EXPLAIN ANALYZE, VACUUM, or estimate of reclaimable free bytes.
"""
from datetime import datetime, timezone

# Keep stats storage bounded: 10 fixed names, not a growing catalog dump.
WATCHED = (
    'bob_decision_audit',
    'bob_diagnostic_history',
    'bob_improvement_observations',
    'bob_decision_outcomes',
    'bob_metric_checks',
    'bob_candle_evidence',
    'bob_test_repairs',
    'bob_list_price_pairs',
    'bob_future_predictions',
    'bob_cold_observation_objects',
)
COUNTERS = ('inserted', 'updated', 'deleted', 'hotUpdated')
DAY = 86400
# Fixed 30-minute slots, tolerate missed snapshots and variable scheduler delay.
MIN_DAY = 23 * 3600
MAX_DAY = 25 * 3600


def _valid_uint(x):
    return type(x) is int and x >= 0


def snapshot_counters(conn):
    """Small metadata-only SELECT for the existing half-hour storage snapshot."""
    with conn.transaction():
        rows = conn.execute("""SELECT relname,n_tup_ins,n_tup_upd,n_tup_del,n_tup_hot_upd
            FROM pg_stat_user_tables
            WHERE schemaname=current_schema() AND relname=ANY(%s::text[])
            ORDER BY relname LIMIT 10""", (list(WATCHED),)).fetchall()
    result = {}
    for name, ins, upd, dele, hot in rows:
        values = (ins, upd, dele, hot)
        if name in WATCHED and all(_valid_uint(v) for v in values):
            result[name] = dict(zip(COUNTERS, values))
    return result


def _daily_pair(samples):
    """Find actual near-24-hour snapshot, not the oldest observed point."""
    valid = [r for r in samples if len(r) >= 3
             and _valid_uint(r[0]) and type(r[2]) is dict]
    if not valid:
        return None
    latest = max(valid, key=lambda r: r[0])
    eligible = [r for r in valid if MIN_DAY <= latest[0] - r[0] <= MAX_DAY]
    if not eligible:
        return (latest, None)
    baseline = min(eligible, key=lambda r: (abs(latest[0]-r[0]-DAY),-r[0]))
    return (latest, baseline)


def daily(samples):
    pair = _daily_pair(samples)
    if pair is None:
        return {'status': 'needs-24h-pair', 'writeCountersStatus': 'needs-two-counter-snapshots',
                'tables': [], 'diskBytesFreed': None}
    latest, previous = pair
    if previous is None:
        return {'status': 'needs-24h-pair', 'latestSlot': latest[0],
                'writeCountersStatus': 'needs-two-counter-snapshots',
                'tables': [], 'diskBytesFreed': None}

    first_sizes, last_sizes = previous[2], latest[2]
    old_writes = previous[3] if len(previous) >= 4 and type(previous[3]) is dict else {}
    new_writes = latest[3] if len(latest) >= 4 and type(latest[3]) is dict else {}
    rows = []
    states = []
    for name in WATCHED:
        before, after = first_sizes.get(name), last_sizes.get(name)
        if not _valid_uint(before) or not _valid_uint(after):
            continue
        old = old_writes.get(name)
        new = new_writes.get(name)
        state = 'needs-two-counter-snapshots'
        delta = None
        if type(old) is dict and type(new) is dict and all(
                _valid_uint(old.get(key)) and _valid_uint(new.get(key))
                for key in COUNTERS):
            values = [new[key]-old[key] for key in COUNTERS]
            if all(v >= 0 for v in values):
                state = 'observed-cumulative-counter-delta'
                delta = dict(zip(COUNTERS, values))
            else:
                # pg_stat_reset or a single-table counter reset; never label as
                # negative SQL writes or pretend the trend is complete.
                state = 'counter-reset-or-wrap'
        states.append(state)
        rows.append({'table': name,
                     'allocatedBytesBefore': before,
                     'allocatedBytesAfter': after,
                     'netAllocatedBytes': after-before,
                     'counterState': state,
                     'writeCounters': delta})
    rows.sort(key=lambda r: (-max(0,r['netAllocatedBytes']),r['table']))
    overall = ('observed' if states and all(s == 'observed-cumulative-counter-delta' for s in states)
               else 'counter-reset-or-wrap' if 'counter-reset-or-wrap' in states
               else 'partial-counters' if 'observed-cumulative-counter-delta' in states
               else 'needs-two-counter-snapshots')
    return {'status': 'observed' if rows else 'no-common-relations',
            'startSlot': previous[0], 'endSlot': latest[0],
            'elapsedSeconds': latest[0]-previous[0],
            'writeCountersStatus': overall,
            'tables': rows, 'diskBytesFreed': None,
            'scope': '24h-comparable-allocation-and-postgres-cumulative-write-counters',
            'note': 'Allocation deltas are not net inserts, reclaimed disk, or table bloat. '
                    'PostgreSQL cumulative tuple counters count estimated operations since resets; '
                    'deltas are not per-day bytes written or WAL bytes.'}



# These windows use only the already-persisted, fixed half-hour catalog
# observations. They must not issue extra production SQL, add a writer or
# infer free disk bytes from PostgreSQL relation allocation changes.
_SHORT_WINDOWS = (('twoHours', 7200), ('sixHours', 21600))
_WINDOW_TOLERANCE = 1800
_MAX_NAMED = 12


def _safe_relation_name(name):
    # Only structural Bob table names. Never echo arbitrary, sensitive,
    # quoted or unusually long catalog identifiers in private reports.
    if type(name) is not str or len(name) > 64 or not name.startswith('bob_'):
        return False
    if not all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in name):
        return False
    return not any(part in name for part in ('oauth', 'secret', 'token',
                                            'credential', 'session', 'passkey',
                                            'password', 'setting'))


def recent_windows(samples):
    """Exact 2h/6h allocation comparisons; sizes are NOT disk-free bytes.

    A source relation must exist at both observed times to be comparable.
    New/disappeared relations are not silently treated as zero-sized.
    """
    valid = [s for s in samples if len(s) >= 3 and _valid_uint(s[0])
             and _valid_uint(s[1]) and type(s[2]) is dict]
    if not valid:
        return {key: {'status': 'needs-snapshots', 'diskBytesFreed': None}
                for key, _ in _SHORT_WINDOWS}
    latest = max(valid, key=lambda r: r[0])
    windows = {}
    for label, duration in _SHORT_WINDOWS:
        prior = [s for s in valid if
                 duration - _WINDOW_TOLERANCE <= latest[0] - s[0]
                 <= duration + _WINDOW_TOLERANCE]
        if not prior:
            windows[label] = {
                'status': 'needs-snapshots', 'latestSlot': latest[0],
                'diskBytesFreed': None}
            continue
        baseline = min(prior, key=lambda s:
                       (abs(latest[0] - s[0] - duration), -s[0]))
        old, new = baseline[2], latest[2]
        common = set(old) & set(new)
        comparable = {
            k: new[k] - old[k] for k in common
            if _valid_uint(old[k]) and _valid_uint(new[k])
        }
        named = [(k, delta) for k, delta in comparable.items()
                 if _safe_relation_name(k)]
        increasing = sorted((x for x in named if x[1] > 0),
                            key=lambda x: (-x[1], x[0]))
        decreasing = sorted((x for x in named if x[1] < 0),
                            key=lambda x: (x[1], x[0]))
        database_delta = latest[1] - baseline[1]
        windows[label] = {
            'status': 'observed',
            'startSlot': baseline[0], 'endSlot': latest[0],
            'elapsedSeconds': latest[0] - baseline[0],
            'databaseBytesDelta': database_delta,
            'commonRelationBytesDelta': sum(comparable.values()),
            'comparableRelations': len(comparable),
            'nonComparableRelations': len(set(old) | set(new)) - len(comparable),
            'growingTables': [{'table': k, 'allocatedBytesDelta': v}
                              for k, v in increasing[:_MAX_NAMED]],
            'shrinkingTables': [{'table': k, 'allocatedBytesDelta': v}
                                for k, v in decreasing[:_MAX_NAMED]],
            'truncatedGrowingCount': max(0, len(increasing) - _MAX_NAMED),
            'truncatedShrinkingCount': max(0, len(decreasing) - _MAX_NAMED),
            'diskBytesFreed': None,
            'scope': 'short-window-allocation-only-not-physical-volume',
            'note': 'Net database and relation allocations need not match; '
                    'unlisted/system relations and file metadata differ. '
                    'These deltas are not WAL, physical free disk, tuple writes '
                    'or a measure of rebuildable bloat.'
        }
    return windows



def wal_directory_observation(conn):
    """Optional aggregate pg_wal file allocation; no names or maintenance.

    Some Render plans/roles do not grant pg_ls_waldir. Lack of permission
    must not invalidate the rest of the authenticated storage report.
    Files can be preallocated/recycled, so bytes are never reclaimableBytes.
    """
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='1s'")
            result=conn.execute("""SELECT count(*)::bigint,
                coalesce(sum(size),0)::bigint FROM pg_ls_waldir()""").fetchone()
        if (result is None or len(result)!=2 or
                not _valid_uint(result[0]) or not _valid_uint(result[1])):
            return {'status':'not-observed','bytes':None}
        return {'status':'observed','fileCount':result[0],
                'allocatedFileBytes':result[1],'reclaimableBytes':None,
                'scope':'pg-wal-directory-files-not-total-volume',
                'note':'Preallocated/recycled WAL files are not free or safely '
                       'reclaimable bytes. No checkpoint or file deletion.'}
    except Exception:
        return {'status':'not-observed','bytes':None,
                'reclaimableBytes':None}



def report(conn, samples):
    """Metadata size and counter report, safe inside authenticated read-only SQL."""
    try:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='2s'")
            rows = conn.execute("""SELECT s.relname,pg_relation_size(s.relid),
                  pg_indexes_size(s.relid),
                  CASE WHEN c.reltoastrelid=0 THEN 0
                       ELSE pg_total_relation_size(c.reltoastrelid) END,
                  pg_total_relation_size(s.relid),
                  pg_relation_size(s.relid,'fsm'),
                  pg_relation_size(s.relid,'vm'),
                  s.n_live_tup,s.n_dead_tup,s.n_tup_ins,s.n_tup_upd,s.n_tup_del
                FROM pg_stat_user_tables s
                JOIN pg_class c ON c.oid=s.relid
                WHERE s.schemaname=current_schema()
                  AND s.relname=ANY(%s::text[])
                ORDER BY pg_total_relation_size(s.relid) DESC LIMIT 10""",
                (list(WATCHED),)).fetchall()
        items = []
        for (name, heap, indexes, toast, total, fsm, vm,
             live, dead, inserted, updated, deleted) in rows:
            numbers = (heap,indexes,toast,total,fsm,vm,live,dead,inserted,updated,deleted)
            if name not in WATCHED or not all(_valid_uint(x) for x in numbers):
                continue
            items.append({'table': name,'totalBytes':total,'heapBytes':heap,
                'indexBytes':indexes,'toastBytes':toast,
                'otherAllocatedBytes':max(0,total-heap-indexes-toast),
                'freeSpaceMapBytes':fsm,'visibilityMapBytes':vm,
                'estimatedLiveTuples':live,'estimatedDeadTuples':dead})
        return {'status':'observed','readOnly':True,
                'layout':items, 'day':daily(samples),
                'recentWindows':recent_windows(samples),
                'walDirectory':wal_directory_observation(conn),
                'reclaimableBytes':None,'rebuildAuthorized':False,
                'method':'fixed-10-relation-catalog-read-no-page-scan',
                'note':'FSM/VM sizes describe metadata allocation, NOT the quantity of free pages. '
                       'Dead-tuple estimates, TOAST size, allocated heap and index sizes '
                       'do not prove free bytes, bloat or benefit from VACUUM FULL.'}
    except Exception:
        return {'status':'not-observed','readOnly':True,
                'day':{'status':'not-observed','tables':[]},
                'recentWindows':{'status':'not-observed'},
                'walDirectory':{'status':'not-observed'},
                'reclaimableBytes':None,'rebuildAuthorized':False}
