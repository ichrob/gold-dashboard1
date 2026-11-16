import os
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import Mock

import gold_api_research_service as g

NOW = int(datetime(2026,11,16,4,tzinfo=timezone.utc).timestamp())
ENV = {'BOB_GOLD_API_DAILY_ENABLED':'1','BOB_GOLD_API_COLLECTOR':'render-exclusive',
       'BOB_GOLD_API_SERVER_NOT_BEFORE':str(NOW-3600),'GOLD_API_KEY':'synthetic-test-key'}


def fixture(url, key):
    if '/history?' in url:
        return [{'day':'2026-11-13 00:00:00','avg_price':'4000.50'}]
    start,end=g.interval(date(2026,11,13))
    return dict(open=4000,high=4050,low=3950,close=4020,startTimestamp=start,endTimestamp=end)


class GoldServiceTests(unittest.TestCase):
    def test_missing_configuration_never_opens_database_or_provider(self):
        for missing in ENV:
            env={k:v for k,v in ENV.items() if k!=missing}
            factory=Mock();requester=Mock()
            out=g.run_once(factory,env=env,now=NOW,requester=requester)
            self.assertNotEqual(out['status'],'checked')
            factory.assert_not_called();requester.assert_not_called()

    def test_handoff_cooldown_is_enforced(self):
        factory=Mock()
        result=g.run_once(factory,env={**ENV,'BOB_GOLD_API_SERVER_NOT_BEFORE':str(NOW+1)},now=NOW)
        self.assertEqual(result['status'],'handoff-cooldown')
        factory.assert_not_called()

    def test_closed_weekday_and_settlement_delay(self):
        self.assertEqual(g.target_day(NOW),date(2026,11,13))
        self.assertEqual(g.target_day(int(datetime(2026,11,17,1,tzinfo=timezone.utc).timestamp())),date(2026,11,13))
        self.assertEqual(g.target_day(int(datetime(2026,11,17,3,tzinfo=timezone.utc).timestamp())),date(2026,11,16))

    def test_handoff_summary_does_not_read_missing_initial_table(self):
        conn=Mock()
        env={**ENV,'BOB_GOLD_API_SERVER_NOT_BEFORE':str(NOW+120)}
        result=g.summary(conn,env=env,now=NOW)
        self.assertEqual(result['status'],'handoff-cooldown')
        self.assertEqual(result['notBefore'],NOW+120)
        self.assertFalse(result['affectsLiveSignals'])
        conn.execute.assert_not_called()
        conn.transaction.assert_not_called()

    def test_scheduler_wakes_at_boundary_and_then_resumes_hourly(self):
        env={**ENV,'BOB_GOLD_API_SERVER_NOT_BEFORE':str(NOW+120)}
        self.assertEqual(g.next_delay(env=env,now=NOW),120)
        self.assertEqual(g.next_delay(env=env,now=NOW+119),1)
        self.assertEqual(g.next_delay(env=env,now=NOW+120),3600)
        self.assertEqual(g.next_delay(env=env,now=NOW-7200),3600)
        self.assertEqual(g.next_delay(env={},now=NOW),3600)

    def test_disabled_summary_is_read_free_and_never_contains_key(self):
        conn=Mock()
        result=g.summary(conn,env={})
        self.assertEqual(result['status'],'disabled')
        conn.execute.assert_not_called()
        self.assertFalse(result['affectsLiveSignals'])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI integration')
class GoldServiceDatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg, uuid
        self.pg=psycopg
        self.uri=os.environ['BOB_TEST_DATABASE_URL']
        self.schema='test_gold_daily_'+uuid.uuid4().hex
        with psycopg.connect(self.uri) as conn:
            conn.execute('CREATE SCHEMA '+self.schema)
        with self.factory() as conn:
            g.init(conn)

    @contextmanager
    def factory(self):
        with self.pg.connect(self.uri) as conn:
            conn.execute('SET search_path TO '+self.schema)
            yield conn

    def tearDown(self):
        with self.pg.connect(self.uri) as conn:
            conn.execute('DROP SCHEMA '+self.schema+' CASCADE')

    def test_concurrent_collectors_claim_once_and_persist_originals(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        calls=[];lock=threading.Lock()
        def request(url,key):
            # Another connection sees the committed reservation before HTTP.
            with self.factory() as conn:
                self.assertGreater(conn.execute('SELECT count(*) FROM bob_gold_daily_context').fetchone()[0],0)
            with lock: calls.append(url)
            return fixture(url,key)
        with ThreadPoolExecutor(max_workers=3) as executor:
            results=list(executor.map(lambda _:g.run_once(self.factory,env=ENV,now=NOW,requester=request),range(3)))
        self.assertEqual(len(calls),2)
        with self.factory() as conn:
            result=g.summary(conn,env=ENV,now=NOW)
            self.assertEqual(result['status'],'stored')
            self.assertEqual(result['items']['history-day']['averageUsd'],4000.5)
            self.assertAlmostEqual(result['items']['ohlc-range']['openCloseChangePct'],.5)
            original=conn.execute("SELECT original FROM bob_gold_daily_context WHERE mode='history-day'").fetchone()[0]
            self.assertEqual(original,fixture('/history?',None))
            self.assertEqual(g.summary(conn,env=ENV,now=NOW+86400)['status'],'stale')

    def test_failure_consumes_reservation_and_does_not_retry_on_restart(self):
        requester=Mock(side_effect=ValueError('secret must not escape'))
        g.run_once(self.factory,env=ENV,now=NOW,requester=requester)
        result=g.run_once(self.factory,env=ENV,now=NOW+60,requester=requester)
        self.assertEqual(requester.call_count,2)
        self.assertNotIn('secret',str(result))
        with self.factory() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_gold_daily_context').fetchone()[0],2)
            self.assertEqual(g.summary(conn,env=ENV,now=NOW)['status'],'incomplete')

    def test_account_budget_survives_restart_and_backward_clock(self):
        with self.factory() as conn:
            for i in range(8):
                self.assertTrue(g.claim(conn,date(2026,10,1+i),'history-day',NOW+20))
        requester=Mock()
        g.run_once(self.factory,env=ENV,now=NOW,requester=requester)
        requester.assert_not_called()


if __name__=='__main__':
    unittest.main()
