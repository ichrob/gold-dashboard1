"""Signed browser notification receipt: no OS display inferred and no token leaks."""
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import push_receipt
import push_server
import push_delivery_history
import diagnostic_history


class PushDeviceReceiptTests(unittest.TestCase):
    def test_proof_is_scoped_and_expires(self):
        issued = push_receipt.issue('private-secret', now=1000)
        self.assertEqual(set(issued), {'receiptId', 'receiptExpiry', 'receiptProof'})
        for state in ('show-resolved', 'clicked'):
            self.assertEqual(
                push_receipt.verify({**issued, 'receiptState': state},
                                    'private-secret', now=1001),
                (issued['receiptId'], state))
        for change in (
            {'receiptState': 'user-saw-screen'},
            {'receiptExpiry': issued['receiptExpiry'] + 1},
            {'receiptProof': '0' * 64},
            {'receiptId': 'f' * 32},
            {'receiptExpiry': True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                push_receipt.verify({**issued, 'receiptState': 'show-resolved', **change},
                                    'private-secret', now=1001)
        with self.assertRaises(ValueError):
            push_receipt.verify({**issued, 'receiptState': 'show-resolved'},
                                'private-secret', now=1000 + push_receipt.MAX_AGE + 1)
        with self.assertRaises(ValueError):
            push_receipt.verify({**issued, 'receiptState': 'clicked', 'endpoint': 'SECRET'},
                                'private-secret', now=1001)
        self.assertEqual(push_receipt.event_id(issued['receiptId'], 'clicked'),
                         push_receipt.event_id(issued['receiptId'], 'clicked'))
        self.assertNotEqual(push_receipt.event_id(issued['receiptId'], 'clicked'),
                            push_receipt.event_id(issued['receiptId'], 'show-resolved'))

    def test_gateway_adds_unique_proof_without_journaling_secret(self):
        sent = []
        def provider(**kwargs):
            sent.append(json.loads(kwargs['data']))
            return SimpleNamespace(status_code=201)
        msg = {'title': 'PRIVATE TITLE', 'body': 'PRIVATE BODY',
               'data': {'eventKind': 'early-warning', 'direction': 'LONG',
                        'test': False, 'dataAt': 1793004614000}}
        with patch.object(push_server, 'PUSH_SERVICE_TOKEN', 'private-secret'), \
             patch.object(push_server, '_webpush', side_effect=provider), \
             patch.object(push_server.diagnostic_history, 'emit') as emit:
            for _ in range(2):
                push_server.webpush(data=json.dumps(msg),
                    subscription_info={'endpoint': 'PRIVATE ENDPOINT'})
        self.assertEqual(len(sent), 2)
        self.assertNotEqual(sent[0]['data']['receiptId'], sent[1]['data']['receiptId'])
        for call, sent_msg in zip(emit.call_args_list, sent):
            payload = call.args[2]
            self.assertEqual(payload['outcome'], 'provider-accepted')
            self.assertEqual(payload['receiptId'], sent_msg['data']['receiptId'])
            self.assertNotIn('receiptProof', str(payload))
            self.assertNotIn('PRIVATE', str(payload))
            self.assertNotIn('endpoint', str(payload))
        self.assertNotEqual(sent[0]['data']['receiptProof'], 'private-secret')

    def test_journal_projection_does_not_include_signed_proof(self):
        schema = diagnostic_history.SCHEMAS['push-delivery']
        from bob_diagnostics import project
        projected = project({
            'outcome': 'browser-receipt', 'receiptId': 'a'*32,
            'receiptState': 'clicked', 'receiptProof': 'PRIVATE KEY',
            'endpoint': 'PRIVATE ENDPOINT'}, schema)
        self.assertEqual(projected['receiptState'], 'clicked')
        self.assertNotIn('receiptProof', projected)
        self.assertNotIn('endpoint', projected)

    def test_two_independent_browser_states_not_conflated(self):
        at = datetime(2026, 10, 26, 8, 50, tzinfo=timezone.utc)
        rid = 'a'*32
        conn = Mock()
        provider_row = ('provider-id', at, {
            'outcome': 'provider-accepted', 'httpStatus': 201,
            'direction': 'LONG', 'receiptId': rid, 'test': False,
            'synthetic': False, 'body': 'PRIVATE'})
        conn.execute.side_effect = [
            SimpleNamespace(fetchall=lambda: [provider_row]),
            SimpleNamespace(fetchall=lambda: [(rid, 'show-resolved', at)])
        ]
        value = push_delivery_history.report(conn)
        record = value['records'][0]
        self.assertEqual(record['browserShowReceipt'], 'confirmed')
        self.assertEqual(record['handsetReceipt'], 'not-verified')
        self.assertIs(record['marketEventVerified'], False)
        self.assertNotIn(rid, str(value))
        self.assertNotIn('PRIVATE', str(value))
        self.assertEqual(conn.execute.call_count, 2)

        conn2 = Mock()
        conn2.execute.side_effect = [
            SimpleNamespace(fetchall=lambda: [provider_row]),
            SimpleNamespace(fetchall=lambda: [(rid, 'clicked', at)])
        ]
        clicked = push_delivery_history.report(conn2)['records'][0]
        self.assertEqual(clicked['handsetReceipt'], 'notification-click-confirmed')
        self.assertEqual(clicked['browserShowReceipt'], 'inferred-from-click')
        self.assertIs(clicked['marketEventVerified'], False)

    def test_no_browser_row_does_not_prove_missing_push(self):
        at = datetime(2026, 10, 26, 8, 50, tzinfo=timezone.utc)
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [
            ('old', at, {'outcome': 'provider-accepted', 'httpStatus': 201})]
        rec = push_delivery_history.report(conn)['records'][0]
        self.assertEqual(rec['handsetReceipt'], 'not-verified')
        self.assertEqual(rec['browserShowReceipt'], 'not-verified')
        self.assertEqual(conn.execute.call_count, 1)


if __name__ == '__main__':
    unittest.main()
