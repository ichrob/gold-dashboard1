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
            return {"key": "PUSH_SERVICE_TOKEN", "value": self.ORIGINAL}
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

    def test_utf8_passphrase_with_umlaut_and_emoji_is_accepted_and_verifiable(self):
        # Regression: compare_digest(str, str) throws TypeError for non-ASCII
        # even when the two passphrases match exactly. Bytes are safe.
        password="Starkes-Passwort-äÖß-🔐-2026!"
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"bob-root.vault"
            provided=iter((self.API,password,password))
            result=transfer.run_once(
                input_secret=lambda _:next(provided),fetch=self.api,output=output)
            self.assertTrue(result["localRoundtripVerified"])
            self.assertEqual(unlock_escrow(output,password),self.ORIGINAL.encode())
            self.assertNotIn(password,output.read_text())
            self.assertNotIn(password,json.dumps(result))

    def test_different_utf8_passphrases_do_not_create_vault(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"bob-root.vault"
            provided=iter((self.API,"Sicher-ä-2026-erstes","Sicher-ä-2026-zweites"))
            with self.assertRaises(transfer.TransportBlocked):
                transfer.run_once(input_secret=lambda _:next(provided),
                                  fetch=self.api,output=output)
            self.assertFalse(output.exists())

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
                    return {"key":"OTHER", "value":self.ORIGINAL}
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
                if path=="/v1/services?limit=100" else {"key":"OTHER","value":"x"*64})

    def test_official_render_single_response_is_bare_env_var(self):
        # Public OpenAPI: GET /v1/services/{id}/env-vars/{key}
        # returns a bare envVar, unlike the list endpoint.
        self.assertEqual(
            transfer.original_root(self.API, self.api), self.ORIGINAL.encode())
        def wrapped(token,path):
            if "/env-vars/" in path:
                return {"envVar":{"key":"PUSH_SERVICE_TOKEN","value":self.ORIGINAL}}
            return self.api(token,path)
        with self.assertRaises(transfer.TransportBlocked):
            transfer.original_root(self.API, wrapped)

    def test_http_statuses_are_distinguished_without_response_body(self):
        import io
        import urllib.error
        def Fake(error_code):
            class Opener:
                def open(self, request, timeout):
                    raise urllib.error.HTTPError(
                        request.full_url, error_code, "Do not echo secret response",
                        {}, io.BytesIO(b'API_PRIVATE_VALUE_NOT_FOR_LOGS'))
            return Opener()
        for status, expected in (
            (401,"RENDER_AUTH_REJECTED"),
            (403,"RENDER_ACCESS_DENIED"),
            (404,"RENDER_RESOURCE_NOT_FOUND"),
            (429,"RENDER_RATE_LIMITED")):
            with self.subTest(status=status):
                with self.assertRaises(transfer.TransportBlocked) as context:
                    transfer.read_json(self.API, "/v1/services?limit=100",
                                       opener=Fake(status))
                self.assertEqual(str(context.exception), expected)
                self.assertNotIn("API_PRIVATE",str(context.exception))

    def test_cli_only_prints_allowlisted_status_codes(self):
        import io
        import sys
        from unittest.mock import patch
        stream=io.StringIO()
        with patch.object(sys,"argv",["bob_render_to_offline_escrow.py"]), \
             patch.object(transfer,"run_once",
                          side_effect=transfer.TransportBlocked(
                              "RENDER_ACCESS_DENIED")), \
             patch("sys.stdout",new=stream):
            self.assertEqual(transfer.main(),1)
        output=stream.getvalue()
        self.assertEqual(json.loads(output)["diagnosticCode"],
                         "RENDER_ACCESS_DENIED")
        self.assertNotIn(self.API,output)
        self.assertNotIn(self.ORIGINAL,output)

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
                assert DirectEscrowTests.API not in request.full_url
                assert request.headers["Authorization"] == "Bearer "+DirectEscrowTests.API
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
