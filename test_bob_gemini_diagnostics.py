"""No-secret regressions for Gemini diagnostic views and audit tools."""
import json
import unittest
from unittest.mock import Mock

import bob_gemini_diagnostics as views
import bob_mcp


def sample():
    return {
        "readOnly": True, "realOrders": False, "observedAt": "2026-11-11T00:00:00Z",
        "areas": {
            "simulationAndPush": {"status": "observed",
                "accounts": [{"profile": str(i), "recentCases": {
                    "status": "observed", "items": [{"status": "inconclusive"}]}}
                    for i in range(9)],
                "history": {"journal": {"status": "observed",
                    "items": [{"at": i, "state": "no-exit-evidence"} for i in range(12)]}}},
            "comparisonEvidence": {"status": "observed",
                                   "items": [{"originalAt": i} for i in range(8)]},
            "comparisonHealth": {"status": "observed"},
            "newStudiesBrief": {"status": "observed",
                                "strategyWinnerConfirmed": False,
                                "quality": {"status": "collecting", "studies": [
                                    {"id": "entry-delay", "started": 42, "complete": 7,
                                     "inconclusive": 35, "open": 0}]}},
            "simulationRuntimeBrief": {"status": "observed",
                                       "profilesObserved": 9, "completedProfiles": 7},
            "paperProfitEvidence": {"status": "observed",
                                    "netProductReturnsVerified": False}},
    }


class ViewTests(unittest.TestCase):
    def test_fixed_paths_and_pagination_do_not_change_input(self):
        original = sample()
        before = json.dumps(original, sort_keys=True)
        p0 = views.project_view(original, {"view": "simulation-accounts",
                                            "page": 0, "pageSize": 3})
        p1 = views.project_view(original, {"view": "simulation-accounts",
                                            "page": 1, "pageSize": 3})
        self.assertTrue(p0["readOnly"])
        self.assertFalse(p0["realOrders"])
        self.assertEqual(p0["observedAt"], original["observedAt"])
        self.assertEqual(p0["data"]["totalItems"], 9)
        self.assertEqual([x["profile"] for x in p0["data"]["items"]], ["0", "1", "2"])
        self.assertEqual([x["profile"] for x in p1["data"]["items"]], ["3", "4", "5"])
        self.assertEqual(json.dumps(original, sort_keys=True), before)

    def test_comparison_missing_does_not_become_healthy(self):
        o = sample()
        del o["areas"]["comparisonEvidence"]
        r = views.project_view(o, {"view": "comparison-evidence"})
        self.assertEqual(r["status"], "unavailable")
        self.assertEqual(r["data"]["reason"], "source-area-not-observed")

    def test_empty_and_invalid_views_fail_closed(self):
        for bad in ({}, {"view": "not-known"}, {"view": "__dict__"},
                    {"view": "simulation-accounts", "page": True},
                    {"view": "simulation-accounts", "pageSize": 0},
                    {"view": "simulation-accounts", "page": 1000},
                    {"view": "simulation-accounts", "secret": "x"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                views.validate_view(bad)

    def test_large_subtree_is_explicitly_limited(self):
        o = sample()
        o["areas"]["comparisonEvidence"]["large"] = "a" * 100000
        r = views.project_view(o, {"view": "comparison-evidence"})
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["data"]["reason"], "omitted-response-size-limit")
        self.assertLess(len(json.dumps(r).encode()), views.MAX_BYTES)

    def test_audit_never_claims_profits_or_unobserved_originals(self):
        o = sample()
        r = views.simulation_audit(o)
        self.assertEqual(r["status"], "partial")
        self.assertFalse(r["originalCoverageComplete"])
        self.assertFalse(r["netProductReturnsVerified"])
        self.assertFalse(r["strategyWinnerConfirmed"])
        self.assertEqual(r["studies"][0]["inconclusive"], 35)
        self.assertFalse(r["realOrders"])
        o["truncated"] = True
        o["omittedAreas"] = ["simulationAndPush", "comparisonEvidence"]
        r = views.simulation_audit(o)
        self.assertEqual(r["omittedAreas"], ["simulationAndPush", "comparisonEvidence"])


class McpViewTests(unittest.TestCase):
    def call(self, name, args, *, diagnostics=True):
        reader = Mock(return_value=sample())
        request = {"jsonrpc": "2.0", "id": 17, "method": "tools/call",
                   "params": {"name": name, "arguments": args}}
        status, body = bob_mcp.handle(request, lambda: {"status": "unused"},
                                     diagnostics_reader=reader if diagnostics else None)
        return status, body, reader

    def test_tools_are_only_diagnostic_scope_and_read_only(self):
        defs = {t["name"]: t for t in bob_mcp.tool_definitions(diagnostics=True)}
        for name in ("bob_diagnostics_view", "bob_simulation_audit"):
            self.assertTrue(defs[name]["annotations"]["readOnlyHint"])
            self.assertEqual(defs[name]["inputSchema"]["type"], "object")
            self.assertEqual(defs[name]["securitySchemes"][0]["scopes"],
                             ["bob:diagnostics:read"])
            self.assertEqual(defs[name]["parameters"], defs[name]["inputSchema"])

    def test_unauthorized_tool_does_not_read_private_data(self):
        for name, args in (("bob_diagnostics_view", {"view": "comparison-evidence"}),
                           ("bob_simulation_audit", {})):
            status, body, reader = self.call(name, args, diagnostics=False)
            self.assertEqual(status, 200)
            self.assertTrue(body["result"]["isError"])
            self.assertIn("insufficient_scope",
                          body["result"]["_meta"]["mcp/www_authenticate"][0])
            reader.assert_not_called()

    def test_valid_view_and_audit_return_sanitized_json(self):
        for name, args in (("bob_diagnostics_view", {"view": "simulation-accounts",
                                                      "page": 1, "pageSize": 2}),
                           ("bob_simulation_audit", {})):
            status, body, reader = self.call(name, args)
            self.assertEqual(status, 200)
            self.assertFalse(body["result"]["isError"])
            payload = json.loads(body["result"]["content"][0]["text"])
            self.assertTrue(payload["readOnly"])
            self.assertFalse(payload["realOrders"])
            reader.assert_called_once()

    def test_invalid_args_do_not_read(self):
        for name, args in (("bob_diagnostics_view", {"view": "accounts-private"}),
                           ("bob_diagnostics_view", {"view": "study-quality", "page": -1}),
                           ("bob_simulation_audit", {"trade": True})):
            status, body, reader = self.call(name, args)
            self.assertEqual(status, 200)
            self.assertEqual(body["error"]["code"], -32602)
            reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
