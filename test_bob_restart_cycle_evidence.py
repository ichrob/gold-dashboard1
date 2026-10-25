"""Goal #20: a restarted worker must produce a new successful cycle."""
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import bob_self_healing as healing


def health():
    return dict(status="ok", reasons=[],
                automaticCollection=dict(enabled=True,running=True,state="ready"),
                fibonacciMonitor=dict(configured=True,status="active"),
                strategyResearch=dict(enabled=True,running=True,phase="already-stored"))


class RestartOutcomeTests(unittest.TestCase):
    def setUp(self):
        for key in ("_LAST_ATTEMPTS","_RESTART_HISTORY","_PAUSE_LOGGED",
                    "_UNRESOLVED","_SUSPECT","_HEALTHY","_PENDING"):
            getattr(healing,key).clear()
        healing._EVENTS.clear()
        healing._ACTIVE=()

    def test_market_worker_running_without_fresh_post_restart_cycle_is_not_repaired(self):
        with patch.object(healing.bob_repair_store,"queue_event"):
            self.assertTrue(healing.restart_worker(
                "market-worker-stopped", True, lambda: None, now=100))
            start=healing._PENDING["market-worker-stopped"]["startedWall"]
            candidate=health()
            candidate["automaticCollection"]["lastCycleAt"] = datetime.fromtimestamp(
                start-2, timezone.utc).isoformat()
            healing.observe(candidate,now=101)
            healing.observe(candidate,now=123)
            self.assertIn("market-worker-stopped",healing.pending_codes())
            self.assertFalse(any(e["kind"]=="repair-verified" for e in healing._EVENTS))
            # A real successful cycle after the restart, not just thread-alive.
            healing._PENDING["market-worker-stopped"]["startedWall"] -= 1
            candidate["automaticCollection"]["lastCycleAt"] = datetime.now(
                timezone.utc).isoformat()
            healing.observe(candidate,now=130)
            healing.observe(candidate,now=151)
            self.assertNotIn("market-worker-stopped",healing.pending_codes())
            self.assertEqual(sum(e["kind"]=="repair-verified"
                                 for e in healing._EVENTS),1)

    def test_weekend_paused_cycle_can_never_confirm_market_restart(self):
        with patch.object(healing.bob_repair_store,"queue_event"):
            healing.restart_worker("market-worker-stopped",True,lambda:None,now=100)
            healing._PENDING["market-worker-stopped"]["startedWall"]-=1
            current=datetime.now(timezone.utc).isoformat()
            candidate=health()
            candidate["automaticCollection"].update(state="paused",lastCycleAt=current)
            healing.observe(candidate,now=110)
            healing.observe(candidate,now=140)
        self.assertIn("market-worker-stopped",healing.pending_codes())
        self.assertFalse(any(e["kind"]=="repair-verified" for e in healing._EVENTS))

    def test_background_paused_or_old_success_cannot_be_verification(self):
        with patch.object(healing.bob_repair_store,"queue_event"):
            healing.restart_worker("background-worker-stopped",True,lambda:None,now=100)
            healing._PENDING["background-worker-stopped"]["startedWall"]-=1
            candidate=health()
            candidate["fibonacciMonitor"].update(status="paused",lastSuccessAt=time.time())
            healing.observe(candidate,now=101)
            healing.observe(candidate,now=130)
            self.assertIn("background-worker-stopped",healing.pending_codes())
            candidate["fibonacciMonitor"].update(status="active",
                lastSuccessAt=(time.time()-900)*1000)
            healing.observe(candidate,now=151)
            self.assertIn("background-worker-stopped",healing.pending_codes())
            candidate["fibonacciMonitor"]["lastSuccessAt"]=time.time()
            healing.observe(candidate,now=160)
            healing.observe(candidate,now=181)
        self.assertNotIn("background-worker-stopped",healing.pending_codes())

    def test_research_worker_success_not_running_flag_or_stale_timestamp(self):
        with patch.object(healing.bob_repair_store,"queue_event"):
            healing.restart_worker("research-worker-stopped",True,lambda:None,now=100)
            healing._PENDING["research-worker-stopped"]["startedWall"]-=1
            candidate=health()
            healing.observe(candidate,now=101)
            healing.observe(candidate,now=122)
            self.assertIn("research-worker-stopped",healing.pending_codes())
            candidate["strategyResearch"]["lastSuccessAt"]=time.time()*1000
            healing.observe(candidate,now=130)
            healing.observe(candidate,now=152)
        self.assertNotIn("research-worker-stopped",healing.pending_codes())

    def test_invalid_naive_future_boolean_and_stale_times_fail_closed(self):
        code="market-worker-stopped"
        with patch.object(healing.bob_repair_store,"queue_event"):
            healing.restart_worker(code,True,lambda:None,now=100)
            healing._PENDING[code]["startedWall"]-=1
            invalid=(None,True,float("nan"),time.time()+90,
                     time.time()-1000,"2026-10-25T14:00:00",
                     "not-a-clock", datetime.now(timezone.utc).replace(
                          tzinfo=None).isoformat(),
                     (datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat())
            candidate=health()
            for stamp in invalid:
                candidate["automaticCollection"]["lastCycleAt"]=stamp
                self.assertFalse(healing.worker_healthy(code,candidate),
                                 msg=str(stamp))
            self.assertFalse(healing.worker_healthy("other-worker",candidate))


if __name__ == "__main__":
    unittest.main()
