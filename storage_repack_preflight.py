"""Read-only, operator-only feasibility check for REAL physical PG reclamation.

No extension installation, pg_repack invocation, VACUUM FULL, DDL,
source deletion, migration, shell execution, API route, startup or worker.
Targets one explicitly fixed historical table with preserved originals.
"""
import json
import os
import re
import shutil

TARGET = 'public.bob_improvement_observations'
RESOURCE = 'dpg-datjno1srm7s738vv500-a'
from storage_capacity import ALLOCATION_BYTES, MAX_VOLUME_BYTES
MIN_RESERVE_BYTES = 120_000_000
MAX_TABLE_BYTES = 100_000_000
VERSION = re.compile(r'\d+(?:\.\d+){1,3}\Z')


def evaluate(*, pg_major, table_bytes, disk_usage, current_backup,
             has_primary_key, extension_version, client_available,
             wal_bytes_observed):
    """Feasibility only, never execution authorization.

    Render docs require free space GREATER THAN twice the total table size
    for pg_repack. This adds a separate fixed 120MB reserve, but still cannot
    prove live WAL/scratch write peaks. Final outcome is ALWAYS blocked.
    """
    safe_inputs = (type(pg_major) is int and pg_major >= 16
        and type(table_bytes) is int and 0 < table_bytes <= MAX_TABLE_BYTES
        and type(disk_usage) is int and 0 < disk_usage < ALLOCATION_BYTES)
    spare = ALLOCATION_BYTES-disk_usage if safe_inputs else None
    after_copy = (spare-2*table_bytes) if safe_inputs else None
    capacity = (safe_inputs and disk_usage <= MAX_VOLUME_BYTES
                and after_copy > MIN_RESERVE_BYTES)
    support = (type(extension_version) is str
               and bool(VERSION.fullmatch(extension_version)))
    return {
        'status': 'not-authorized-readonly-assessment',
        'table': TARGET,
        'postgresVersionSupported': type(pg_major) is int and pg_major >= 16,
        'tableBytes': table_bytes if safe_inputs else None,
        'physicalVolumeBytes': disk_usage if safe_inputs else None,
        'estimatedHeadroomAfterTwoCopies': after_copy,
        'conservativeCapacityThresholdMet': bool(capacity),
        'freshIndependentBackupProof': current_backup is True,
        'primaryKeyPresent': has_primary_key is True,
        'pgRepackExtensionInstalled': support,
        'pgRepackClientFound': client_available is True,
        'walSpaceIndependentlyObserved': wal_bytes_observed is True,
        'readyToExecute': False,
        'requiresMaintenanceApproval': True,
        'requiresIndependentActualWALScratchAndLockBudget': True,
        'readOnly': True,
        'productionRowsModified': False,
        'deletionAuthorized': False,
        'diskBytesFreed': None,
    }


def inspect_live():
    """Short private SELECTs and provider volume metadata only."""
    import psycopg
    import render_disk_metrics
    import archive_worker
    import storage_budget
    from datetime import datetime, timezone
    import time

    if not os.environ.get('DATABASE_URL'):
        raise ValueError('Database not configured')
    with psycopg.connect(
        os.environ['DATABASE_URL'],connect_timeout=8,
        application_name='bob_physical_repack_readonly',
        options='-c default_transaction_read_only=on -c statement_timeout=4000 -c lock_timeout=500') as conn:
        conn.execute("SET LOCAL statement_timeout='4s'")
        pg_major = int(conn.execute(
            "SELECT current_setting('server_version_num')::int/10000").fetchone()[0])
        row = conn.execute("""SELECT pg_total_relation_size('public.bob_improvement_observations'::regclass),
            EXISTS (
                SELECT 1 FROM pg_index i
                JOIN pg_class c ON c.oid=i.indrelid
                WHERE c.oid='public.bob_improvement_observations'::regclass
                  AND i.indisprimary AND i.indisvalid
            )""").fetchone()
        if not row or len(row)!=2:
            raise ValueError('Target relation unavailable')
        ext = conn.execute("""SELECT extversion FROM pg_extension
            WHERE extname='pg_repack'""").fetchone()
        proof = storage_budget.archive_status(conn)
        restore = proof.get('latestVerifiedAttempt',{})
        if not isinstance(restore,dict):
            restore={}
        stamp = restore.get('updatedAt')
        valid_backup = (restore.get('status')=='verified'
                       and restore.get('restoreVerified') is True
                       and restore.get('remoteDownloadVerified') is True
                       and restore.get('evidenceDeleted') is False)
        try:
            date = datetime.fromisoformat(str(stamp).replace('Z','+00:00'))
            valid_backup = valid_backup and date.tzinfo is not None and (
                0 <= (datetime.now(timezone.utc)-date).total_seconds() <= 86400)
        except (ValueError,TypeError,OverflowError):
            valid_backup=False
    volume = render_disk_metrics.report()
    observed=volume.get('observedAt')
    # Stale metrics must never authorize maintenance.
    disk=(volume.get('diskUsage') if
          volume.get('status')=='observed' and
          volume.get('resource')==RESOURCE and volume.get('unit')=='bytes'
          and type(observed) in (int,float)
          and 0 <= time.time()-observed <= 300
          else None)
    result=evaluate(pg_major=pg_major,table_bytes=row[0],disk_usage=disk,
                    current_backup=valid_backup,has_primary_key=row[1],
                    extension_version=ext[0] if ext else None,
                    client_available=shutil.which('pg_repack') is not None,
                    wal_bytes_observed=False)
    return result


def main(argv=None):
    import sys
    args=tuple(sys.argv[1:] if argv is None else argv)
    if args!=('preflight',):
        print('Usage: python -m storage_repack_preflight preflight')
        return 2
    try:
        result=inspect_live()
    except Exception as exc:
        # No SQL, URI, token, original data or hostnames exposed.
        result={'status':'preflight-unavailable','errorType':type(exc).__name__,
                'readOnly':True,'readyToExecute':False,
                'deletionAuthorized':False,'diskBytesFreed':None}
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status']=='not-authorized-readonly-assessment' else 3


if __name__=='__main__':
    raise SystemExit(main())
