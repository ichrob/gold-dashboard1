import threading
import unittest
from unittest.mock import patch,Mock
import auxiliary_workers as aux
import bob_self_healing as sh
import bob_issue_watchdog as watchdog
import product_comparison_worker as comparison

class RepairTests(unittest.TestCase):
    def setUp(self):
        for value in (sh._LAST_ATTEMPTS,sh._RESTART_HISTORY,sh._PAUSE_LOGGED,sh._PENDING,
                      sh._UNRESOLVED,sh._SUSPECT,sh._HEALTHY,sh._EVENTS):value.clear()
        self.events=patch('bob_repair_store.queue_event').start();self.addCleanup(patch.stopall)

    def test_restart_budget_stops_storm_and_later_allows_retry(self):
        start=Mock()
        for now in (100,281,462):self.assertTrue(sh.restart_worker('cfd-worker-stopped',True,start,now=now))
        for now in (643,824):self.assertFalse(sh.restart_worker('cfd-worker-stopped',True,start,now=now))
        self.assertEqual(start.call_count,3)
        self.assertEqual(sum(e['kind']=='repair-failed' for e in sh._EVENTS),1)
        self.assertTrue(sh.restart_worker('cfd-worker-stopped',True,start,now=1901))

    def test_restart_needs_new_completed_work_not_old_success(self):
        code='cfd-worker-stopped'
        with patch.object(sh.time,'time',return_value=1000):
            sh.restart_worker(code,True,lambda:None,now=100)
        def observe(at,wall,mono):
            health={'auxiliaryWorkers':{code:dict(running=True,successfulAt=at,state='current')}}
            with patch.object(sh.time,'time',return_value=wall):sh.observe(health,now=mono)
        observe(999,1001,101);observe(999,1022,122)
        self.assertIn(code,sh.pending_codes())
        observe(1023,1024,124);observe(1023,1045,145)
        self.assertIn(code,sh.pending_codes())
        observe(1054,1055,155)
        self.assertNotIn(code,sh.pending_codes())
        self.assertTrue(any(e['kind']=='repair-verified' for e in sh._EVENTS))
        self.assertNotIn(code,sh._RESTART_HISTORY)

    def test_live_threads_not_restarted_and_disabled_is_noop(self):
        with patch.object(aux,'health',return_value={c:dict(running=c!='cfd-worker-stopped') for c in aux.CODES}), \
             patch('investing_card.start') as cfd,patch('spot_daily_change.start') as spot,patch('future_comparison.start') as future:
            aux.maintain(False);cfd.assert_not_called()
            aux.maintain(True);cfd.assert_called_once();spot.assert_not_called();future.assert_not_called()

    def test_failed_start_does_not_block_other_worker(self):
        with patch.object(aux,'health',return_value={c:dict(running=False) for c in aux.CODES}), \
             patch('investing_card.start',side_effect=OSError('private')),patch('spot_daily_change.start') as spot,patch('future_comparison.start') as future:
            aux.maintain(True);spot.assert_called_once();future.assert_called_once()
        self.assertNotIn('private',str(sh._EVENTS))

    def test_initial_start_only_missing_workers(self):
        with patch('investing_card.health', return_value={'running': True}), \
             patch('spot_daily_change.health', return_value={'running': False}), \
             patch('future_comparison.health', return_value={'running': True}), \
             patch('investing_card.start') as cfd, \
             patch('spot_daily_change.start') as spot, \
             patch('future_comparison.start') as comparison:
            state=aux.start_initial(True)
            self.assertEqual(state[aux.CODES[0]],'already-running')
            self.assertEqual(state[aux.CODES[1]],'start-attempted')
            cfd.assert_not_called()
            spot.assert_called_once_with()
            comparison.assert_not_called()

    def test_initial_failure_is_isolated_and_disabled_is_inert(self):
        with patch('investing_card.health', side_effect=OSError('secret')), \
             patch('spot_daily_change.health', return_value={'running': False}), \
             patch('future_comparison.health', return_value={'running': False}), \
             patch('investing_card.start') as cfd, \
             patch('spot_daily_change.start') as spot, \
             patch('future_comparison.start') as future:
            self.assertEqual(aux.start_initial(False)[aux.CODES[0]], 'disabled')
            status=aux.start_initial(True)
            self.assertEqual(status[aux.CODES[0]],'start-failed')
            self.assertEqual(status[aux.CODES[1]],'start-attempted')
            self.assertEqual(status[aux.CODES[2]],'start-attempted')
            cfd.assert_not_called()
            spot.assert_called_once_with()
            future.assert_called_once_with()

    def test_pending_repair_not_closed_when_thread_only_alive(self):
        code='cfd-worker-stopped'
        result=watchdog.classify({'status':'ok','repairPendingCodes':[code,'secret'],
             'auxiliaryWorkers':{code:{'running':True}}},{'status':'ok'},
             {'ok':True,'productAuditCodes':[]},market_open=False)
        self.assertIn(code,result);self.assertNotIn('secret',result)

    def test_comparison_thread_start_failure_releases_lock(self):
        lock=threading.Lock()
        with patch.object(comparison,'_lock',lock),patch.object(comparison,'_last',0), \
             patch.object(comparison.time,'monotonic',return_value=100), \
             patch.object(comparison.threading,'Thread') as thread:
            thread.return_value.start.side_effect=RuntimeError('cannot start')
            comparison.enqueue(None,{})
            self.assertFalse(lock.locked());self.assertEqual(comparison._last,0)
            comparison.enqueue(None,{})
            self.assertEqual(thread.return_value.start.call_count,2)

if __name__=='__main__':unittest.main()
