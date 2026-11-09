"""Contract tests for the stand-alone provider; no listening socket or real OCR."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch


spec=importlib.util.spec_from_file_location("bob_external_ocr_server",
    Path(__file__).resolve().parent/"ops"/"ocr-oci"/"server.py")
server=importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
RAW=b"\x89PNG\r\n\x1a\n"+b"synthetic" * 30
PNG=base64.b64encode(RAW).decode()
TOKEN="p"*48


class ServerTests(unittest.TestCase):
    def handler(self, token):
        handler=object.__new__(server.Handler)
        handler.path="/ocr"
        handler.headers={"X-Bob-Ocr-Key": token}
        handler.rfile=io.BytesIO()
        handler.respond=Mock()
        return handler

    def body(self, **changes):
        data={"png":PNG, "sha256":hashlib.sha256(RAW).hexdigest(), "enhanced":False}
        data.update(changes)
        return json.dumps(data).encode()

    def test_wrong_token_rejected_before_reading_image_or_starting_ocr(self):
        handler=self.handler("wrong")
        with patch.dict(server.os.environ,{"BOB_REMOTE_OCR_TOKEN":TOKEN},clear=True), \
             patch.object(server.subprocess,"run") as run:
            handler.do_POST()
        handler.respond.assert_called_once_with(401,{"error":"unauthorized"})
        run.assert_not_called()

    def test_authenticated_request_has_exact_digest_and_bounded_ocr_process(self):
        handler=self.handler(TOKEN)
        data=self.body()
        handler.headers["Content-Length"]=str(len(data))
        handler.rfile=io.BytesIO(data)
        child=subprocess.CompletedProcess(["python"],0,json.dumps([["read1","read2"]]),"")
        with patch.dict(server.os.environ,{"BOB_REMOTE_OCR_TOKEN":TOKEN},clear=True), \
             patch.object(server.subprocess,"run",return_value=child) as run:
            handler.do_POST()
        self.assertEqual(handler.respond.call_args.args[0],200)
        self.assertEqual(handler.respond.call_args.args[1]["sha256"],hashlib.sha256(RAW).hexdigest())
        self.assertEqual(handler.respond.call_args.args[1]["passes"],["read1","read2"])
        self.assertEqual(run.call_args.kwargs["timeout"],55)
        self.assertIn("--ocr",run.call_args.args[0])

    def test_missing_owner_free_tier_review_blocks_service_start(self):
        with patch.dict(server.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "owner_free_tier_review_required"):
                server.serve()

    def test_tls_only_service_fails_if_certificate_absent(self):
        with patch.dict(server.os.environ, {
                "BOB_OCI_FREE_TIER_OWNER_REVIEWED": "true",
                "BOB_ORACLE_OCR_TLS_CERT": "/nonexistent/tls.crt",
                "BOB_ORACLE_OCR_TLS_KEY": "/nonexistent/tls.key"}, clear=True):
            with self.assertRaises((FileNotFoundError, OSError)):
                server.serve()

    def test_mismatched_input_hash_is_never_accepted(self):
        handler=self.handler(TOKEN)
        data=self.body(sha256="0"*64)
        handler.headers["Content-Length"]=str(len(data))
        handler.rfile=io.BytesIO(data)
        with patch.dict(server.os.environ,{"BOB_REMOTE_OCR_TOKEN":TOKEN},clear=True), \
             patch.object(server.subprocess,"run") as run:
            handler.do_POST()
        handler.respond.assert_called_once_with(422,{"error":"recognition_failed"})
        run.assert_not_called()


if __name__=="__main__":
    unittest.main()
