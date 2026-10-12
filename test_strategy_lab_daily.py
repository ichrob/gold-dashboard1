"""Automatic daily strategy comparison: trading-day gates, archive dedupe and failures."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch

import strategy_lab_background as bg
import strategy_lab_store as store
import strategy_lab

Z=ZoneInfo("Europe/Zurich")


class AutomaticResearchTests(unittest.TestCase):
    def test_weekday_8_am_not_weekend_or_night(self):
        self.assertIsNone(bg.trading_day(datetime(2026,10,12,7,59,tzinfo=Z)))
        self.assertEqual(bg.trading_day(datetime(2026,10,12,8,0,tzinfo=Z)),"2026-10-12")
        self.assertIsNone(bg.trading_day(datetime(2026,10,12,21,0,tzinfo=Z)))
        self.assertIsNone(bg.trading_day(datetime(2026,10,11,15,0,tzinfo=Z)))

    def test_already_saved_never_recomputes(self):
        calls=[]
        def storage(action,payload):
            calls.append(action)
            return dict(mode="RESEARCH_ONLY",automation=dict(lastDay="2026-10-12"),
                        latestReport=dict(status="evaluated",version=strategy_lab.VERSION))
        out=bg.evaluate_and_store(
            lambda *_:self.fail("recomputed despite saved daily snapshot"),
            lambda *_:self.fail("marked despite saved daily snapshot"),
            now=datetime(2026,10,12,9,tzinfo=Z),storage=storage)
        self.assertEqual(out["status"],"already-stored")
        self.assertEqual(calls,["read"])

    def test_background_writes_once_with_proof(self):
        calls=[]
        def storage(action,payload):
            calls.append((action,payload))
            if action=="read":
                return dict(mode="RESEARCH_ONLY",automation=dict(lastDay=None),latestReport=None)
            self.assertEqual(action,"write")
            self.assertEqual(payload["day"],"2026-10-12")
            self.assertFalse(payload["report"]["approved"])
            self.assertFalse(payload["report"]["orderExecutionEnabled"])
            return dict(saved=True,day="2026-10-12")
        with patch.object(bg.strategy_lab,"run",return_value=dict(
            status="insufficient",mode="RESEARCH_ONLY",approved=False,
            orderExecutionEnabled=False,closedBars=9,folds=[])) as engine:
            out=bg.evaluate_and_store(lambda *_:[dict(openTime=1)],
                                      lambda rows,mins:rows,
                                      now=datetime(2026,10,12,9,tzinfo=Z),storage=storage)
        self.assertEqual(out["status"],"insufficient")
        engine.assert_called_once()
        self.assertEqual([x[0] for x in calls],["read","write"])

    def test_storage_error_does_not_claim_success(self):
        def offline(*args):raise OSError("offline")
        with self.assertRaises(OSError):
            bg.evaluate_and_store(lambda *_:[],lambda *args:[],
                                  now=datetime(2026,10,12,9,tzinfo=Z),storage=offline)

    def test_archive_rejects_live_and_unverified_inputs(self):
        report = dict(mode="RESEARCH_ONLY",version=strategy_lab.VERSION,status="evaluated",
                      approved=False,orderExecutionEnabled=False,brokerConnected=False,
                      affectsLiveSignals=False,closedBars=650,
                      rangeMs=[1700000000000,1701000000000])
        with patch.object(store,"datetime",wraps=datetime) as dt:
            dt.now.return_value=datetime(2026,10,12,9,tzinfo=Z)
            valid=store.validate(dict(day="2026-10-12",report=report))
            self.assertEqual(str(valid[0]),"2026-10-12")
            for changes in (
                dict(approved=True),dict(orderExecutionEnabled=True),
                dict(brokerConnected=True),dict(affectsLiveSignals=True),
                dict(version="untrusted"),dict(status="adopted"),
            ):
                with self.subTest(changes=changes),self.assertRaises(ValueError):
                    store.validate(dict(day="2026-10-12",report={**report,**changes}))
            with self.assertRaises(ValueError):
                store.validate(dict(day="2026-10-13",report=report))
            with self.assertRaises(ValueError):
                store.validate(dict(day="2026-10-11",report=report))

    def test_database_write_is_idempotent_upsert_and_archive_read(self):
        conn=Mock()
        payload=dict(day="2026-10-12",report=dict(
            mode="RESEARCH_ONLY",version=strategy_lab.VERSION,status="evaluated",
            approved=False,orderExecutionEnabled=False,brokerConnected=False,
            affectsLiveSignals=False,closedBars=650,rangeMs=[1700000000000,1701000000000]))
        with patch.object(store,"datetime",wraps=datetime) as dt:
            dt.now.return_value=datetime(2026,10,12,9,tzinfo=Z)
            receipt=store.handle(conn,"write",payload)
        self.assertTrue(receipt["saved"])
        self.assertIn("ON CONFLICT(run_day) DO UPDATE",conn.execute.call_args_list[0].args[0])
        self.assertIn("status != 'evaluated' OR excluded.status = 'evaluated'",
                      conn.execute.call_args_list[0].args[0])
        conn.execute.reset_mock()
        conn.execute.return_value.fetchall.return_value=[]
        report=store.handle(conn,"read",{})
        self.assertIsNone(report["latestReport"])
        self.assertEqual(report["automation"]["history"],[])


if __name__=="__main__":unittest.main()
