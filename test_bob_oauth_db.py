"""Run against isolated CI PostgreSQL, never production connection settings."""
import os
import secrets
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
import bob_oauth_store as store


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class OAuthDatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.psycopg = psycopg
        self.dsn = os.environ['BOB_TEST_DATABASE_URL']
        self.schema = 'oauth_test_'+secrets.token_hex(8)
        self.account = 'b'*64
        with psycopg.connect(self.dsn) as conn:
            conn.execute('CREATE SCHEMA '+self.schema)
            conn.execute('SET search_path TO '+self.schema)
            store.init(conn)

    def tearDown(self):
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute('DROP SCHEMA '+self.schema+' CASCADE')

    def call(self,action,**fields):
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute('SET search_path TO '+self.schema)
            return store.handle(conn,action,{'account':self.account,**fields})

    def test_reconnect_atomic_exchange_rotation_and_revocation(self):
        cid = self.call('register',redirect_uris=[store.REDIRECT])['client_id']
        verifier = 'v'*43
        req = self.call('begin',client_id=cid,redirect_uri=store.REDIRECT,response_type='code',
            scope=store.SCOPE,resource=store.RESOURCE,state='test',code_challenge=store.challenge(verifier),
            code_challenge_method='S256')['request']
        code = self.call('approve',request=req,until=time.time()+86400)['code']
        fields = dict(grant_type='authorization_code',client_id=cid,redirect_uri=store.REDIRECT,
                      code=code,code_verifier=verifier,resource=store.RESOURCE)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:self.call('token',**fields),range(2)))
        tokens = [r for r in results if 'access_token' in r]
        self.assertEqual(len(tokens),1)
        # A replay revokes even the winning transaction's grant.
        self.assertFalse(self.call('check',token=tokens[0]['access_token'])['valid'])
        self.call('revoke-all')
        self.assertEqual(self.call('list')['grants'],[])

