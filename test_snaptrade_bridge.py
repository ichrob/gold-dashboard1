import base64
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
from urllib.parse import urlsplit
import snaptrade_bridge as b
import snaptrade_settings as settings

C = '11111111-1111-4111-8111-111111111111'
A = '22222222-2222-4222-8222-222222222222'
CONFIG = {'clientId': 'test-client', 'consumerKey': 'test-consumer-key', 'personalFreeConfirmed': True}


def fixtures():
    at = datetime.now(timezone.utc).isoformat()
    return {'/authorizations': [{'id': C, 'brokerage': {'slug': 'DEGIRO'}, 'disabled': False,
                                'type': 'read', 'data_freshness_mode': {'institution': 'realtime', 'snaptrade': 'realtime'}}],
            '/connections/' + C + '/accounts': {'results': [{'id': A, 'connection_id': C, 'kind': 'investment'}]},
            '/accounts/' + A + '/positions/all': {'results': [{'instrument': {'kind': 'other', 'symbol': 'UNVERIFIED', 'description': '<img src=x onerror=alert(1)>'},
                                                               'units': '2.5', 'currency': 'CHF', 'price': '8.0'}], 'data_freshness': {'as_of': at}},
            '/accounts/' + A + '/balances/v2': {'account_id': A, 'cash': [{'amount': '12.34', 'currency': 'CHF'}], 'data_freshness': {'as_of': at}}}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.saved = (b._CONFIG, b._LOADED, b._GENERATION, b._NEXT, copy.deepcopy(b._STATE))
        b._CONFIG, b._LOADED, b._NEXT = None, True, 0
        b._STATE.clear(); b._STATE.update(code='SETUP_REQUIRED', snapshot=None)

    def tearDown(self):
        b._CONFIG, b._LOADED, b._GENERATION, b._NEXT, state = self.saved
        b._STATE.clear(); b._STATE.update(state)

    def test_configuration_encrypted_persistent_and_erased(self):
        db = {}
        def storage(action, payload=None):
            if action == 'save': db.update(payload); return {'saved': True}
            if action == 'delete': db.clear(); return {'deleted': True}
            return dict(db)
        with patch.dict(os.environ, PUSH_SERVICE_TOKEN='local-test-encryption-key'), patch.object(b, 'storage', side_effect=storage), patch.object(b, 'start'):
            result = b.configure(CONFIG)
            serialized = json.dumps(result)
            for secret in ('test-client', 'test-consumer-key'):
                self.assertNotIn(secret, serialized); self.assertNotIn(secret, db['sealed'])
            b._CONFIG, b._LOADED = None, False
            b.load_config(); self.assertEqual(b._CONFIG, CONFIG)
            b.disconnect(); self.assertFalse(db); self.assertFalse(b.status()['configured'])

    def test_missing_encryption_fails_closed_before_storage(self):
        with patch.dict('sys.modules', {'cryptography.fernet': None}), patch.object(b, 'storage') as store:
            with self.assertRaises(b.ReadError) as error:
                b.configure(CONFIG)
            self.assertEqual(error.exception.code, 'CRYPTO_UNAVAILABLE')
            store.assert_not_called()
            self.assertFalse(b.status()['configured'])
            self.assertFalse(b.diagnostics()['encryptionReady'])

    def test_no_unconfirmed_or_broker_credentials(self):
        for payload in ({**CONFIG, 'personalFreeConfirmed': False}, {**CONFIG, 'otp': '123456'}, {**CONFIG, 'password': 'secret'}):
            with self.assertRaises(ValueError): b.validate_config(payload)
        self.assertFalse(b.status()['realOrders'])

    def test_exact_signed_get_only_allowlist_and_no_user_secret(self):
        response = Mock(); response.read.return_value = b'[]'
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        opener = Mock(); opener.open.return_value = response
        with patch.object(b, 'build_opener', return_value=opener), patch.object(b.time, 'time', return_value=1700000000):
            self.assertEqual(b.api_get('/authorizations', CONFIG), [])
            request = opener.open.call_args.args[0]
            self.assertEqual(request.method, 'GET')
            self.assertEqual(urlsplit(request.full_url).netloc, 'api.snaptrade.com')
            self.assertEqual(urlsplit(request.full_url).query, 'clientId=test-client&timestamp=1700000000')
            expected = base64.b64encode(hmac.new(CONFIG['consumerKey'].encode(), b'{"content":null,"path":"/authorizations","query":"clientId=test-client&timestamp=1700000000"}', hashlib.sha256).digest()).decode()
            self.assertEqual(request.get_header('Signature'), expected)
            self.assertNotIn('userSecret', request.full_url)
            for path in ('/orders', '/authorizations/' + C + '/refresh', '//evil.test/x', '/accounts/' + A + '/orders/place', '/authorizations?evil=x'):
                with self.assertRaises(b.ReadError): b.api_get(path, CONFIG)
            self.assertEqual(opener.open.call_count, 1)
        self.assertIsNone(b.NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_current_data_is_not_product_approval_or_execution_quote(self):
        data = fixtures()
        snap = b.read_snapshot(CONFIG, lambda path, _: data[path])
        b._CONFIG = CONFIG; b._STATE.update(code='READ_OK', snapshot=snap)
        self.assertTrue(b.status()['fresh'])
        self.assertFalse(snap['realOrders']); self.assertFalse(snap['liveQuotes'])
        row = snap['accounts'][0]['positions'][0]
        self.assertIsNone(row['isin']); self.assertFalse(row['tradeApproved'])
        self.assertEqual(row['units'], '2.5')
        snap['accounts'][0]['positionsSourceAt'] = None
        self.assertFalse(b.status()['fresh'])

    def test_disabled_connections_never_read_cached_holdings_as_live(self):
        data = fixtures(); data['/authorizations'][0]['disabled'] = True
        calls = []
        def get(path, _): calls.append(path); return data[path]
        with self.assertRaises(b.ReadError) as e: b.read_snapshot(CONFIG, get)
        self.assertEqual(e.exception.code, 'AUTH_REQUIRED'); self.assertEqual(calls, ['/authorizations'])

    def test_unrelated_broker_not_imported_and_trade_permission_rejected(self):
        data = fixtures(); data['/authorizations'][0]['brokerage']['slug'] = 'OTHER'
        with self.assertRaises(b.ReadError) as e: b.read_snapshot(CONFIG, lambda path, _: data[path])
        self.assertEqual(e.exception.code, 'CONNECT_DEGIRO')
        data = fixtures(); data['/authorizations'][0]['type'] = 'trade'
        with self.assertRaises(b.ReadError) as e: b.read_snapshot(CONFIG, lambda path, _: data[path])
        self.assertEqual(e.exception.code, 'READ_CONNECTION_REQUIRED')

    def test_invalid_partial_snapshot_keeps_previous_and_cooldown(self):
        b._CONFIG = CONFIG; old = {'preserve': True}; b._STATE.update(snapshot=old)
        with patch.object(b, 'read_snapshot', side_effect=b.ReadError('INVALID_RESPONSE')) as read:
            b.refresh(); b.refresh(); read.assert_called_once()
        self.assertEqual(b._STATE['snapshot'], old); self.assertFalse(b.status()['fresh'])

    def test_concurrent_disconnect_drops_inflight_result(self):
        b._CONFIG = CONFIG
        def delayed(_):
            b._GENERATION += 1; b._CONFIG = None; b._STATE.update(code='SETUP_REQUIRED', snapshot=None)
            return {'accounts': [], 'completeConnections': True}
        with patch.object(b, 'read_snapshot', side_effect=delayed): b.refresh()
        self.assertIsNone(b.status()['snapshot']); self.assertFalse(b.status()['configured'])

    def test_private_reconciliation_diagnostics_are_counters_only(self):
        b._STATE.update(code='READ_OK', snapshot={
            'completeConnections':False,
            'accounts':[{
                'positions':[],
                'tradeInsights':{'reconciliation':{
                    'status':'available','candidatePairs':1,'ambiguousGroups':2,
                    'orderFillsWithoutExactActivity':3,
                    'activityTradesWithoutExactOrder':4, 'missingEvidence':5,
                    'accountHistoryComplete':False,
                    'pairs':[{'isin':'DE000FG309G0','secret':'NEVER_EXPOSE',
                              'price':'12.34','reportedActivityFee':'5.12'}]
                }}
            }]
        })
        report=b.diagnostics()
        self.assertEqual(report['executionReconciliation'][0]['candidatePairs'],1)
        self.assertEqual(report['executionReconciliation'][0]['ambiguousGroups'],2)
        self.assertEqual(report['executionReconciliation'][0]['missingOrderEvidence'],5)
        self.assertFalse(report['executionReconciliation'][0]['netProfitVerified'])
        self.assertFalse(report['executionReconciliation'][0]['learningEligible'])
        self.assertNotIn('DE000FG309G0',json.dumps(report))
        self.assertNotIn('NEVER_EXPOSE',json.dumps(report))
        self.assertNotIn('12.34',json.dumps(report))

    def test_quality_diagnostics_exclude_private_values(self):
        b._STATE.update(code='READ_OK',snapshot={'completeConnections':False,
            'accounts':[{'positions':[], 'journal':{},
               'evidenceQuality':{'orderRows':2,'privateName':'DO_NOT_EXPOSE'},
               'profitReadiness':{'netProfitVerified':False,'amount':'SECRET_VALUE'}}]})
        report=b.diagnostics()
        self.assertEqual(report['evidenceGaps'][0]['orderRows'],2)
        self.assertFalse(report['profitReadiness'][0]['netProfitVerified'])
        self.assertNotIn('DO_NOT_EXPOSE',json.dumps(report))
        self.assertNotIn('SECRET_VALUE',json.dumps(report))
        self.assertEqual(report['connectionWatch']['pushesSent'],0)
        self.assertEqual(report['connectionWatch']['emailsSent'],0)

    def test_errors_are_sanitized_and_not_retried_in_a_loop(self):
        opener = Mock(); opener.open.side_effect = HTTPError('https://private?secret=DO_NOT_ECHO', 429, 'DO_NOT_ECHO', {'Retry-After': '3600'}, None)
        with patch.object(b, 'build_opener', return_value=opener):
            with self.assertRaises(b.ReadError) as e: b.api_get('/authorizations', CONFIG)
        self.assertEqual(e.exception.code, 'RATE_LIMITED'); self.assertNotIn('DO_NOT_ECHO', str(e.exception))
        self.assertEqual(e.exception.retry_after, 3600)
        opener.open.assert_called_once()
        b._CONFIG = CONFIG
        with patch.object(b, 'read_snapshot', side_effect=b.ReadError('RATE_LIMITED', 3600)):
            b.refresh()
        self.assertGreaterEqual(b.status()['nextCheckSeconds'], 3599)

    def test_invalid_numbers_and_future_timestamps_remain_unknown(self):
        for value in (True, 'NaN', 'Infinity', None): self.assertIsNone(b.number(value))
        for value in ('2026-01-01', '9999-01-01T00:00:00Z', 'not a time'): self.assertIsNone(b.source_time(value))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'PostgreSQL integration in CI')
class SettingsPersistenceTest(unittest.TestCase):
    def test_only_ciphertext_is_saved_loaded_deleted(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            with patch.dict(os.environ, PUSH_SERVICE_TOKEN='test-only'):
                sealed = b.cipher().encrypt(json.dumps(CONFIG).encode()).decode()
                settings.handle(conn, 'save', {'sealed': sealed})
                loaded = settings.handle(conn, 'read', {})['sealed']
                self.assertEqual(json.loads(b.cipher().decrypt(loaded.encode())), CONFIG)
                self.assertNotIn(CONFIG['consumerKey'], loaded)
                settings.handle(conn, 'state-save', {'sealed': sealed})
                self.assertEqual(settings.handle(conn, 'state-read', {})['sealed'], sealed)
                settings.handle(conn, 'delete', {})
                self.assertIsNone(settings.handle(conn, 'state-read', {})['sealed'])
                self.assertIsNone(settings.handle(conn, 'read', {})['sealed'])


if __name__ == '__main__': unittest.main()
