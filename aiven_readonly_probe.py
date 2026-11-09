"""Opt-in, single-connection Aiven PostgreSQL canary; no production fallback.

Nothing imports or runs this probe in Bob's live services. Credentials are read
only from an operator-managed environment variable and never logged. It performs
only fixed read-only SQL and returns status codes without exception messages.
"""
import json
import os
import tempfile
from contextlib import contextmanager, nullcontext
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


@contextmanager
def _temporary_ca_certificate(pem):
    # PEM is handled only inside the process; 0600 file removed on exit.
    with tempfile.TemporaryDirectory(prefix='bob-aiven-ca-') as directory:
        path = Path(directory) / 'ca.pem'
        path.write_text(pem, encoding='ascii')
        path.chmod(0o600)
        yield str(path)


def probe(environ=None, connect=None):
    """Return a bounded, secret-free status; never accept arbitrary SQL."""
    env = os.environ if environ is None else environ
    uri = env.get('BOB_AIVEN_TEST_DATABASE_URL', '')
    pem = env.get('BOB_AIVEN_TEST_CA_PEM', '').strip()
    root = env.get('BOB_AIVEN_TEST_CA_FILE', '') or '/etc/secrets/bob_aiven_ca.pem'
    if not uri or not (pem or Path(root).is_file()):
        return {'status': 'not-configured', 'readOnly': True}
    if not _valid_aiven_uri(uri):
        return {'status': 'invalid-configuration', 'readOnly': True}
    # A full PEM can be entered as a second Render environment variable.
    if pem and (len(pem) > 32768 or not pem.startswith('-----BEGIN CERTIFICATE-----')
                or not pem.endswith('-----END CERTIFICATE-----')):
        return {'status': 'invalid-configuration', 'readOnly': True}
    try:
        if connect is None:
            import psycopg
            connect = psycopg.connect
        ca = _temporary_ca_certificate(pem + '\\n') if pem else nullcontext(root)
        # Explicit settings override a weaker sslmode=require in Aiven's URI.
        with ca as ca_path:
            with connect(uri, sslmode='verify-full', sslrootcert=ca_path,
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
