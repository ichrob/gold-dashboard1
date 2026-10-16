"""Regression: recover stored DEGIRO email bodies without sending any mail."""
import unittest
from unittest.mock import patch

import agentmail_receipt_recovery as recovery
from test_trade_document_import import TEXT


class MailRecoveryTests(unittest.TestCase):
    def test_authenticated_inbox_recovery_is_scoped_and_idempotent(self):
        mid="<test-confirmation@example.test>"
        def fake_get(url,key,cap):
            self.assertEqual(key,'test-token-secure')
            self.assertTrue(url.startswith(recovery.BASE))
            if "?" in url:
                return {"messages":[
                    {"inbox_id":recovery.INBOX,"message_id":mid,"labels":["received"],
                     "subject":"DEGIRO - Transaktionsbestätigung: Kauf"},
                    {"inbox_id":"other@agentmail.to","message_id":"other",
                     "labels":["received"],"subject":"DEGIRO"},
                    {"inbox_id":recovery.INBOX,"message_id":"sent",
                     "labels":["sent"],"subject":"DEGIRO"},
                    {"inbox_id":recovery.INBOX,"message_id":mid,"labels":["received"],
                     "subject":"DEGIRO"}]}
            return {"inbox_id":recovery.INBOX,"message_id":mid,
                "from":"DEGIRO <notifications@degiro.com>",
                "subject":"DEGIRO - Transaktionsbestätigung: Kauf",
                "html":'<div>DEGIRO</div><div>'+TEXT.replace('\n','<br>')+'</div>'}
        items=recovery.recover('test-token-secure','customer@example.test',fake_get)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['messageId'],mid)
        self.assertEqual(items[0]['record']['status'],'pending-review')
        self.assertEqual(items[0]['record']['totalChf'],6.04)
        self.assertEqual(items[0]['record']['senderKind'],'original-degiro-unverified')
        self.assertNotIn('html',str(items))

    def test_unconfigured_skip_network(self):
        def fail(*args):
            raise AssertionError('No unconfigured external traffic')
        self.assertEqual(recovery.recover('', 'user@example.test',fail),[])
        self.assertEqual(recovery.recover('test-token-secure', '',fail),[])

    def test_request_cannot_switch_to_another_inbox(self):
        with self.assertRaises(ValueError):
            recovery.api_json('https://other.example/v0/inboxes/other/messages',
                              'test-token-secure',1000)


if __name__=="__main__":
    unittest.main()
