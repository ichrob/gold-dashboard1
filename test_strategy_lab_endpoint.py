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
             patch.object(server,"fetch_technical_history",side_effect=AssertionError("no fetch")):
            h.do_GET()
        self.assertEqual(h.responses,[401])
        self.assertIn(b"Authentication required", h.wfile.getvalue())

    def test_authenticated_research_is_read_only(self):
        h = fake_handler()
        stub = dict(mode="RESEARCH_ONLY",approved=False,orderExecutionEnabled=False,
                    status="insufficient")
        data = [dict(openTime=1700000000000+i*3600000,open=2000.,high=2001.,
                     low=1999.,close=2000.,isOpen=False,instrument="XAU/USD")
                for i in range(600)]
        with patch.object(server.bob_recovery,"route",return_value=False), \
             patch.object(server.Handler,"authenticated",return_value=True), \
             patch.object(server,"retain_technical_history",return_value=data), \
             patch.object(server.strategy_lab,"run",return_value=stub) as research, \
             patch.object(server.broker_bridge,"status",return_value=dict(executionEnabled=False)):
            h.do_GET()
        self.assertEqual(h.responses,[200])
        research.assert_called_once()
        report=json.loads(h.wfile.getvalue())
        self.assertFalse(report["orderExecutionEnabled"])
        self.assertFalse(report["brokerReadiness"]["executionEnabled"])


if __name__=="__main__":
    unittest.main()
