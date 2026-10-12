"""Zukunft endpoint must never expose research to an unauthenticated caller."""
import io
import json
import unittest
from unittest.mock import patch
import server


def fake_handler():
    h = object.__new__(server.Handler)
    h.path = "/api/zukunft/research"
    h.headers = {}
    h.wfile = io.BytesIO()
    h.responses = []
    h.send_response = lambda status: h.responses.append(status)
    h.send_header = lambda *args: None
    h.end_headers = lambda: None
    return h


class FutureLabHttpTests(unittest.TestCase):
    def test_research_requires_login(self):
        h = fake_handler()
        with patch.object(server.bob_recovery,"route",return_value=False), \
             patch.object(server.Handler,"authenticated",return_value=False), \
             patch.object(server.strategy_lab_background,"request",side_effect=AssertionError("no fetch")):
            h.do_GET()
        self.assertEqual(h.responses,[401])
        self.assertIn(b"Authentication required", h.wfile.getvalue())

    def test_authenticated_research_only_reads_archive(self):
        h = fake_handler()
        stub = dict(mode="RESEARCH_ONLY",approved=False,orderExecutionEnabled=False,
                    status="insufficient")
        snapshot = dict(mode="RESEARCH_ONLY",latestReport=stub,
                        automation=dict(enabled=True,history=[],lastDay="2026-10-12"))
        with patch.object(server.bob_recovery,"route",return_value=False), \
             patch.object(server.Handler,"authenticated",return_value=True), \
             patch.object(server.strategy_lab_background,"request",return_value=snapshot) as reader, \
             patch.object(server.strategy_lab,"run",side_effect=AssertionError("no reanalysis")), \
             patch.object(server.broker_bridge,"status",return_value=dict(executionEnabled=False)):
            h.do_GET()
        self.assertEqual(h.responses,[200])
        reader.assert_called_once_with("read", {})
        report=json.loads(h.wfile.getvalue())
        self.assertFalse(report["orderExecutionEnabled"])
        self.assertTrue(report["automation"]["enabled"])
        self.assertFalse(report["brokerReadiness"]["executionEnabled"])

    def test_no_archive_never_fabricates_results(self):
        h=fake_handler()
        with patch.object(server.bob_recovery,"route",return_value=False), \
             patch.object(server.Handler,"authenticated",return_value=True), \
             patch.object(server.strategy_lab_background,"request",side_effect=OSError("offline")):
            h.do_GET()
        result=json.loads(h.wfile.getvalue())
        self.assertEqual(result["status"],"unavailable")
        self.assertFalse(result["approved"])

if __name__=="__main__":
    unittest.main()
