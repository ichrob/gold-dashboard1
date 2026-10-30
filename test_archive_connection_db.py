"""Isolated CI Postgres: encrypted persistence and consume-before-network proof."""
import os
import secrets
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import archive_connection as c
from test_archive_connection import CONFIG, BINDING

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class ArchiveConnectionDatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.pg=psycopg;self.dsn=os.environ['BOB_TEST_DATABASE_URL'];self.schema='archive_connection_test_'+secrets.token_hex(8)
        self.secret=patch.dict(os.environ,PUSH_SERVICE_TOKEN='isolated-ci-test-key');self.secret.start()
        with self.pg.connect(self.dsn) as conn:
            conn.execute('CREATE SCHEMA '+self.schema)
            conn.execute('CREATE TABLE '+self.schema+'.bob_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        self.call('configure',config=CONFIG)
    def tearDown(self):
        self.secret.stop()
        with self.pg.connect(self.dsn) as conn:conn.execute('DROP SCHEMA '+self.schema+' CASCADE')
    def call(self,action,**fields):
        with self.pg.connect(self.dsn) as conn:
            conn.execute('SET search_path TO '+self.schema)
            return c.handle(conn,action,dict(binding=BINDING,**fields))
    def test_failed_exchange_consumed_across_restart_and_secret_encrypted(self):
        nonce=parse_qs(urlparse(self.call('begin')['url']).query)['state'][0]
        with patch.object(c,'exchange',side_effect=OSError('private provider response')) as exchange:
            with self.assertRaises(OSError):self.call('complete',state=nonce,code='test-code')
            with self.assertRaises(ValueError):self.call('complete',state=nonce,code='test-code')
            self.assertEqual(exchange.call_count,1)
        with self.pg.connect(self.dsn) as conn:
            row=conn.execute('SELECT value FROM '+self.schema+'.bob_settings').fetchone()[0]
            self.assertNotIn('test-secret',row);self.assertNotIn('test-code',row)
    def test_success_never_enables_worker_or_exposes_refresh_token(self):
        nonce=parse_qs(urlparse(self.call('begin')['url']).query)['state'][0]
        with patch.object(c,'exchange',return_value={'refresh_token':'private-refresh-token'}):
            result=self.call('complete',state=nonce,code='test-code')
        self.assertTrue(result['connected']);self.assertFalse(result['archiveEnabled'])
        status=self.call('status');self.assertTrue(status['connected']);self.assertNotIn('token',str(status))
        with self.assertRaises(ValueError):self.call('configure',config=CONFIG)
