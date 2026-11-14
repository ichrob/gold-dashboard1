"""No-network release-gate tests for Twelve Data's manual localhost button.

Never set real credentials, call the vendor, or approve a release.
"""
import http.client
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from http.server import HTTPServer

import twelve_research_one_click as ui


class OneClickSafetyTests(unittest.TestCase):
    def test_default_is_blocked_and_does_not_call_network(self):
        with patch.object(ui, "fetch_research") as network:
            status = ui.readiness({})
            self.assertEqual(status["code"], "BLOCKED")
            self.assertFalse(status["networkUsed"])
            self.assertFalse(status["licensedDataDisplayed"])
            self.assertEqual(ui.OneClick(env={}).run(), "BLOCKED")
            network.assert_not_called()

    def test_flags_cannot_substitute_for_private_archive(self):
        flags = {key: "1" for key in ui.RELEASE_GATES}
        flags["BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED"] = "1"
        flags["BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED"] = "1"
        flags["TWELVEDATA_API_KEY"] = "synthetic_test_only"
        flags["BOB_TWELVE_RESEARCH_ARCHIVE"] = "/not/a/real/private/archive.sqlite"
        self.assertEqual(ui.readiness(flags)["code"], "BLOCKED")

    def test_button_is_disabled_when_blocked_and_displays_no_data(self):
        page = ui.page("BLOCKED", "synthetic-nonce")
        self.assertIn("disabled", page)
        self.assertIn('method="post"', page)
        self.assertNotIn("4000.00", page)
        self.assertIn("Keine Live-Kurse", page)

    def test_single_attempt_consumed_before_fetch_even_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.chmod(0o700)
            archive = root / "research.sqlite"
            sqlite3.connect(str(archive)).close()
            archive.chmod(0o600)
            flags = {key: "1" for key in ui.RELEASE_GATES}
            flags.update(BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED="1",
                         BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED="1",
                         TWELVEDATA_API_KEY="synthetic_test_only",
                         BOB_TWELVE_RESEARCH_ARCHIVE=str(archive))
            # Unit-test-only attestation. No real approval is given.
            with patch.object(ui, "manual_preflight", return_value={"blockers": []}):
                calls = []
                def failed(*args, **kwargs):
                    calls.append(1)
                    raise RuntimeError("synthetic failure")
                job = ui.OneClick(env=flags, fetch=failed)
                self.assertEqual(job.run(), "REQUEST_FAILED")
                self.assertTrue(job.used)
                self.assertEqual(job.run(), "ALREADY_USED")
                self.assertEqual(len(calls), 1)

    def test_blocked_local_session_expires_without_request(self):
        class FakeServer:
            def __init__(self):
                self.calls = 0
                self.timeout = None
            def handle_request(self):
                self.calls += 1
        server = FakeServer()
        job = ui.OneClick(env={})
        ticks = iter([0, 0, 1, 2])
        ui.serve_until_used(server, job, max_idle_seconds=1,
                            clock=lambda: next(ticks))
        self.assertEqual(server.calls, 1)
        self.assertFalse(job.used)

    def test_host_origin_nonce_and_get_do_not_execute(self):
        job = ui.OneClick(env={})
        server = HTTPServer(("127.0.0.1", 0), ui.handler_factory(job, "synthetic-nonce"))
        server.timeout = 2
        thread = threading.Thread(target=lambda: [server.handle_request() for _ in range(4)],
                                  daemon=True)
        thread.start()
        try:
            port = server.server_port
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/", headers={"Host": "127.0.0.1:" + str(port)})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn(b"disabled", response.read())
            conn.close()
            for origin, nonce in [("http://evil.invalid", "synthetic-nonce"),
                                  ("http://127.0.0.1:" + str(port), "wrong-nonce")]:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                body = urlencode({"nonce": nonce})
                conn.request("POST", "/run", body, headers={
                    "Host": "127.0.0.1:" + str(port),
                    "Origin": origin,
                    "Content-Type": "application/x-www-form-urlencoded"})
                response = conn.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
                conn.close()
            self.assertFalse(job.used)
        finally:
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
