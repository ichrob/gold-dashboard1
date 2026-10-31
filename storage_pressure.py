"""Bounded cold-storage cadence from measured database bytes, not disk free space."""
def policy(database_bytes):
    if type(database_bytes) is not int or database_bytes < 0:
        return {'state': 'unknown', 'nextRunSeconds': 3600, 'databaseBytes': None}
    seconds = 300 if database_bytes >= 700_000_000 else 900 if database_bytes >= 500_000_000 else 3600
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
