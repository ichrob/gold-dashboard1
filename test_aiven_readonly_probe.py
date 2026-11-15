import tempfile
import unittest
from pathlib import Path
from aiven_readonly_probe import _valid_aiven_uri, probe

URI = 'postgresql://avnadmin:SECRET@pg-testing.example.aivencloud.com:12345/defaultdb?sslmode=require'


class FakeCursor:
    def __init__(self, read_only='on'):
        self.read_only = read_only
        self.last_query = None
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query):
        self.last_query = query
        self.calls.append(query)

    def fetchone(self):
        return (self.read_only if 'transaction_read_only' in self.last_query else 1,)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def cursor(self):
        return self._cursor


class AivenProbeTests(unittest.TestCase):
    def test_missing_configuration_is_not_reported_as_connected(self):
        self.assertEqual(probe({})['status'], 'not-configured')

    def test_rejects_production_or_redirected_uris(self):
        self.assertFalse(_valid_aiven_uri('postgresql://u:p@db.render.com:5432/x'))
        self.assertFalse(_valid_aiven_uri(URI + '&host=production.example.org'))
        self.assertFalse(_valid_aiven_uri(URI + '&hostaddr=127.0.0.1'))
        self.assertTrue(_valid_aiven_uri(URI))

    def test_single_short_verified_read_only_session(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory, 'ca.pem')
            ca.write_text('fake cert for injected connector test')
            cursor = FakeCursor()
            connection = FakeConnection(cursor)
            invocations = []

            def connect(*args, **kwargs):
                invocations.append((args, kwargs))
                return connection

            result = probe({'BOB_AIVEN_TEST_DATABASE_URL': URI,
                            'BOB_AIVEN_TEST_CA_FILE': str(ca)}, connect)
            self.assertEqual(result['status'], 'connected-read-only')
            self.assertTrue(connection.closed)
            self.assertEqual(len(invocations), 1)
            self.assertEqual(invocations[0][1]['sslmode'], 'verify-full')
            self.assertEqual(invocations[0][1]['connect_timeout'], 5)
            self.assertEqual(cursor.calls, ['BEGIN READ ONLY',
                                            "SELECT current_setting('transaction_read_only')", 'SELECT 1'])

    def test_failed_connection_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory, 'ca.pem')
            ca.write_text('fixture')

            def failing(*args, **kwargs):
                raise RuntimeError('password SECRET at pg-testing.example.aivencloud.com')

            result = probe({'BOB_AIVEN_TEST_DATABASE_URL': URI,
                            'BOB_AIVEN_TEST_CA_FILE': str(ca)}, failing)
            self.assertEqual(result['status'], 'connection-not-confirmed')
            self.assertNotIn('SECRET', str(result))
            self.assertNotIn('aivencloud.com', str(result))

    def test_inline_render_pem_is_not_exposed_or_persisted(self):
        pem = '-----BEGIN CERTIFICATE-----\nQUJDRA==\n-----END CERTIFICATE-----'
        with tempfile.TemporaryDirectory() as ignored:
            paths = []
            def connect(*args, **kwargs):
                cert_path = Path(kwargs['sslrootcert'])
                paths.append(cert_path)
                self.assertEqual(cert_path.read_text(), pem + '\n')
                self.assertEqual(cert_path.stat().st_mode & 0o077, 0)
                return FakeConnection(FakeCursor())
            result = probe({'BOB_AIVEN_TEST_DATABASE_URL': URI,
                            'BOB_AIVEN_TEST_CA_PEM': pem}, connect)
            self.assertEqual(result, {'status': 'connected-read-only', 'readOnly': True})
            self.assertFalse(paths[0].exists())

    def test_malformed_inline_pem_rejected(self):
        self.assertEqual(probe({'BOB_AIVEN_TEST_DATABASE_URL': URI,
                                'BOB_AIVEN_TEST_CA_PEM': 'BAD CERTIFICATE'})['status'],
                         'invalid-configuration')

    def test_read_only_must_be_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            ca = Path(directory, 'ca.pem')
            ca.write_text('fixture')
            result = probe({'BOB_AIVEN_TEST_DATABASE_URL': URI,
                            'BOB_AIVEN_TEST_CA_FILE': str(ca)},
                           lambda *_a, **_kw: FakeConnection(FakeCursor('off')))
            self.assertEqual(result['status'], 'read-only-not-confirmed')
            self.assertFalse(result['readOnly'])


if __name__ == '__main__':
    unittest.main()
