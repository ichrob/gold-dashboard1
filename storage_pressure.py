"""Conservative cold-storage cadence based on verified physical 5-GB usage.

Logical PostgreSQL size is telemetry, not a reason to archive every five
minutes. In particular, 500/700-MB logical thresholds are retired by #1329.
An unknown or stale Render provider measurement never accelerates offload.
Eligibility and independent recovery/reader proof remain separate gates.
"""
from storage_capacity import CAUTION_BYTES as CAUTION_VOLUME_BYTES
from storage_capacity import ACTION_BYTES as ACTION_VOLUME_BYTES


def policy(database_bytes, volume_bytes=None):
    if type(database_bytes) is not int or database_bytes < 0:
        return {'state': 'unknown', 'nextRunSeconds': 3600,
                'databaseBytes': None, 'volumeBytes': None}
    if type(volume_bytes) is not int or volume_bytes < 0:
        return {'state': 'normal', 'nextRunSeconds': 3600,
                'databaseBytes': database_bytes, 'volumeBytes': None,
                'basis': 'verified-volume-required'}
    seconds = (300 if volume_bytes >= ACTION_VOLUME_BYTES else
               900 if volume_bytes >= CAUTION_VOLUME_BYTES else 3600)
    return {'state': 'action' if seconds == 300 else 'caution' if seconds == 900 else 'normal',
            'nextRunSeconds': seconds, 'databaseBytes': database_bytes,
            'volumeBytes': volume_bytes, 'basis': 'physical-render-volume'}


def observe(conn):
    import time
    from render_disk_metrics import RESOURCE, report
    database_bytes = conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    metric = report()
    observed = metric.get('observedAt')
    if (metric.get('status') == 'observed' and metric.get('resource') == RESOURCE
            and metric.get('unit') == 'bytes'
            and type(observed) in (float, int) and 0 <= time.time()-observed <= 300
            and type(metric.get('diskUsage')) is int and metric['diskUsage'] >= 0):
        return policy(database_bytes, metric['diskUsage'])
    return policy(database_bytes)


def delay(result):
    if result.get('status') == 'archive-running':
        return 60
    # Failures never cause rapid retries. All workers retain their batch/time caps.
    if result.get('status') != 'checked':
        return 3600
    return result.get('pressure', {}).get('nextRunSeconds', 3600)



def verified_writer_preflight(conn, now=None):
    """Read-only, fail-closed gate before any automatic cold-payload replacement.

    The full original remains SQL-local until a fresh reviewed-evidence
    independent restore AND recovery key check are persisted. A separate
    fresh provider disk measurement must leave the existing WAL/scratch
    headroom; logical pg_database_size never substitutes for volume usage.
    """
    import time
    from storage_budget import archive_status
    from cold_decision_product_writer import _proof_state
    from storage_capacity import MAX_VOLUME_BYTES
    import render_disk_metrics

    seconds = time.time() if now is None else now
    # Check capacity before expensive archive-credential/proof work. With
    # comfortable physical headroom, no writer proceeds even if the most
    # recent independent recovery receipt has aged out.
    volume = render_disk_metrics.report()
    observed = volume.get('observedAt')
    if (volume.get('status') != 'observed' or
            volume.get('resource') != render_disk_metrics.RESOURCE or
            volume.get('unit') != 'bytes' or
            type(observed) not in (int, float) or
            not 0 <= seconds - observed <= 300 or
            type(volume.get('diskUsage')) is not int or
            volume['diskUsage'] > MAX_VOLUME_BYTES):
        return {'status': 'fresh-volume-proof-unavailable', 'movedRows': 0}
    # Below half the actual 5-GB volume, do not replace any original
    # payload merely to meet a historical small-DB operating target.
    # Continue independent backup receipts and fixed capacity monitoring.
    if volume['diskUsage'] < CAUTION_VOLUME_BYTES:
        return {'status': 'capacity-comfortable-no-offload', 'movedRows': 0}
    if _proof_state(archive_status(conn), seconds) != 'verified-fresh':
        return {'status': 'backup-proof-not-fresh', 'movedRows': 0}
    return None
