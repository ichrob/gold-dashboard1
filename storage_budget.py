"""Bounded storage observations and lossless PostgreSQL storage tuning.

No research deletion, downsampling, paid scaling or order side effects.
Database size excludes WAL and other databases; never label it disk free space.
"""
import json
import threading
import time

# Confirmed Render allocation, 2026-10-27. Conservative decimal GB.
ALLOCATION_BYTES=1_000_000_000
CAUTION_BYTES=500_000_000
ACTION_BYTES=700_000_000  # leave room for WAL, indexes and maintenance
TABLES=('bob_decision_audit','bob_precision_quotes','bob_precision_cases',
        'bob_list_price_pairs','bob_diagnostic_history','bob_candle_evidence')
_NEXT=0
_LOCK=threading.Lock()


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_storage_samples (
        slot BIGINT PRIMARY KEY, sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        database_bytes BIGINT NOT NULL)''')


def state(size):
    return 'action-required' if size>=ACTION_BYTES else 'caution' if size>=CAUTION_BYTES else 'below-budget-threshold'


def tune(conn):
    applied=[]
    for name in TABLES:
        row=conn.execute('SELECT reloptions FROM pg_class WHERE oid=to_regclass(%s)',(name,)).fetchone()
        if not row:continue
        if 'toast_tuple_target=512' not in (row[0] or []):
            # Static table allowlist; refuse to wait behind active worker transactions.
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout='250ms'")
                conn.execute('ALTER TABLE '+name+' SET (toast_tuple_target=512)')
        applied.append(name)
    return applied


def maybe_observe(conn,now=None):
    global _NEXT
    now=time.time() if now is None else now
    if now<_NEXT or not _LOCK.acquire(blocking=False):return
    try:
        _NEXT=now+1800
        # SAVEPOINT protects the diagnostic event if metadata maintenance is unavailable.
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='3s'")
            tune(conn)
            size=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
            conn.execute('INSERT INTO bob_storage_samples(slot,database_bytes) VALUES(%s,%s) ON CONFLICT DO NOTHING',
                (int(now//1800)*1800,size))
            # Only capacity telemetry expires. Never delete test/market evidence.
            conn.execute('DELETE FROM bob_storage_samples WHERE slot<%s',(int(now)-90*86400,))
    except Exception:
        _NEXT=now+300
    finally:
        _LOCK.release()


def report(conn,now=None):
    now=time.time() if now is None else now
    size=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    # Catalog statistics and size functions, never full COUNT(*) scans of evidence.
    tables=conn.execute('''SELECT relname,pg_total_relation_size(relid),
        n_live_tup,n_dead_tup,last_autovacuum
        FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 12''').fetchall()
    samples=conn.execute('SELECT slot,database_bytes FROM bob_storage_samples ORDER BY slot DESC LIMIT 336').fetchall()
    growth=None;days=None
    if len(samples)>1:
        last,first=samples[0],samples[-1]
        elapsed=last[0]-first[0]
        if elapsed>=86400:
            growth=(last[1]-first[1])*86400/elapsed
            if growth>0:days=max(0,(ACTION_BYTES-size)/growth)
    policy=conn.execute('SELECT relname,reloptions FROM pg_class WHERE relname=ANY(%s)',(list(TABLES),)).fetchall()
    return dict(status='observed',readOnly=True,observedAt=now,
        databaseBytes=size,configuredAllocationBytes=ALLOCATION_BYTES,
        budgetState=state(size),cautionBytes=CAUTION_BYTES,actionBytes=ACTION_BYTES,
        scope='logical-database-size-not-total-disk-use-or-free-space',
        estimatedGrowthBytesPerDay=round(growth) if growth is not None else None,
        estimatedDaysToActionThreshold=round(days,1) if days is not None else None,
        growthStatus='observed' if growth is not None else 'needs-at-least-24-hours',
        lastSampleAt=samples[0][0] if samples else None,
        losslessStorageTables=[name for name,opts in policy if 'toast_tuple_target=512' in (opts or [])],
        largestTables=[dict(table=name,bytes=n,estimatedRows=live,estimatedDeadRows=dead,
            lastAutovacuum=str(vac) if vac else None) for name,n,live,dead,vac in tables],
        evidenceDeleted=False,automaticPaidScaling=False,
        note='Compression keeps original values. Existing rows are not bulk-rewritten. '
             'Dead-row estimates do not measure reclaimable disk bytes. Capacity forecasts are estimates.')
