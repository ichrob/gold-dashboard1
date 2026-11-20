"""Regression: paper ledgers must not stop after three unusable products.

These tests use synthetic candidates only, no issuer requests or live trading.
"""
import copy
import unittest
from unittest.mock import patch

import paper_simulation as sim


NOW = 1795197600000


def candidate(isin, direction="SHORT", **updates):
    return dict(isin=isin, direction=direction, koGuardRequired=True,
                indicative=False, estimated=False, **updates)


class PaperRankedFallbackTests(unittest.TestCase):
    def test_verified_fourth_candidate_is_considered_without_changing_visible_three(self):
        visible = [candidate("PAPER-A"), candidate("PAPER-B"), candidate("PAPER-C")]
        fourth = candidate("PAPER-D")
        payload = {"choices": copy.deepcopy(visible),
                   "researchCandidates": copy.deepcopy(visible) + [fourth]}
        seen = sim.paper_entry_candidates(payload)
        self.assertEqual([x["isin"] for x in seen],
                         ["PAPER-A", "PAPER-B", "PAPER-C", "PAPER-D"])
        self.assertEqual(payload["choices"], visible)

        quotes = {"PAPER-D": {"isin": "PAPER-D", "ask": 11.0}}
        def fresh(raw, now, isin):
            return raw if raw and raw["isin"] == isin else None

        with patch.object(sim, "fresh_quote", side_effect=fresh), patch.object(
                sim.paper_ko_guard, "entry_reason", return_value=(None, {})):
            selected = sim.ranked_entry_candidate(
                seen, quotes, {"direction": "SHORT"}, NOW, 150.0, require_ko=True)
        self.assertEqual(selected["isin"], "PAPER-D")

    def test_extra_candidates_never_bypass_ko_guard_or_risk_budget(self):
        original = [candidate("PAPER-A")]
        extra = candidate("PAPER-D")
        seen = sim.paper_entry_candidates(
            {"choices": original, "researchCandidates": [extra]})
        quotes = {"PAPER-D": {"isin": "PAPER-D", "ask": 20.0}}
        with patch.object(sim, "fresh_quote", side_effect=lambda q, now, isin: q), patch.object(
                sim.paper_ko_guard, "entry_reason", return_value=("KO proof missing", None)):
            result = sim.ranked_entry_candidate(
                seen, quotes, {"direction": "SHORT"}, NOW, 100.0, require_ko=True)
        self.assertEqual(result["isin"], "PAPER-A")

        with patch.object(sim, "fresh_quote", side_effect=lambda q, now, isin: q), patch.object(
                sim.paper_ko_guard, "entry_reason", return_value=(None, {})):
            result = sim.ranked_entry_candidate(
                seen, quotes, {"direction": "SHORT"}, NOW, 10.0, require_ko=True)
        self.assertEqual(result["isin"], "PAPER-A")

    def test_unverified_extra_and_opposite_direction_are_not_selected(self):
        visible = [candidate("PAPER-A")]
        malformed = [
            {"isin": "NO-KO", "direction": "SHORT"},
            {"isin": "INDICATIVE", "direction": "SHORT", "koGuardRequired": True, "indicative": True},
            {"isin": "ESTIMATED", "direction": "SHORT", "koGuardRequired": True, "estimated": True},
            candidate("PAPER-A"), candidate("LONG-ONLY", direction="LONG"),
            candidate("PAPER-D"),
        ]
        selection = {"choices": visible, "researchCandidates": malformed}
        seen = sim.paper_entry_candidates(selection, blocked={"PAPER-D"})
        self.assertEqual([x["isin"] for x in seen], ["PAPER-A", "LONG-ONLY"])
        quotes = {"LONG-ONLY": {"isin": "LONG-ONLY", "ask": 1}}
        with patch.object(sim, "fresh_quote", side_effect=lambda q, now, isin: q), patch.object(
                sim.paper_ko_guard, "entry_reason", return_value=(None, {})):
            result = sim.ranked_entry_candidate(
                seen, quotes, {"direction": "SHORT"}, NOW, 100.0, require_ko=True)
        self.assertEqual(result["isin"], "PAPER-A")

    def test_bounded_candidate_list_and_missing_payload(self):
        self.assertEqual(sim.paper_entry_candidates(None), [])
        self.assertEqual(sim.paper_entry_candidates({"choices": "invalid"}), [])
        extras = [candidate("PAPER-" + str(i)) for i in range(25)]
        got = sim.paper_entry_candidates({"choices": [], "researchCandidates": extras})
        self.assertEqual(len(got), 12)
        self.assertEqual(got[-1]["isin"], "PAPER-11")


if __name__ == "__main__":
    unittest.main()
