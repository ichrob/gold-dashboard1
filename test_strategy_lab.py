import copy
import math
import unittest

import broker_bridge as broker
import strategy_lab as lab


def candles(n=940):
    """Closed, hourly, single-instrument fictitious OHLC, NOT financial evidence."""
    result = []
    last = 2000.
    for i in range(n):
        delta = 2*math.sin(i*.27) + .6*math.cos(i*.035) + .2
        price = last + delta
        result.append(dict(openTime=1700000000000 + i*3600000,
                           open=last, high=max(price,last)+1,
                           low=min(price,last)-1, close=price,
                           instrument="XAU/USD", isOpen=False))
        last = price
    return result


class WalkForwardResearchTests(unittest.TestCase):
    def test_time_splits_and_no_automatic_approval(self):
        r = lab.run(candles())
        self.assertEqual(r["status"], "evaluated")
        self.assertGreaterEqual(len(r["folds"]), 3)
        self.assertEqual(set(r["outOfSampleByStrategy"]), set(lab.STRATEGIES))
        self.assertFalse(r["approved"])
        self.assertFalse(r["orderExecutionEnabled"])
        for fold in r["folds"]:
            self.assertLess(fold["trainEndMs"], fold["validationStartMs"])
            self.assertLess(fold["validationStartMs"], fold["testStartMs"])
            self.assertLess(fold["testStartMs"], fold["testEndMs"])
            self.assertFalse(fold["selectionUsesTest"])
            self.assertIn(fold["selectedOnValidation"], lab.STRATEGIES)

    def test_future_prices_cannot_change_earlier_fold(self):
        original = candles()
        a = lab.run(original)
        mutated = copy.deepcopy(original)
        first_end = a["folds"][0]["testEndMs"]
        for b in mutated:
            if b["openTime"] > first_end + 2*3600000:
                b["open"] *= 1.2
                b["close"] *= 1.2
                b["high"] = max(b["open"],b["close"])+1
                b["low"] = min(b["open"],b["close"])-1
        b = lab.run(mutated)
        self.assertEqual(a["folds"][0], b["folds"][0])

    def test_missing_and_open_candles_never_invented(self):
        self.assertEqual(lab.run(candles(350))["status"], "insufficient")
        partial = candles(350)
        partial[-1]["isOpen"] = True
        self.assertEqual(lab.run(partial)["closedBars"], 349)
        duplicate = candles(650)
        duplicate.append(dict(duplicate[-1]))
        with self.assertRaises(ValueError):
            lab.run(duplicate)
        mixed = candles(650)
        mixed[2]["instrument"] = "GC=F"
        with self.assertRaises(ValueError):
            lab.run(mixed)
        broken = candles(650)
        broken[2]["high"] = broken[2]["low"]-1
        with self.assertRaises(ValueError):
            lab.run(broken)

    def test_no_trade_across_quote_gap(self):
        rows = candles(600)
        rows[550]["openTime"] += 3600000
        for j in range(551, len(rows)):
            rows[j]["openTime"] += 3600000
        result = lab.run(rows)
        self.assertEqual(result["status"], "evaluated")
        self.assertFalse(result["approved"])

    def test_costs_are_conservative_and_bounded(self):
        with self.assertRaises(ValueError):
            lab.run(candles(), -1)
        zero = lab.run(candles(), 0)
        high = lab.run(candles(), 80)
        self.assertLessEqual(
            high["outOfSampleByStrategy"]["baseline"]["meanFoldNetPct"],
            zero["outOfSampleByStrategy"]["baseline"]["meanFoldNetPct"])
        self.assertFalse(high["evidence"]["productNetValidated"])


class BrokerFailClosedTests(unittest.TestCase):
    def test_official_providers_unconnected(self):
        status = broker.status()
        self.assertEqual({item["id"] for item in status["brokers"]}, {"ibkr", "ig"})
        self.assertFalse(status["executionEnabled"])
        self.assertFalse(status["paperOrders"])
        for item in status["brokers"]:
            adapter = broker.BrokerAdapter(item["id"])
            with self.assertRaises(broker.LiveTradingDisabled):
                adapter.submit_order(isin="DE000FG309G0", quantity=10)
            with self.assertRaises(broker.LiveTradingDisabled):
                adapter.find_contract("DE000FG309G0")
            check = broker.instrument_check(item["id"], "DE000FG309G0")
            self.assertFalse(check["allowed"])
            self.assertIsNone(check["contractId"])

    def test_isin_format_and_checksum(self):
        self.assertEqual(broker.validate_isin("DE000FG309G0"), "DE000FG309G0")
        for value in ("DE000FG309G1", "DE000", "hello", "BE000FG4JXV7"):
            with self.assertRaises(ValueError):
                broker.validate_isin(value)


if __name__ == "__main__":
    unittest.main()
