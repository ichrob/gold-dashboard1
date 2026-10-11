"""Deterministic, offline evidence checks for Bob's Zukunft research."""
import copy
import math
import unittest
from datetime import datetime, timedelta, timezone

import zukunft_research as zr


def sample(n=430, side="LONG"):
    begin = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        # SYNTHETIC fixtures only: these MUST NOT enter a live or verified ledger.
        at = begin + timedelta(minutes=5*i)
        bid = round(1.10 + .22*math.sin(i*.21) + .01*math.sin(i*.07), 4)
        rows.append(dict(
            at=at.isoformat(), source_at=(at-timedelta(seconds=3)).isoformat(),
            bid_eur=bid, ask_eur=round(bid+.025, 4),
            underlying_usd=4000+40*math.sin(i*.2), score=85.0,
            trend=side, approved=True, market_open=True,
            bar_closed=True, quote_source="SYNTHETIC_TEST_ONLY",
            ko_distance_fraction=.20))
    return dict(schema="bob-zukunft-observed-v1", synthetic=False,
                realOrders=False, isin="DE000PJ9NCK0", side=side,
                costs=dict(fee_eur_per_side=0.0, slippage_bps=10.0,
                           financing_eur_per_day_per_unit=0.0),
                settings=dict(train_rows=180, test_rows=60, purge_rows=5,
                              min_train_trades=1, min_oos_trades=10),
                observations=rows)


class ResearchTests(unittest.TestCase):
    def test_research_never_is_broker_permission(self):
        r = zr.compare(sample())
        self.assertEqual(r["mode"], "RESEARCH_ONLY")
        self.assertFalse(r["realOrders"])
        self.assertFalse(r["qualified_for_live_trading"])
        self.assertEqual(len(r["folds"]), 3)
        self.assertEqual(set(r["totals"]), set(zr.STRATEGIES)|{"ml_shadow"})
        self.assertEqual(r["cost_assumptions"]["fee_eur_per_side"], 0)

    def test_duplicate_and_future_quote_are_rejected(self):
        data = sample()
        data["observations"][10]["at"] = data["observations"][9]["at"]
        with self.assertRaisesRegex(zr.EvidenceError, "chronological"):
            zr.compare(data)
        data = sample()
        data["observations"][10]["source_at"] = data["observations"][11]["at"]
        with self.assertRaisesRegex(zr.EvidenceError, "Future"):
            zr.compare(data)

    def test_cost_disclosure_and_trust_markers(self):
        for change in ({"costs": {}}, {"synthetic": True},
                       {"realOrders": True}, {"schema": "unknown"}):
            data = sample()
            data.update(change)
            with self.assertRaises(zr.EvidenceError):
                zr.compare(data)

    def test_stale_quotes_and_approval_block_entries(self):
        _, side, rows, cfg = zr.prepare(sample(60))
        for r in rows:
            r["approved"] = False
        result = zr.replay(rows, side, cfg, "baseline", 70, 0, len(rows))
        self.assertEqual(result["trades"], 0)
        for r in rows:
            r["approved"] = True
            r["source_at"] = r["at"]-400
        result = zr.replay(rows, side, cfg, "baseline", 70, 0, len(rows))
        self.assertEqual(result["trades"], 0)

    def test_oos_first_fold_immune_to_future_changes(self):
        d = sample()
        a = zr.compare(d)["folds"][0]
        altered = copy.deepcopy(d)
        for q in altered["observations"][320:]:
            q["score"] = 1
            q["trend"] = "NEUTRAL"
            q["bid_eur"] *= .8
            q["ask_eur"] *= .8
        b = zr.compare(altered)["folds"][0]
        self.assertEqual(a, b)

    def test_train_and_test_do_not_overlap(self):
        result = zr.compare(sample())["folds"]
        for i, f in enumerate(result):
            self.assertLess(f["train"][1], f["test"][0])
            if i:
                self.assertLess(result[i-1]["test"][1], f["test"][0])

    def test_no_fabricated_exit_on_unpriced_position(self):
        data = sample(80)
        _, side, rows, cfg = zr.prepare(data)
        # Constant rising quote: stop/target are unreachable, end position open.
        for i, q in enumerate(rows):
            q["bid"] = 1.0 + i*.001
            q["ask"] = q["bid"]+.02
        result = zr.replay(rows, side, cfg, "baseline", 70, 0, len(rows))
        self.assertFalse(result["complete"])
        self.assertEqual(result["trades"], 0)
        self.assertTrue(result["uncertain"])

    def test_ml_labels_only_from_training_window(self):
        _, side, rows, cfg = zr.prepare(sample())
        w, n = zr.fit_shadow(rows, side, 0, 180, cfg)
        for i in range(180, len(rows)):
            rows[i]["bid"] *= .8
            rows[i]["ask"] *= .8
        w2, n2 = zr.fit_shadow(rows, side, 0, 180, cfg)
        self.assertEqual((w, n), (w2, n2))

    def test_missing_candle_and_quote_provenance_are_refused(self):
        for field, value in (("bar_closed", False), ("quote_source", ""), ("trend", "?")):
            data = sample()
            data["observations"][4][field] = value
            with self.assertRaises(zr.EvidenceError):
                zr.compare(data)


if __name__ == "__main__":
    unittest.main()
