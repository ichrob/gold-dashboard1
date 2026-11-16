"""Bounded PostgreSQL observations for the already configured Aiven restore target.

No source rows, SQL texts, credentials or endpoints leave this module. Host RAM
and kernel OOM attribution are deliberately unknown: PostgreSQL statistics do
not measure either. The target session lock is shared with restore checks.
"""
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit

from aiven_readonly_probe import _valid_aiven_uri

TARGET_LOCK_SQL = "SELECT pg_try_advisory_lock(hashtext('bob_restore_target_v1'))"
INTERVAL_SECONDS = 1800
_HISTORY = deque(maxlen=48)
_LOCK = threading.Lock()
_THREAD = None


def configured(env):
    uri = env.get('BOB_ARCHIVE_RESTORE_DATABASE_URL', '')
    if not uri:
        return False
    try:
        parts = urlsplit(uri)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        keys = [key for key, _ in pairs]
        # The existing restore URI carries its CA path and connect timeout.
        # Preserve those for libpq; reject every endpoint/user/options override.
        if len(keys) != len(set(keys)) or any(
                key not in ('sslmode', 'sslrootcert', 'connect_timeout') for key in keys):
            return False
        identity_uri = parts._replace(query=urlencode(
            [(key, value) for key, value in pairs if key == 'sslmode'])).geturl()
        return (_valid_aiven_uri(identity_uri) and
                urlsplit(uri).hostname != urlsplit(env.get('DATABASE_URL', '')).hostname)
    except ValueError:
        return False


def inspect(environ=None, connect=None):
    env = os.environ if environ is None else environ
    result = dict(status='not-configured', observedAt=datetime.now(timezone.utc).isoformat(),
                  readOnly=True, hostMemoryAvailablePercent=None,
                  processMemoryBytes=None, oomCause='unknown')
    if not configured(env):
        return result
    try:
        if connect is None:
            import psycopg
            connect = psycopg.connect
        # Retain stronger existing TLS modes; reject weak modes rather than use
        # libpq's default opportunistic encryption on this remote connection.
        from urllib.parse import parse_qs
        uri = env['BOB_ARCHIVE_RESTORE_DATABASE_URL']
        mode = parse_qs(urlsplit(uri).query).get('sslmode', ['require'])[-1]
        if mode not in ('require', 'verify-ca', 'verify-full'):
            return {**result, 'status': 'invalid-tls-configuration'}
        with connect(uri, connect_timeout=5, sslmode=mode,
                     application_name='bob_aiven_health', autocommit=True,
                     options='-c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250') as conn:
            # Session lock survives transaction boundaries, releases on close.
            if conn.execute(TARGET_LOCK_SQL).fetchone() != (True,):
                return {**result, 'status': 'restore-busy'}
            row = conn.execute("""SELECT pg_postmaster_start_time(),
                pg_database_size(current_database()),
                current_setting('max_connections')::int,
                current_setting('transaction_read_only')""").fetchone()
            if row[3] != 'on':
                return {**result, 'status': 'read-only-not-confirmed', 'readOnly': False}
            activity = conn.execute("""SELECT count(*),
                count(*) FILTER (WHERE backend_type='client backend'),
                count(*) FILTER (WHERE state='active' AND backend_type='client backend'),
                count(*) FILTER (WHERE state='idle in transaction'),
                count(*) FILTER (WHERE state='active' AND backend_type='client backend'
                    AND query_start < now()-interval '60 seconds')
                FROM pg_stat_activity WHERE pid <> pg_backend_pid()""").fetchone()
            stats = conn.execute("""SELECT temp_files,temp_bytes,deadlocks,stats_reset
                FROM pg_stat_database WHERE datname=current_database()""").fetchone()
        return {**result, 'status': 'observed', 'postgresStartedAt': row[0].isoformat(),
                'databaseBytes': row[1], 'maxConnections': row[2],
                'backends': activity[0], 'clientConnections': activity[1],
                'activeClients': activity[2], 'idleTransactions': activity[3],
                'longActiveClients': activity[4], 'tempFiles': stats[0],
                'tempBytes': stats[1], 'deadlocks': stats[2],
                'statsResetAt': stats[3].isoformat() if stats[3] else None}
    except Exception:
        return {**result, 'status': 'observation-failed'}


def _observation_time(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp if stamp.tzinfo is not None else None
    except ValueError:
        return None


def assess(current, previous=None):
    """Only compare counters within the same observed PostgreSQL statistics epoch."""
    findings = []
    if current['status'] != 'observed':
        return findings
    if current['clientConnections'] >= current['maxConnections'] * .75:
        findings.append('connection-pressure')
    if current['idleTransactions']:
        findings.append('idle-transaction')
    if current['longActiveClients']:
        findings.append('long-query')
    if previous and previous.get('status') == 'observed':
        current_at = _observation_time(current.get('observedAt'))
        previous_at = _observation_time(previous.get('observedAt'))
        current_start = _observation_time(current.get('postgresStartedAt'))
        previous_start = _observation_time(previous.get('postgresStartedAt'))
        if (None in (current_at, previous_at, current_start, previous_start)
                or current_at <= previous_at or current_start > current_at
                or previous_start > previous_at):
            return findings
        if current_start != previous_start:
            findings.append('postgres-restarted')
        else:
            reset = _observation_time(current.get('statsResetAt'))
            previous_reset = _observation_time(previous.get('statsResetAt'))
            # Two unknown reset times do not establish a shared statistics epoch.
            if reset is None or reset != previous_reset or reset > previous_at:
                return findings
            # A decreasing/malformed cumulative counter invalidates the comparison.
            for key in ('deadlocks', 'tempBytes', 'tempFiles'):
                before, after = previous.get(key), current.get(key)
                if type(before) is not int or type(after) is not int or not 0 <= before <= after:
                    return findings
            if current['deadlocks'] > previous['deadlocks']:
                findings.append('new-deadlock')
            if current['tempBytes'] > previous['tempBytes']:
                findings.append('temporary-disk-growth')
    return findings


def sample():
    result = inspect()
    with _LOCK:
        result['findings'] = assess(result, _HISTORY[-1] if _HISTORY else None)
        _HISTORY.append(result)
    print('BOB_AIVEN_HEALTH ' + json.dumps(result, sort_keys=True), flush=True)
    return result


def status():
    with _LOCK:
        history = list(_HISTORY)
    return {'enabled': _THREAD is not None, 'intervalSeconds': INTERVAL_SECONDS,
            'historyCapacity': 48, 'samples': history,
            'latest': history[-1] if history else {'status': 'not-observed'},
            'hostMemoryCoverage': 'unavailable', 'automaticRestoreAllowed': False}


def start():
    global _THREAD
    if not configured(os.environ) or os.environ.get('BOB_AIVEN_HEALTH_DISABLED') == '1':
        return
    with _LOCK:
        if _THREAD is not None:
            return
        def work():
            time.sleep(90)
            while True:
                try:
                    sample()
                except Exception:
                    # A telemetry failure cannot stop live trading analysis.
                    print('BOB_AIVEN_HEALTH {"status":"worker-observation-failed"}', flush=True)
                time.sleep(INTERVAL_SECONDS)
        _THREAD = threading.Thread(target=work, name='bob-aiven-health', daemon=True)
        _THREAD.start()
