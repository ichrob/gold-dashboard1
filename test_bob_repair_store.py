"""Regression tests for Bob's permanent self-healing counter (no real network)."""
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import bob_repair_store as archive
import bob_self_healing as healing


class Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        archive.init(self)

    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace("%s", "?"), args)


class RepairStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        archive._STATS_CACHE = None
        archive._STATS_AT = 0.0
        healing._LAST_ATTEMPTS.clear()
        healing._EVENTS.clear()
        healing._UNRESOLVED.clear()
        healing._SUSPECT.clear()
        healing._HEALTHY.clear()
        healing._PENDING.clear()
        healing._ACTIVE = ()

    def write(self, key, kind, code):
        return archive.handle(self.db, "write", {
            "id": "%032x" % key,
            "kind": kind,
            "code": code,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    def test_permanent_counts_and_idempotent_event_ack(self):
        self.assertTrue(self.write(1, "detected", "market-worker-stopped")["stored"])
        self.assertFalse(self.write(1, "detected", "market-worker-stopped")["stored"])
        self.write(2, "repair-attempt", "market-worker-stopped")
        self.write(3, "repair-verified", "market-worker-stopped")
        self.write(4, "recovered", "market-worker-stopped")
        self.write(5, "detected", "market-feed-not-current")
        self.write(6, "recovered", "market-feed-not-current")
        data = archive.handle(self.db, "read", {})
        self.assertEqual(data["detected"], 2)
        self.assertEqual(data["repairAttempts"], 1)
        self.assertEqual(data["verifiedRepairs"], 1)
        self.assertEqual(data["normalizedWithoutVerifiedRepair"], 1)
        self.assertEqual(len(data["events"]), 6)

    def test_restart_attempt_never_counts_as_solution(self):
        self.write(1, "detected", "background-worker-stopped")
        self.write(2, "repair-attempt", "background-worker-stopped")
        self.write(3, "repair-failed", "background-worker-stopped")
        data = archive.handle(self.db, "read", {})
        self.assertEqual(data["detected"], 1)
        self.assertEqual(data["verifiedRepairs"], 0)
        self.assertEqual(data["failedAttempts"], 1)

    def test_invalid_codes_or_unstructured_details_rejected(self):
        event = {"id": "1" * 32, "at": datetime.now(timezone.utc).isoformat(),
                 "kind": "detected", "code": "not-a-fixed-code"}
        with self.assertRaises(ValueError):
            archive.handle(self.db, "write", event)
        event["code"] = "market-worker-stopped"
        event["kind"] = "arbitrary-message"
        with self.assertRaises(ValueError):
            archive.handle(self.db, "write", event)

    def test_cache_marks_remote_outage_as_stale_not_zero(self):
        values = iter(({"status": "ok", "detected": 3, "verifiedRepairs": 1,
                        "normalizedWithoutVerifiedRepair": 1, "repairAttempts": 2},
                       OSError("unreachable")))
        def reader(action, payload):
            value = next(values)
            if isinstance(value, Exception):
                raise value
            return value
        first = archive.statistics(read=reader, clock=lambda: 100)
        second = archive.statistics(read=reader, clock=lambda: 105)
        third = archive.statistics(read=reader, clock=lambda: 200)
        self.assertEqual((first["detected"], second["detected"], third["detected"]), (3, 3, 3))
        self.assertEqual(third["status"], "stale")

    def test_positive_post_repair_verification_requires_two_probes(self):
        healthy = {
            "status": "ok", "reasons": [],
            "automaticCollection": {"enabled": True, "running": True},
            "fibonacciMonitor": {"configured": True, "status": "active"},
            "strategyResearch": {"enabled": True, "running": True, "phase": "already-stored"},
        }
        with patch.object(archive, "queue_event"):
            self.assertTrue(healing.restart_worker(
                "research-worker-stopped", True, lambda: None, now=100))
            healing.observe(healthy, now=101)
            self.assertFalse(any(x["kind"] == "repair-verified" for x in healing._EVENTS))
            healing.observe(healthy, now=111)
            self.assertFalse(any(x["kind"] == "repair-verified" for x in healing._EVENTS))
            healing.observe(healthy, now=122)
            self.assertEqual(sum(x["kind"] == "repair-verified" for x in healing._EVENTS), 1)
            healing.observe(healthy, now=200)
            self.assertEqual(sum(x["kind"] == "repair-verified" for x in healing._EVENTS), 1)

    def test_normal_recovery_is_not_a_verified_self_repair(self):
        good = {
            "status": "ok", "reasons": [],
            "automaticCollection": {},
            "fibonacciMonitor": {},
            "strategyResearch": {},
        }
        bad = dict(good, status="degraded", reasons=["market-feed-not-current"])
        with patch.object(archive, "queue_event"):
            healing.observe(bad, now=100)
            healing.observe(bad, now=121)
            healing.observe(good, now=140)
            healing.observe(good, now=161)
        self.assertEqual(sum(x["kind"] == "detected" for x in healing._EVENTS), 1)
        self.assertEqual(sum(x["kind"] == "recovered" for x in healing._EVENTS), 1)
        self.assertFalse(any(x["kind"] == "repair-verified" for x in healing._EVENTS))


if __name__ == "__main__":
    unittest.main()
