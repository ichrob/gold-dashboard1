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
        sh._UNRESOLVED.clear()
        sh._SUSPECT.clear()
        sh._HEALTHY.clear()
        sh._PENDING.clear()

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
        sh.observe(broken, now=100)
        sh.observe(broken, now=121)
        sh.observe(healthy(), now=140)
        sh.observe(healthy(), now=161)
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

    def test_distinct_issues_are_counted_and_recovered_individually(self):
        actions = []
        current = []
        next_number = [5]

        def requester(method, path, **kw):
            data = kw.get("data")
            actions.append((method, path, data))
            if method == "GET":
                return list(current)
            if method == "POST" and path == "/issues":
                number = next_number[0]
                next_number[0] += 1
                current.append({"title": data["title"], "number": number})
                return {"number": number}
            if method == "PATCH":
                number = int(path.split("/")[2])
                current[:] = [item for item in current if item["number"] != number]
            return {}

        args = {"token": "test", "repo": "ichrob/gold-dashboard1", "requester": requester}
        both = ["scanner-unreachable", "push-unreachable"]
        self.assertEqual(watchdog.sync_issue(both, **args), "opened-5,opened-6")
        self.assertEqual(len(current), 2)
        self.assertEqual(watchdog.sync_issue(both, **args), "already-open")
        self.assertEqual(watchdog.sync_issue(["scanner-unreachable"], **args), "closed-5")
        self.assertEqual([item["number"] for item in current], [6])
        self.assertEqual(watchdog.sync_issue([], **args), "closed-6")
        self.assertEqual(current, [])
        self.assertEqual(sum(1 for method, path, _ in actions
                             if method == "POST" and path == "/issues"), 2)

    def test_legacy_combined_issue_is_archived(self):
        actions = []
        current = [{"title": watchdog.ISSUE_TITLE, "number": 20}]
        def requester(method, path, **kw):
            actions.append((method, path))
            if method == "GET":
                return list(current)
            if method == "POST" and path == "/issues":
                return {"number": 21}
            return {}
        args = {"token": "test", "repo": "ichrob/gold-dashboard1", "requester": requester}
        self.assertEqual(watchdog.sync_issue(["scanner-unreachable"], **args), "opened-21,closed-20")
        self.assertIn(("PATCH", "/issues/20"), actions)

    def test_scope_prevents_other_repo_access(self):
        with self.assertRaises(ValueError):
            watchdog.sync_issue(["scanner-unreachable"], token="test", repo="wrong/repo")


if __name__ == "__main__":
    unittest.main()
