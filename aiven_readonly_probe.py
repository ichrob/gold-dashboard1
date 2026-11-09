"""Opt-in, single-connection Aiven PostgreSQL canary; no production fallback.

Nothing imports or runs this probe in Bob's live services. Credentials are read
only from an operator-managed environment variable and never logged. It performs
only fixed read-only SQL and returns status codes without exception messages.
"""
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


def _valid_aiven_uri(uri):
    try:
        parts = urlsplit(uri)
        # Reject libpq query overrides which could silently redirect the target.
        parameters = [key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)]
        return (parts.scheme in ('postgres', 'postgresql')
                and bool(parts.hostname)
                and parts.hostname.endswith('.aivencloud.com')
                and bool(parts.port)
                and bool(parts.username) and bool(parts.password)
                and not parts.fragment
                and all(key == 'sslmode' for key in parameters))
    except (ValueError, TypeError):
        return False


def probe(environ=None, connect=None):
    """Return a bounded, secret-free status; never accept arbitrary SQL."""
    env = os.environ if environ is None else environ
    uri = env.get('BOB_AIVEN_TEST_DATABASE_URL', '')
    root = env.get('BOB_AIVEN_TEST_CA_FILE', '')
    if not uri or not root:
        return {'status': 'not-configured', 'readOnly': True}
    if not _valid_aiven_uri(uri) or not Path(root).is_file():
        return {'status': 'invalid-configuration', 'readOnly': True}
    try:
        if connect is None:
            import psycopg
            connect = psycopg.connect
        # Explicit settings override a weaker sslmode=require in Aiven's URI.
        with connect(uri, sslmode='verify-full', sslrootcert=root,
                     connect_timeout=5, autocommit=True,
                     application_name='bob_aiven_test_read_only',
                     options='-c default_transaction_read_only=on -c statement_timeout=1500') as conn:
            with conn.cursor() as cursor:
                cursor.execute('BEGIN READ ONLY')
                cursor.execute("SELECT current_setting('transaction_read_only')")
                if cursor.fetchone()[0] != 'on':
                    return {'status': 'read-only-not-confirmed', 'readOnly': False}
                cursor.execute('SELECT 1')
                if cursor.fetchone()[0] != 1:
                    return {'status': 'query-not-confirmed', 'readOnly': True}
        return {'status': 'connected-read-only', 'readOnly': True}
    except Exception:
        # libpq/psycopg exception strings can contain endpoints and credentials.
        return {'status': 'connection-not-confirmed', 'readOnly': True}


def main():
    result = probe()
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'connected-read-only' else 2


if __name__ == '__main__':
    raise SystemExit(main())
