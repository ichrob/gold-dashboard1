"""Bounded cold-storage cadence from measured database bytes, not disk free space."""
# Operating targets remain small after a capacity upgrade. Physical rewrite
# gates still use storage_capacity and fresh provider measurements separately.
CAUTION_BYTES = 500_000_000
ACTION_BYTES = 700_000_000

def policy(database_bytes):
    if type(database_bytes) is not int or database_bytes < 0:
        return {'state': 'unknown', 'nextRunSeconds': 3600, 'databaseBytes': None}
    seconds = 300 if database_bytes >= ACTION_BYTES else 900 if database_bytes >= CAUTION_BYTES else 3600
    return {'state': 'action' if seconds == 300 else 'caution' if seconds == 900 else 'normal',
            'nextRunSeconds': seconds, 'databaseBytes': database_bytes}


def observe(conn):
    return policy(conn.execute('SELECT pg_database_size(current_database())').fetchone()[0])


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
    if _proof_state(archive_status(conn), seconds) != 'verified-fresh':
        return {'status': 'backup-proof-not-fresh', 'movedRows': 0}
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
    return None
