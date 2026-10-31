"""Bounded storage observations for durable comparison evidence.

No research deletion, downsampling, paid scaling or order side effects.
Database size excludes WAL and other databases; never label it disk free space.
"""
import json
import threading
import time
from contextlib import nullcontext

# Confirmed Render allocation, 2026-10-27. Conservative decimal GB.
ALLOCATION_BYTES=1_000_000_000
CAUTION_BYTES=500_000_000
ACTION_BYTES=700_000_000  # leave room for WAL, indexes and maintenance
_NEXT=0
_LOCK=threading.Lock()


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_storage_samples (
        slot BIGINT PRIMARY KEY, sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        database_bytes BIGINT NOT NULL,
        relation_bytes JSONB NOT NULL DEFAULT '{}'::jsonb)''')
    # Existing installations predate fixed per-relation snapshots.  Keep all
    # historical database-size samples and add only the missing observation
    # column; no evidence table or retention rule is changed.
    conn.execute("ALTER TABLE bob_storage_samples ADD COLUMN IF NOT EXISTS relation_bytes JSONB NOT NULL DEFAULT '{}'::jsonb")


def state(size):
    return 'action-required' if size>=ACTION_BYTES else 'caution' if size>=CAUTION_BYTES else 'below-budget-threshold'


def maybe_observe(conn,now=None):
    global _NEXT
    now=time.time() if now is None else now
    if now<_NEXT or not _LOCK.acquire(blocking=False):return
    try:
        _NEXT=now+1800
        # SAVEPOINT protects the diagnostic event if metadata maintenance is unavailable.
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='3s'")
            size=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
            relations=conn.execute('''SELECT relname,pg_total_relation_size(relid)
                FROM pg_stat_user_tables WHERE schemaname=current_schema()''').fetchall()
            relation_bytes={name:value for name,value in relations
                if isinstance(name,str) and isinstance(value,int) and value>=0}
            conn.execute('''INSERT INTO bob_storage_samples(slot,database_bytes,relation_bytes)
                VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
                (int(now//1800)*1800,size,json.dumps(relation_bytes,sort_keys=True)))
            # Only capacity telemetry expires. Never delete test/market evidence.
            conn.execute('DELETE FROM bob_storage_samples WHERE slot<%s',(int(now)-90*86400,))
    except Exception:
        _NEXT=now+300
    finally:
        _LOCK.release()


def archive_status(conn):
    """Combine process state with the latest persisted, sanitized attempt result."""
    process = __import__('archive_worker').status()
    try:
        # Older schemas may lack the ledger. Keep that optional read from
        # aborting the caller's transaction and subsequent cold-tier telemetry.
        with conn.transaction() if hasattr(conn, 'transaction') else nullcontext():
            row = conn.execute('''SELECT status,updated_at,receipt FROM bob_archive_attempts
                ORDER BY updated_at DESC LIMIT 1''').fetchone()
    except Exception:
        row = None
    if not row:
        return process
    stored = row[2] if isinstance(row[2], dict) else {}
    proof = stored.get('receipt') if isinstance(stored.get('receipt'), dict) else {}
    return {**process, 'latestPersistedAttempt': {
        'status': row[0], 'updatedAt': str(row[1]),
        'phase': stored.get('phase'), 'errorType': stored.get('errorType'),
        'receiptPersistenceErrorType': stored.get('receiptPersistenceErrorType'),
        'restoreVerified': proof.get('restoreVerified') is True,
        'remoteDownloadVerified': proof.get('remoteDownloadVerified') is True,
        'deletionPermitted': proof.get('deletionPermitted'),
        'evidenceDeleted': stored.get('evidenceDeleted') is True}}


def report(conn,now=None):
    now=time.time() if now is None else now
    size=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    # Catalog statistics and size functions, never full COUNT(*) scans of evidence.
    tables=conn.execute('''SELECT relname,pg_total_relation_size(relid),
        n_live_tup,n_dead_tup,last_autovacuum
        FROM pg_stat_user_tables WHERE schemaname=current_schema()
        ORDER BY pg_total_relation_size(relid) DESC LIMIT 12''').fetchall()
    samples=conn.execute('''SELECT slot,database_bytes,relation_bytes
        FROM bob_storage_samples ORDER BY slot DESC LIMIT 336''').fetchall()
    growth=None;days=None
    if len(samples)>1:
        last,first=samples[0],samples[-1]
        elapsed=last[0]-first[0]
        if elapsed>=86400:
            growth=(last[1]-first[1])*86400/elapsed
            if growth>0:days=max(0,(ACTION_BYTES-size)/growth)
    relation_samples=[sample for sample in samples
        if isinstance(sample[2],dict) and sample[2]]
    relation_deltas=[]
    relation_elapsed=None
    relation_first_at=None
    relation_last_at=None
    if len(relation_samples)>1:
        latest,baseline=relation_samples[0],relation_samples[-1]
        relation_last_at,relation_first_at=latest[0],baseline[0]
        relation_elapsed=relation_last_at-relation_first_at
        if relation_elapsed>0:
            names=set(latest[2])|set(baseline[2])
            for name in names:
                before=baseline[2].get(name)
                after=latest[2].get(name)
                if isinstance(before,int) and isinstance(after,int):
                    relation_deltas.append(dict(table=name,bytesBefore=before,
                        bytesAfter=after,bytesDelta=after-before))
            relation_deltas.sort(key=lambda item:(abs(item['bytesDelta']),item['table']),reverse=True)
    return dict(status='observed',readOnly=True,observedAt=now,
        databaseBytes=size,configuredAllocationBytes=ALLOCATION_BYTES,
        budgetState=state(size),cautionBytes=CAUTION_BYTES,actionBytes=ACTION_BYTES,
        scope='logical-database-size-not-total-disk-use-or-free-space',
        estimatedGrowthBytesPerDay=round(growth) if growth is not None else None,
        estimatedDaysToActionThreshold=round(days,1) if days is not None else None,
        growthStatus='observed' if growth is not None else 'needs-at-least-24-hours',
        lastSampleAt=samples[0][0] if samples else None,
        relationGrowthStatus='observed' if relation_deltas else 'needs-two-fixed-snapshots',
        relationBaselineSampleAt=relation_first_at,
        relationLatestSampleAt=relation_last_at,
        relationElapsedSeconds=relation_elapsed,
        largestTableDeltas=relation_deltas[:12],
        largestTables=[dict(table=name,bytes=n,estimatedRows=live,estimatedDeadRows=dead,
            lastAutovacuum=str(vac) if vac else None) for name,n,live,dead,vac in tables],
        archiveWorker=archive_status(conn),
        coldMetrics=__import__('cold_metrics').status(conn),
        evidenceDeleted=False,automaticPaidScaling=False,
        note='Cold metric payloads retain their keys and verified private archive references. '
             'Dead-row estimates do not measure reclaimable disk bytes. Capacity forecasts are estimates.')
