"""Synthetic local-only tests: no live Render requests or production credentials."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bob_render_to_offline_escrow as transfer
from bob_offline_key_escrow import unlock_escrow


class DirectEscrowTests(unittest.TestCase):
    API = "synthetic-API-key-" + "A"*35
    ORIGINAL = "synthetic-original-root-" + "B"*49
    PASSWORD = "separate strong synthetic offline password"

    def api(self, token, path):
        self.assertEqual(token, self.API)
        if path == "/v1/services?limit=100":
            return [{"service": {"id": "srv-abcdef123456789", "name": "bob-push-service"},
                     "cursor": "done"}]
        if path == "/v1/services/srv-abcdef123456789/env-vars/PUSH_SERVICE_TOKEN":
            return {"envVar": {"key": "PUSH_SERVICE_TOKEN", "value": self.ORIGINAL}}
        self.fail("unexpected network endpoint")

    def test_real_original_is_locally_encrypted_without_chat_or_disk_plaintext(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "private" / "bob-archive-root.vault"
            provided = iter((self.API,self.PASSWORD,self.PASSWORD))
            status = transfer.run_once(input_secret=lambda _:next(provided),
                                       fetch=self.api,output=output)
            self.assertEqual(status["status"], "escrow-ciphertext-created")
            self.assertTrue(status["localRoundtripVerified"])
            self.assertFalse(status["offlineMediaVerified"])
            self.assertFalse(status["archiveCiphertextVerified"])
            self.assertFalse(status["independentPostgresRestoreVerified"])
            self.assertFalse(status["productionDataChanged"])
            self.assertNotIn(self.API,json.dumps(status))
            self.assertNotIn(self.ORIGINAL,json.dumps(status))
            self.assertNotIn(self.API,output.read_text())
            self.assertNotIn(self.ORIGINAL,output.read_text())
            self.assertEqual(unlock_escrow(output,self.PASSWORD),self.ORIGINAL.encode())
            with self.assertRaises(transfer.TransportBlocked):
                transfer.run_once(input_secret=lambda _:self.API,fetch=self.api,output=output)

    def test_wrong_env_key_or_service_fails_before_escrow(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "vault"
            def wrong_service(token, path):
                return [{"service":{"id":"srv-abcdef123456789","name":"different"}}]
            with self.assertRaises(transfer.TransportBlocked):
                transfer.run_once(input_secret=lambda _:self.API,
                                  fetch=wrong_service,output=output)
            self.assertFalse(output.exists())
            def wrong_env(token,path):
                if "env-vars/" in path:
                    return {"envVar":{"key":"OTHER", "value":self.ORIGINAL}}
                return self.api(token,path)
            with self.assertRaises(transfer.TransportBlocked):
                transfer.run_once(input_secret=lambda _:self.API,
                                  fetch=wrong_env,output=output)
            self.assertFalse(output.exists())

    def test_duplicate_service_and_source_group_absence_fail_closed(self):
        two=[{"service":{"name":"bob-push-service","id":"srv-aaaaaaaa"}},
             {"service":{"name":"bob-push-service","id":"srv-bbbbbbbb"}}]
        with self.assertRaises(transfer.TransportBlocked):
            transfer.discover_service(self.API,lambda *_:two)
        with self.assertRaises(transfer.TransportBlocked):
            transfer.original_root(self.API,lambda token,path:
                [{"service":{"name":"bob-push-service","id":"srv-aaaaaaaa"}}]
                if path=="/v1/services?limit=100" else {"envVar":{}})

    def test_no_credential_in_url_and_no_remote_mutations(self):
        class FakeResponse:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):
                return json.dumps([{"service":{
                    "id":"srv-abcdefghijklmno","name":"bob-push-service"}}]).encode()
        class FakeOpener:
            def open(self, request, timeout):
                self_req = request
                assert request.get_method() == "GET"
                assert request.full_url == transfer.API_HOST + "/v1/services?limit=100"
                assert self.API not in request.full_url
                assert request.headers["Authorization"] == "Bearer "+self.API
                return FakeResponse()
        value=transfer.read_json(self.API,"/v1/services?limit=100",opener=FakeOpener())
        self.assertEqual(value[0]["service"]["name"],"bob-push-service")
        for bad in ("https://other.site/v1/services?limit=100",
                    "/v1/services/abc/env-vars/OTHER",
                    "/v1/services?limit=100#fragment",
                    "/v1/services?limit=100&other=1"):
            with self.subTest(path=bad),self.assertRaises(transfer.TransportBlocked):
                transfer.read_json(self.API,bad,opener=FakeOpener())


if __name__=="__main__":
    unittest.main()
