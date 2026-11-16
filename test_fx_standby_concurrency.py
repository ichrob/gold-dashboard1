import copy
import threading
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import fx_data as fx


class StandbyConcurrency(unittest.TestCase):
    def test_fresh_cache_readable_during_single_flight_network_refresh(self):
        now=datetime(2026, 11, 16, 13, tzinfo=timezone.utc)
        def quote(at):
            return dict(result='success',base='USD',rates={'EUR':.9,'CHF':.8},
                effective_at={'EUR':at.isoformat(),'CHF':at.isoformat()},
                data_updated_at=at.isoformat())
        cached=quote(now-timedelta(seconds=20))
        new=quote(now-timedelta(seconds=1))
        entered,release=threading.Event(),threading.Event()
        failures=[]
        def network(*args,**kwargs):
            entered.set()
            if not release.wait(3):raise AssertionError('Test refresh not released')
            return new
        def refresh():
            try:fx.warm_backup()
            except BaseException as exc:failures.append(exc)
        with patch.object(fx,'_standby',copy.deepcopy(cached)),\
             patch.object(fx,'_standby_attempted',float('-inf')),\
             patch.object(fx,'backup',side_effect=network) as fetch:
            worker=threading.Thread(target=refresh)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(fx.peek_backup(now),cached)
                self.assertIsNone(fx.warm_backup())
                self.assertEqual(fetch.call_count,1)
                # An in-flight refresh cannot make expired evidence fresh.
                self.assertIsNone(fx.peek_backup(now+timedelta(seconds=100)))
                read=fx.peek_backup(now)
                read['rates']['CHF']=999
                self.assertEqual(fx.peek_backup(now),cached)
            finally:
                release.set()
                worker.join(4)
            self.assertFalse(worker.is_alive())
            self.assertFalse(failures)
            self.assertEqual(fx.peek_backup(now),new)

    def test_failed_refresh_keeps_original_timestamp_and_releases_lock(self):
        now=datetime(2026,11,16,13,tzinfo=timezone.utc)
        cached=dict(result='success',base='USD',rates={'EUR':.9,'CHF':.8},
                    data_updated_at=now.isoformat(),
                    effective_at={'EUR':now.isoformat(),'CHF':now.isoformat()})
        with patch.object(fx,'_standby',copy.deepcopy(cached)),\
             patch.object(fx,'_standby_attempted',float('-inf')),\
             patch.object(fx,'backup',side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError):fx.warm_backup()
            self.assertEqual(fx.peek_backup(now),cached)
            self.assertTrue(fx._warm_lock.acquire(blocking=False))
            fx._warm_lock.release()
