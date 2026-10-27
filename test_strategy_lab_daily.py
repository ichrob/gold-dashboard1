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
                        latestReport=dict(status="evaluated",version=strategy_lab.VERSION,replay={"available":True}))
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
            return dict(saved=True,day="2026-10-12",replaySaved=True,replayId=payload.get("replay",{}).get("id"))
        with patch.object(bg.strategy_lab,"run",return_value=dict(
            status="insufficient",mode="RESEARCH_ONLY",approved=False,
            orderExecutionEnabled=False,closedBars=9,folds=[])) as engine:
            out=bg.evaluate_and_store(lambda *_:[dict(openTime=1)],
                                      lambda rows,mins:rows,
                                      now=datetime(2026,10,12,9,tzinfo=Z),storage=storage)
        self.assertEqual(out["status"],"insufficient")
        engine.assert_called_once()
        self.assertEqual([x[0] for x in calls],["read","write"])

    def hourly_archive(self, n=700, now=None):
        from test_strategy_lab import candles
        from candle_reliability import SOURCES
        now=now or datetime(2026,10,12,9,tzinfo=Z)
        rows=candles(n)
        end=int(now.timestamp()*1000)-3600000
        first=end-(n-1)*3600000
        for i,b in enumerate(rows):
            b["openTime"]=first+i*3600000
            b["source"]=SOURCES["xaus"]
        return rows

    def test_verified_hourly_archive_prevents_false_insufficient_research(self):
        import candle_reliability as candle
        now=datetime(2026,10,12,9,tzinfo=Z)
        archive=self.hourly_archive(700,now)
        short=[dict(b,source=candle.SOURCES["biquote"]) for b in archive[-168:]]
        with patch.object(candle,"_ROWS",{"xaus/1h":archive}):
            selected=bg.verified_hourly_research_archive(short,now=now)
            self.assertEqual(len(selected),700)
            self.assertEqual(selected[0]["source"],candle.SOURCES["xaus"])
            self.assertEqual(strategy_lab.run(short)["status"],"insufficient")
            self.assertEqual(strategy_lab.run(selected)["status"],"evaluated")
            stored=[]
            def storage(action,payload):
                if action=="read":return {"mode":"RESEARCH_ONLY","automation":{}}
                stored.append(payload)
                return {"saved":True,"day":"2026-10-12","replaySaved":True,"replayId":payload["replay"]["id"]}
            result=bg.evaluate_and_store(lambda *_:short,lambda rows,minutes:rows,
                                         now=now,storage=storage)
        self.assertEqual(result["status"],"evaluated")
        self.assertEqual(stored[0]["report"]["closedBars"],700)
        self.assertFalse(stored[0]["report"]["approved"])
        self.assertFalse(stored[0]["report"]["orderExecutionEnabled"])

    def test_hourly_archive_is_fail_closed_on_stale_conflicted_and_invalid_data(self):
        import candle_reliability as candle
        now=datetime(2026,10,12,9,tzinfo=Z)
        good=self.hourly_archive(700,now)
        short=[dict(b,source=candle.SOURCES["biquote"]) for b in good[-168:]]
        for variant in ("future", "mixed", "open", "wrong-instrument", "too-old",
                        "newer-primary", "short-archive"):
            data=[dict(b) for b in good]
            rows=[dict(b) for b in short]
            if variant=="future":data[-1]["openTime"]+=3600000
            elif variant=="mixed":data[12]["source"]=candle.SOURCES["biquote"]
            elif variant=="open":data[-1]["isOpen"]=True
            elif variant=="wrong-instrument":data[12]["instrument"]="GC=F"
            elif variant=="too-old":
                for b in data:b["openTime"]-=4*3600000
            elif variant=="newer-primary":rows[-1]["openTime"]+=3*3600000
            elif variant=="short-archive":data=data[-350:]
            with self.subTest(variant=variant),patch.object(candle,"_ROWS",{"xaus/1h":data}):
                self.assertIsNone(bg.verified_hourly_research_archive(rows,now=now))

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
        upsert = next(c.args[0] for c in conn.execute.call_args_list if "ON CONFLICT(run_day) DO UPDATE" in c.args[0])
        self.assertIn("ON CONFLICT(run_day) DO UPDATE",upsert)
        self.assertIn("status != 'evaluated' OR excluded.status = 'evaluated'",
                      upsert)
        conn.execute.reset_mock()
        conn.execute.return_value.fetchall.return_value=[]
        report=store.handle(conn,"read",{})
        self.assertIsNone(report["latestReport"])
        self.assertEqual(report["automation"]["history"],[])


if __name__=="__main__":unittest.main()
