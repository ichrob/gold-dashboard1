"""A browser acknowledgment must be committed before we claim it is stored."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import push_server
import push_receipt

class DurableReceiptEndpointTests(unittest.TestCase):
    def setUp(self):
        self.secret = "local-only-key"
        self.proof = push_receipt.issue(self.secret)
        self.handler = SimpleNamespace(path="/device-receipt")

    def test_persisted_response_and_idempotent_write_id(self):
        sent = []
        saved = []
        conn = Mock()
        dbctx = Mock()
        dbctx.__enter__ = Mock(return_value=conn)
        dbctx.__exit__ = Mock(return_value=False)
        for state in ("show-resolved", "clicked", "clicked"):
            payload = {**self.proof, "receiptState": state}
            with patch.object(push_server, "PUSH_SERVICE_TOKEN", self.secret), \
                 patch.object(push_server, "json_body", return_value=payload), \
                 patch.object(push_server, "db", return_value=dbctx), \
                 patch.object(push_server.diagnostic_history, "write", side_effect=lambda _conn, data: saved.append(data)), \
                 patch.object(push_server, "send_json", side_effect=lambda _, code, data: sent.append((code, data))):
                push_server.Handler.do_POST(self.handler)
        self.assertEqual([x[0] for x in sent], [200,200,200])
        self.assertTrue(all(x[1] == {"stored":True, "androidDisplayVerified":False} for x in sent))
        self.assertEqual(saved[1]["id"], saved[2]["id"])
        self.assertNotEqual(saved[0]["id"], saved[1]["id"])
        self.assertEqual(saved[1]["payload"]["receiptState"], "clicked")
        self.assertNotIn("receiptProof", str(saved))
        self.assertNotIn(self.secret, str(saved))
        self.assertEqual(conn.execute.call_count,3)

    def test_no_success_when_storage_fails(self):
        results=[]
        conn=Mock()
        dbctx=Mock()
        dbctx.__enter__=Mock(return_value=conn)
        dbctx.__exit__=Mock(return_value=False)
        with patch.object(push_server, "PUSH_SERVICE_TOKEN", self.secret), \
             patch.object(push_server, "json_body", return_value={**self.proof, "receiptState":"clicked"}), \
             patch.object(push_server, "db", return_value=dbctx), \
             patch.object(push_server.diagnostic_history, "write", side_effect=RuntimeError("database-unavailable")), \
             patch.object(push_server, "send_json", side_effect=lambda _,code,payload: results.append((code,payload))):
            push_server.Handler.do_POST(self.handler)
        self.assertEqual(len(results),1)
        self.assertEqual(results[0][0],503)
        self.assertNotIn("database-unavailable", str(results[0]))

    def test_invalid_proof_never_touches_storage(self):
        answers=[]
        with patch.object(push_server, "PUSH_SERVICE_TOKEN", self.secret), \
             patch.object(push_server, "json_body", return_value={**self.proof, "receiptState":"clicked", "receiptProof":"0"*64}), \
             patch.object(push_server, "db") as db, \
             patch.object(push_server, "send_json", side_effect=lambda _,code,payload: answers.append(code)):
            push_server.Handler.do_POST(self.handler)
            db.assert_not_called()
        self.assertEqual(answers,[400])

if __name__ == "__main__":
    unittest.main()
