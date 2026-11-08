import unittest
from datetime import datetime, timezone, timedelta

from degiro_manual_trade_handoff import (
    buy_handoff, sell_handoff, stop_update_handoff,
)
from trade_execution_readiness import build_review


NOW = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)
AT = (NOW - timedelta(seconds=20)).isoformat()


def approved_review():
    signal = dict(direction="LONG", ready=True, priceFresh=True,
                  at=AT, marketOpen=True)
    product = dict(isin="DE000FG4JXV7", direction="LONG",
                   underlying="XAU/USD", underlyingType="SPOT",
                   productType="TURBO", factorProduct=False, currency="EUR",
                   identityVerified=True, venueVerified=True,
                   koVerified=True, termsVerified=True, tradingOpen=True,
                   ko=3900, strike=3900, ratio=0.01, leverage=12,
                   koDistancePct=10, bidEUR=9.8, askEUR=10,
                   quoteAt=AT, quoteSource="Original-Emittent",
                   quoteKind="ISSUER_BID_ASK")
    risk = dict(cashEUR=1000, positionBudgetEUR=200,
                maxLossEUR=200, dailyLossEUR=0,
                dailyLossLimitEUR=250, expectedFeesEUR=5,
                openPositions=0, maxPositions=1,
                stopProductBidEUR=9, targetProductBidEUR=12,
                stopTargetVerified=True)
    return build_review(signal, product, risk, now=NOW)


def position():
    return dict(tradeId="trade-123", active=True, recordOnly=False, dir="LONG",
                product=dict(isin="DE000FG4JXV7", currency="EUR",
                             quantity=10, entry=10),
                purchase=dict(transactionId="receipt-123",
                              at="2026-11-09T14:00:00Z"))


class DegiroManualHandoffTests(unittest.TestCase):
    def test_valid_buy_never_triggers_broker_execution(self):
        ticket = buy_handoff(approved_review(), now=NOW)
        self.assertEqual(ticket["state"], "MANUAL_BUY_REVIEW")
        self.assertEqual(ticket["quantity"], 19)
        self.assertEqual(ticket["orderSide"], "BUY")
        self.assertEqual(ticket["currency"], "EUR")
        self.assertFalse(ticket["orderSubmitted"])
        self.assertFalse(ticket["executionConfirmed"])
        self.assertTrue(ticket["manualOnly"])
        self.assertEqual(ticket["reference"], approved_review()["reviewFingerprint"])

    def test_expired_or_unapproved_buy_has_no_order_details(self):
        old = NOW + timedelta(seconds=95)
        ticket = buy_handoff(approved_review(), now=old)
        self.assertEqual(ticket["state"], "BLOCKED")
        self.assertFalse(ticket["orderSubmitted"])
        self.assertNotIn("indicativeLimitEUR", ticket)
        for invalid in (dict(approved_review(), state="BLOCKED"),
                        dict(approved_review(), tradeApproved=True),
                        dict(approved_review(), orderSubmitted=True)):
            self.assertEqual(buy_handoff(invalid, now=NOW)["state"], "BLOCKED")

    def test_stop_tightening_only_against_confirmed_broker_stop(self):
        self.assertEqual(stop_update_handoff(position(), proposed_stop_eur=10,
            broker_confirmed_stop_eur=9, observed_bid_eur=12)["state"],
            "MANUAL_STOP_REVIEW")
        self.assertEqual(stop_update_handoff(position(), proposed_stop_eur=8,
            broker_confirmed_stop_eur=9, observed_bid_eur=12)["state"],
            "BLOCKED")
        self.assertEqual(stop_update_handoff(position(), proposed_stop_eur=10,
            broker_confirmed_stop_eur=None, observed_bid_eur=12)["state"],
            "BLOCKED")
        self.assertEqual(stop_update_handoff(position(), proposed_stop_eur=13,
            broker_confirmed_stop_eur=9, observed_bid_eur=12)["state"],
            "BLOCKED")

    def test_buy_receipt_required_stop_and_sell(self):
        unconfirmed = position()
        unconfirmed["purchase"] = {}
        self.assertEqual(stop_update_handoff(unconfirmed, proposed_stop_eur=10,
            broker_confirmed_stop_eur=9, observed_bid_eur=12)["state"],
            "BLOCKED")
        quote = dict(isin="DE000FG4JXV7", currency="EUR",
                     bidEUR=11, quoteAt=AT,
                     quoteKind="ISSUER_BID_ASK", source="Emittent")
        self.assertEqual(sell_handoff(unconfirmed, quote, exit_reason="target",
                                      now=NOW)["state"], "BLOCKED")

    def test_sell_needs_original_quote_and_confirmed_position(self):
        quote = dict(isin="DE000FG4JXV7", currency="EUR",
                     bidEUR=11, quoteAt=AT,
                     quoteKind="ISSUER_BID_ASK", source="Emittent")
        ticket = sell_handoff(position(), quote, exit_reason="target",
                              now=NOW)
        self.assertEqual(ticket["state"], "MANUAL_SELL_REVIEW")
        self.assertEqual(ticket["quantity"], 10)
        self.assertEqual(ticket["side"], "SELL")
        self.assertFalse(ticket["orderSubmitted"])
        self.assertFalse(ticket["executionConfirmed"])
        self.assertEqual(sell_handoff(position(), quote, quantity=3,
                            exit_reason="trend-reversal", now=NOW)["quantity"], 3)
        for changes in (dict(quote, quoteAt=(NOW-timedelta(seconds=91)).isoformat()),
                        dict(quote, isin="DE000FG4JXV1"),
                        dict(quote, quoteKind="MODEL"),
                        dict(quote, source="")):
            self.assertEqual(sell_handoff(position(), changes,
                exit_reason="stop", now=NOW)["state"], "BLOCKED")
        self.assertEqual(sell_handoff(position(), quote, quantity=11,
            exit_reason="manual", now=NOW)["state"], "BLOCKED")

    def test_closed_or_paper_trades_never_get_sell_handoff(self):
        q = dict(isin="DE000FG4JXV7", currency="EUR", bidEUR=11,
                 quoteAt=AT, quoteKind="ISSUER_BID_ASK", source="Emittent")
        for update in ({"active": False}, {"recordOnly": True}):
            self.assertEqual(sell_handoff(dict(position(), **update), q,
                             exit_reason="stop", now=NOW)["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
