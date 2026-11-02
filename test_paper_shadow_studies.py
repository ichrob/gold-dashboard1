"""Regression coverage for the independent, full-evidence shadow studies."""
import copy
import os
import unittest
from datetime import datetime, timezone
from contextlib import nullcontext
from unittest.mock import Mock

import paper_shadow_studies as shadow
from test_paper_ko_guard import NOW, ISIN, quote, choice, market as gold_market


def observed(at=NOW, direction="LONG", price=4000., adx=30.):
    # The exact same original timestamp must be present on the source, the
    # evaluator and an already-closed original 15m analysis bar.
    bar=(at//900000-1)*900000
    bundle=dict(spots=dict(spot_price_as_of=datetime.fromtimestamp(
        at/1000,timezone.utc).isoformat(),xaus=price,
        is_genuine_xauusd_spot=True,xaus_is_spot=True),
        history=dict(bars_by_tf=dict(
            **{"15m":[dict(openTime=bar,isOpen=False)]})))
    market=gold_market(price=price,at=at,direction=direction)
    market["analysisBarAt"]=bar
    market["context"]=dict(adx=adx,atr=8.,barAt=bar)
    market["dmi"]=dict(frames={"5m":{"direction":"SHORT"}})
    market["score"]=80 if direction=="LONG" else 0
    return bundle,market


class RecordingConnection:
    def __init__(self):
        self.calls=[]
    def execute(self,sql,params=()):
        self.calls.append((sql,params))
        return Mock(fetchone=lambda:None,fetchall=lambda:[])


class ShadowStudiesTests(unittest.TestCase):
    def test_original_input_is_strict_and_never_estimates(self):
        bundle,market=observed()
        self.assertTrue(shadow.original_input(bundle,market,NOW)["verified"])
        for change in ("future","missing-bar","open-bar","estimated-bar","mismatch","stale"):
            b=copy.deepcopy(bundle)
            m=copy.deepcopy(market)
            now=NOW
            if change=="future":now=NOW-1000
            if change=="missing-bar":b["history"]["bars_by_tf"]["15m"]=[]
            if change=="open-bar":b["history"]["bars_by_tf"]["15m"][0]["isOpen"]=True
            if change=="estimated-bar":b["history"]["bars_by_tf"]["15m"][0]["estimated"]=True
            if change=="mismatch":m["dataAt"]=NOW-5000
            if change=="stale":now=NOW+61000
            self.assertFalse(shadow.original_input(b,m,now)["verified"],change)

    def test_market_regime_is_a_prospective_paused_or_trade_hypothesis(self):
        bundle,market=observed()
        valid=shadow.original_input(bundle,market,NOW)
        decision=shadow.regime_decision(market,valid)
        self.assertEqual(decision["baseline"],"LONG")
        self.assertEqual(decision["candidate"],"LONG")
        market["context"]["adx"]=15.
        decision=shadow.regime_decision(market,valid)
        self.assertEqual(decision["baseline"],"LONG")
        self.assertEqual(decision["candidate"],"ABWARTEN")
        self.assertEqual(decision["regime"]["trend"],"sideways")

    def test_wait_does_not_change_live_neutral_decision(self):
        bundle,market=observed(direction="NEUTRAL")
        old=copy.deepcopy(market)
        decision=shadow.wait_decision(market,shadow.original_input(bundle,market,NOW))
        self.assertEqual(decision["baseline"],"ABWARTEN")
        self.assertEqual(decision["candidate"],"SHORT")
        self.assertFalse(decision["liveApproval"])
        self.assertEqual(old,market)

    def test_baseline_and_candidate_directions_scored_independently(self):
        case=dict(study="regime-routing",entryAt=NOW,entryPrice=4000.,
                  baseline="SHORT",candidate="ABWARTEN")
        observation=dict(sourceAt=NOW+shadow.HORIZON_MS+1000,
                         verified=True,price=3960.)
        result=shadow.price_signal_case(case,observation,NOW+shadow.HORIZON_MS+1000)
        self.assertEqual(result["candidatePct"],0)
        self.assertGreater(result["baselinePct"],0)
        self.assertLess(result["differencePct"],0)
        self.assertFalse(result["executableProductReturnVerified"])

    def test_missing_outcome_remains_inconclusive_never_profit(self):
        case=dict(study="wait-vs-enter",entryAt=NOW,entryPrice=4000.,
                  baseline="ABWARTEN",candidate="SHORT")
        self.assertIsNone(shadow.price_signal_case(case,dict(
            sourceAt=NOW+shadow.HORIZON_MS+1000,verified=False,
            price=3990.),NOW+shadow.HORIZON_MS+1000))
        result=shadow.price_signal_case(case,dict(
            sourceAt=NOW+shadow.HORIZON_MS+62000,verified=True,
            price=3990.),NOW+shadow.HORIZON_MS+62000)
        self.assertEqual(result["status"],"inconclusive-original-followup-missing")
        self.assertIsNone(result["candidatePct"])

    def test_signal_cases_never_backfill_or_duplicate_same_bar(self):
        conn=RecordingConnection()
        bundle,market=observed()
        quality=shadow.original_input(bundle,market,NOW)
        control=shadow.seed("regime-routing",NOW)
        decision=shadow.regime_decision(market,quality)
        shadow.update_signal_study(conn,control,"regime-routing",decision,quality,NOW)
        shadow.update_signal_study(conn,control,"regime-routing",decision,quality,NOW+30000)
        self.assertEqual(control["casesStarted"],1)
        self.assertEqual(len(control["openCases"]),1)
        good=dict(quality,sourceAt=NOW+shadow.HORIZON_MS,
                  price=4040.,verified=True)
        shadow.update_signal_study(conn,control,"regime-routing",decision,good,
                                   NOW+shadow.HORIZON_MS)
        self.assertEqual(control["casesPriced"],1)

    def test_product_requires_original_issuer_pair_and_safe_ko(self):
        conn=RecordingConnection()
        bundle,market=observed()
        quality=shadow.original_input(bundle,market,NOW)
        control=shadow.seed("product-e2e",NOW)
        product=quote()
        result=shadow.product_study(conn,control,quality,market,
                                    {"choices":[choice()]},{ISIN:product},NOW)
        self.assertEqual(result["state"],"observed-model-entry")
        self.assertIsNotNone(control["position"])
        self.assertLess(control["cash"],1000.)
        self.assertEqual(control["casesStarted"],1)
        self.assertFalse(control["position"]["brokerExecutionVerified"])
        control=shadow.seed("product-e2e",NOW)
        unsafe=quote(ko=3990.)
        result=shadow.product_study(conn,control,quality,market,
                                    {"choices":[choice()]},{ISIN:unsafe},NOW)
        self.assertIsNone(control["position"])
        self.assertEqual(result["reason"],"no-verified-product-bid-ask-ko")

    def test_no_fictitious_sale_without_new_dated_bid(self):
        conn=RecordingConnection()
        bundle,market=observed()
        quality=shadow.original_input(bundle,market,NOW)
        control=shadow.seed("product-e2e",NOW)
        shadow.product_study(conn,control,quality,market,
                             {"choices":[choice()]},{ISIN:quote()},NOW)
        self.assertIsNotNone(control["position"])
        market2=gold_market(price=4320.,at=NOW+120000)
        market2["analysisBarAt"]=quality["analysisBarAt"]
        quality2=dict(quality,sourceAt=NOW+120000,price=4320.,
                      verified=True)
        # Old bid cannot be used for an exit.
        out=shadow.product_study(conn,control,quality2,market2,
                                {},{ISIN:quote(NOW)},NOW+120000)
        self.assertEqual(out["state"],"exit-unpriced")
        self.assertIsNotNone(control["position"])
        self.assertEqual(control["casesPriced"],0)
        # A later datestamped bid is an explicit virtual model close.
        out=shadow.product_study(conn,control,quality2,market2,
                   {},{ISIN:quote(NOW+120000,bid=12.)},NOW+120000)
        self.assertEqual(out["state"],"observed-model-exit")
        self.assertIsNone(control["position"])
        self.assertEqual(control["casesPriced"],1)
        self.assertGreater(control["profit"],0)

    def test_stored_journal_is_append_only_and_reporting_not_execution(self):
        conn=RecordingConnection()
        shadow.init(conn)
        self.assertFalse(any("DELETE FROM" in sql or "TRUNCATE " in sql
                             for sql,_ in conn.calls))
        self.assertEqual(shadow.STUDIES,
                         ("regime-routing","wait-vs-enter","product-e2e"))


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "CI PostgreSQL integration")
class DatabaseTests(unittest.TestCase):
    def test_initialize_and_original_paper_snapshot_persist(self):
        import uuid
        import psycopg
        from psycopg import sql
        schema="paper_shadow_"+uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"]) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                shadow.init(conn)
                bundle,market=observed()
                shadow.tick(conn,bundle,market,{"choices":[]},{},NOW)
                result=shadow.report(conn)
                self.assertEqual(result["status"],"observed")
                self.assertEqual(len(result["studies"]),3)
                count=conn.execute("SELECT count(*) FROM bob_shadow_study_events").fetchone()[0]
                self.assertEqual(count,3)
                count=conn.execute("SELECT count(*) FROM bob_shadow_study_cases").fetchone()[0]
                self.assertEqual(count,1) # Regime study; no live product quote.
                conn.commit()
            finally:
                conn.rollback()
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
                conn.commit()


if __name__=="__main__":
    unittest.main()
