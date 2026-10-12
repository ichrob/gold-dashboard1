import unittest
import bob_self_healing as sh
import bob_issue_watchdog as watchdog


def healthy():
    return {
        "status": "ok", "build": "a" * 40, "reasons": [],
        "automaticCollection": {"enabled": True, "running": True},
        "fibonacciMonitor": {"configured": True, "status": "active"},
        "strategyResearch": {"enabled": True, "running": True},
    }


class SelfHealingTests(unittest.TestCase):
    def setUp(self):
        sh._LAST_ATTEMPTS.clear()
        sh._EVENTS.clear()
        sh._ACTIVE = ()

    def test_reasons_are_allowlisted(self):
        data = healthy()
        data["status"] = "degraded"
        data["reasons"] = ["market-feed-not-current", "unrecognized-diagnostic"]
        data["build"] = "not-a-commit"
        out = sh.snapshot(data)
        self.assertEqual(out["status"], "hilfe-noetig")
        self.assertNotIn("unrecognized-diagnostic", out["helpRequest"])
        self.assertIn("market-feed-not-current", out["helpRequest"])
        self.assertEqual(len(out["active"]), 1)

    def test_worker_restart_is_allowlisted_throttled_and_audited(self):
        calls = []
        self.assertFalse(sh.restart_worker("untrusted-code", True, lambda: calls.append("bad"), now=100))
        self.assertTrue(sh.restart_worker("market-worker-stopped", True, lambda: calls.append("once"), now=100))
        self.assertFalse(sh.restart_worker("market-worker-stopped", True, lambda: calls.append("twice"), now=120))
        self.assertTrue(sh.restart_worker("market-worker-stopped", True, lambda: calls.append("third"), now=281))
        self.assertEqual(calls, ["once", "third"])
        self.assertEqual(sh._EVENTS[0]["kind"], "repair-attempt")

    def test_failed_restart_does_not_expose_exception_text(self):
        def fail():
            raise RuntimeError("internal error should not be copied")
        self.assertFalse(sh.restart_worker("background-worker-stopped", True, fail, now=100))
        self.assertNotIn("internal error should not be copied", str(sh.snapshot(healthy())))

    def test_recovery_is_recorded(self):
        broken = healthy()
        broken["status"] = "degraded"
        broken["reasons"] = ["background-not-current"]
        sh.snapshot(broken)
        out = sh.snapshot(healthy())
        self.assertEqual(out["status"], "bereit")
        self.assertEqual(out["recentEvents"][0]["kind"], "recovered")


class WatchdogTests(unittest.TestCase):
    def test_fixed_public_diagnostic_codes(self):
        app = healthy()
        push = {"ok": True, "paperObservation": {"state": "ok"}}
        self.assertEqual(watchdog.classify(app, {"status": "ok"}, push, market_open=False), [])
        self.assertIn("background-not-current", watchdog.classify(app, None, push, market_open=True))
        app["automaticCollection"]["running"] = False
        self.assertIn("market-worker-stopped", watchdog.classify(app, {"status": "ok"}, push, market_open=True))
        self.assertEqual(watchdog.classify(None, None, None, market_open=False),
                         ["push-unreachable", "scanner-unreachable"])

    def test_unknown_issue_codes_are_excluded(self):
        report = watchdog.issue_body(["scanner-unreachable", "unrecognized-diagnostic"], "2026-10-12T13:00:00Z")
        self.assertIn("scanner-unreachable", report)
        self.assertNotIn("unrecognized-diagnostic", report)

    def test_issue_deduplicates_and_closes(self):
        actions = []
        current = []
        def requester(method, path, **kw):
            actions.append((method, path, kw.get("data")))
            if method == "GET":
                return list(current)
            if path == "/issues":
                return {"number": 5}
            return {}
        args = {"token": "test", "repo": "ichrob/gold-dashboard1", "requester": requester}
        self.assertEqual(watchdog.sync_issue(["scanner-unreachable"], **args), "opened-5")
        current[:] = [{"title": watchdog.ISSUE_TITLE, "number": 5}]
        self.assertEqual(watchdog.sync_issue(["scanner-unreachable"], **args), "already-open")
        self.assertEqual(watchdog.sync_issue([], **args), "closed-5")
        self.assertEqual([a[0] for a in actions], ["GET", "POST", "GET", "GET", "POST", "PATCH"])

    def test_scope_prevents_other_repo_access(self):
        with self.assertRaises(ValueError):
            watchdog.sync_issue(["scanner-unreachable"], token="test", repo="wrong/repo")


if __name__ == "__main__":
    unittest.main()
