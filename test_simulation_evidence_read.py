"""Tests for bounded paper-case diagnostic projections."""
import unittest
import bob_diagnostics as diagnostics


class SimulationEvidenceTests(unittest.TestCase):
    def test_sample_counts_without_claiming_execution(self):
        sample = {"status": "observed", "accounts": [
            {"profile": "balanced", "status": "running",
             "recentCases": {"status": "observed", "items": [
                 {"status": "inconclusive", "events": [
                     {"kind": "data-gap"}, {"kind": "deferred-sale"}]},
                 {"status": "closed", "events": [{"kind": "stop"}]},
                 {"status": "open", "events": [{"kind": "entry"}]}
             ]}}
        ]}
        out = diagnostics.simulation_evidence_snapshot(sample)
        item = out["accountSamples"][0]
        self.assertEqual(item["sampleSize"], 3)
        self.assertEqual(item["counts"]["inconclusive"], 1)
        self.assertEqual(item["counts"]["closed"], 1)
        self.assertEqual(item["casesWithRecordedDataGap"], 1)
        self.assertEqual(item["casesWithRecordedDeferredSale"], 1)
        self.assertFalse(out["realOrders"])
        self.assertFalse(item["netProductReturnsVerified"])

    def test_empty_but_readable_weekend_recent_cases_do_not_raise_gap_warning(self):
        sample = {"status": "observed", "accounts": [
            {"profile": "trend800", "recentCases": {"status": "observed", "items": []}},
            {"profile": "normal1000nov", "recentCases": {"status": "observed", "items": []}}
        ]}
        out = diagnostics.simulation_evidence_snapshot(sample)
        review = out["gapReview"]
        self.assertEqual(review["status"], "no-recorded-gaps-in-sample")
        self.assertFalse(review["fullHistoricalGapCoverageVerified"])
        self.assertEqual(review["sampledDistinctGapInstants"], 0)
        self.assertEqual(out["accountSamples"][0]["sampleSize"], 0)
        self.assertFalse(out["realOrders"])

        sample["accounts"][1]["recentCases"]["status"] = "unavailable"
        partial = diagnostics.simulation_evidence_snapshot(sample)
        self.assertEqual(partial["gapReview"]["status"], "unavailable")
        self.assertEqual(partial["accountSamples"][1]["sampleStatus"], "unavailable")

    def test_missing_and_bounded_history(self):
        sample = {"status": "observed", "accounts": [
            {"profile": "conservative", "recentCases": {"status": "unavailable"}},
            {"profile": "offensive", "recentCases": {"status": "observed",
                "items": [{"status": "inconclusive", "events": []}] * 7}}
        ]}
        out = diagnostics.simulation_evidence_snapshot(sample)
        self.assertEqual(out["accountSamples"][0]["sampleStatus"], "unavailable")
        self.assertEqual(out["accountSamples"][1]["sampleSize"], 5)
        self.assertEqual(diagnostics.simulation_evidence_snapshot({})["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
