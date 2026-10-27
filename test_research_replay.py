import copy
import os
import unittest
import uuid
from datetime import datetime,timezone
import research_replay as replay
import strategy_lab
import research_learning
from test_strategy_lab import candles


def fixture():
    rows=candles(700)
    report=research_learning.enrich(strategy_lab.run(rows),rows,{},day='2026-10-27')
    report['learningCycle']['checkpoint']='morning'
    return rows,report,replay.make(rows,{},'2026-10-27','morning',report)


class ReplayTests(unittest.TestCase):
    def test_roundtrip_recomputes_all_seven_strategies_and_learning_state(self):
        rows,report,envelope=fixture()
        restored=replay.replay(envelope)
        self.assertTrue(restored['matches'])
        self.assertEqual(restored['report'],report)
        self.assertEqual(len(report['outOfSampleByStrategy']),7)
        rows.clear()  # deleting the original working input cannot affect the package
        self.assertTrue(replay.replay(envelope)['matches'])

    def test_legacy_same_day_result_gets_new_package_instead_of_false_replay_claim(self):
        import strategy_lab_background as bg
        from zoneinfo import ZoneInfo
        rows,report,_=fixture()
        writes=[]
        def storage(action,payload):
            if action=='read':return dict(mode='RESEARCH_ONLY',automation={'lastDay':'2026-10-27'},latestReport=report)
            writes.append(payload)
            self.assertTrue(replay.replay(payload['replay'])['matches'])
            return dict(saved=True,day='2026-10-27')
        out=bg.evaluate_and_store(lambda *_:rows,lambda rows,*_:rows,
            now=datetime(2026,10,27,9,tzinfo=ZoneInfo('Europe/Zurich')),storage=storage)
        self.assertEqual(out['status'],'evaluated')
        self.assertEqual(len(writes),1)
        self.assertTrue(writes[0]['report']['replay']['available'])

    def test_tampering_and_engine_drift_are_not_silently_replayed(self):
        _,_,envelope=fixture()
        bad={**envelope,'id':'0'*64}
        with self.assertRaises(ValueError):replay.replay(bad)
        from unittest.mock import patch
        with patch.object(replay,'sources',return_value={}):
            with self.assertRaises(ValueError):replay.replay(envelope)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class ReplayDatabaseTests(unittest.TestCase):
    def test_durable_export_after_reconnect_and_expired_source_retention(self):
        import psycopg
        from psycopg import sql
        import bob_market_store
        url=os.environ['BOB_TEST_DATABASE_URL'];schema='replay_'+uuid.uuid4().hex
        _,report,envelope=fixture()
        with psycopg.connect(url) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                replay.init(conn);bob_market_store.init(conn)
                replay.save(conn,envelope,'2026-10-27',report)
                replay.save(conn,envelope,'2026-10-27',report)
                conn.execute("INSERT INTO bob_spot_observations VALUES (%s,'2020-01-01',1500)",(bob_market_store.STREAM,))
                bob_market_store.handle(conn,'write',dict(symbol='XAU',currency='USD',price=4000,at=datetime.now(timezone.utc).isoformat()))
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_spot_observations').fetchone()[0],2)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_research_replays').fetchone()[0],1)
                import candle_reliability as candles_store
                from test_ema200_history_backfill import candle_series
                candles_store.init(conn)
                bars=candle_series(3,step=60000)
                for bar in bars:bar['source']=candles_store.SOURCES['biquote']
                candles_store.handle(conn,'write',dict(key='biquote/1m',rows=bars))
                candles_store.handle(conn,'write',dict(key='biquote/1m',rows=bars))
                changed=copy.deepcopy(bars[-1:]);changed[0]['high']+=1
                candles_store.handle(conn,'write',dict(key='biquote/1m',rows=changed))
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_candle_evidence').fetchone()[0],4)
                # Source table can be absent: replay must depend only on frozen package.
                conn.execute('DROP TABLE bob_spot_observations');conn.commit()
                with psycopg.connect(url) as reopened:
                    reopened.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                    stored=replay.read(reopened,envelope['id'])
                    self.assertTrue(replay.replay(stored['replay'])['matches'])
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()
