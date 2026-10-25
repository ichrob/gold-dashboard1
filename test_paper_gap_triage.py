"""Paper gap evaluation must not invent an exit, lost trade, or root-cause proof."""
import json
import unittest
import paper_gap_triage as t
import bob_diagnostics


class PaperGapTriageTests(unittest.TestCase):
    @staticmethod
    def sample():
        clocks = [1000000, 2000000, 3000000, 4000000, 5000000]
        return (
            {"recentRecordedGapInstants": [
                {"recordedAt": x, "affectedVirtualCases": n, "reasonCodes": ["missing-current-market"]}
                for x, n in zip(clocks, (1, 2, 5, 1, 4))]},
            {"items": [
                {"eventAt": 1000000, "state": "nearby-original-observed",
                 "nearestSourceAt": 999500, "deltaSeconds": .5,
                 "timeRelation": "before-or-at-event"},
                {"eventAt": 2000000, "state": "nearby-original-observed",
                 "nearestSourceAt": 1995000, "deltaSeconds": 5,
                 "timeRelation": "before-or-at-event"},
                {"eventAt": 3000000, "state": "nearby-original-observed",
                 "nearestSourceAt": 3010000, "deltaSeconds": 10,
                 "timeRelation": "after-event"},
                {"eventAt": 4000000, "state": "no-original-observed-in-90s-window"},
                {"eventAt": 5000000, "state": "nearby-original-observed",
                 "nearestSourceAt": 5080000, "deltaSeconds": 80,
                 "timeRelation": "after-event"},
            ]},
            {"items": [
                {"eventAt": 3000000, "state": "nearby-15m-analysis-observed",
                 "analysisAt": 3000000, "timeRelation": "before-or-at-event", "deltaSeconds": 0,
                 "ready": False, "priceFresh": False},
                {"eventAt": 4000000, "state": "nearby-15m-analysis-observed",
                 "analysisAt": 4000000, "timeRelation": "before-or-at-event", "deltaSeconds": 0,
                 "ready": False, "priceFresh": False},
                {"eventAt": 5000000, "state": "nearby-15m-analysis-observed",
                 "analysisAt": 5000000, "timeRelation": "before-or-at-event", "deltaSeconds": 0,
                 "ready": False, "priceFresh": False},
            ]})

    def test_five_distinct_clocks_not_thirteen_independent_outages(self):
        result = t.assess(*self.sample())
        self.assertEqual(result["sampledDistinctGapInstants"], 5)
        self.assertEqual(sum(x["affectedVirtualCases"] for x in result["items"]), 13)
        self.assertEqual(result["counts"]["originalAtOrBeforeWithin60s"], 2)
        self.assertEqual(result["counts"]["originalAfterEventOnly"], 2)
        self.assertEqual(result["counts"]["noGoldApiOriginalIn90sWindow"], 1)
        self.assertEqual(result["counts"]["nearby15mNotReadyOrNotFresh"], 3)
        self.assertEqual(result["counts"]["reviewableInputHandoffCandidates"], 2)
        self.assertTrue(all(x["rootCauseVerified"] is False and
                            x["executedExitVerified"] is False and
                            x["profitOrLossVerified"] is False
                            for x in result["items"]))
        self.assertEqual(result["items"][2]["nextCheck"],
                         "never-backdate-later-original-observation")

    def test_same_clock_spot_with_analysis_ready_still_is_not_fill(self):
        correlation, spot, analysis = self.sample()
        analysis["items"].append({"eventAt": 1000000,
            "state": "nearby-15m-analysis-observed",
            "analysisAt": 1000000, "timeRelation": "before-or-at-event",
            "deltaSeconds": 0, "ready": True, "priceFresh": True})
        result = t.assess(correlation, spot, analysis)
        self.assertEqual(result["counts"]["reviewableInputHandoffCandidates"], 1)
        self.assertEqual(result["counts"]["nearby15mReadyFreshUnlinked"], 1)
        self.assertFalse(result["items"][0]["productBidVerified"])

    def test_mislabelled_future_original_cannot_invent_earlier_evidence(self):
        corr, spot, analysis = self.sample()
        # An observed price 5 seconds *after* the event cannot be rewritten as
        # before-or-at by changing only the descriptive archive label.
        spot["items"][0]["nearestSourceAt"] = 1005000
        spot["items"][0]["deltaSeconds"] = 5
        result = t.assess(corr, spot, analysis)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["counts"]["spotArchiveClockInconsistent"], 1)
        self.assertEqual(result["counts"]["reviewableInputHandoffCandidates"], 1)
        self.assertEqual(result["items"][0]["spotEvidence"], "spot-archive-clock-inconsistent")
        self.assertEqual(result["items"][0]["nextCheck"], "inspect-inconsistent-archive-clocks")
        self.assertFalse(result["items"][0]["executedExitVerified"])

    def test_future_healthy_analysis_must_not_retroactively_clear_gap(self):
        corr, spot, analysis = self.sample()
        analysis["items"].append({"eventAt": 1000000,
            "state": "nearby-15m-analysis-observed", "analysisAt": 1005000,
            "timeRelation": "after-event", "deltaSeconds": 5,
            "ready": True, "priceFresh": True})
        result = t.assess(corr, spot, analysis)
        self.assertEqual(result["counts"]["analysisOnlyAfterGap"], 1)
        self.assertEqual(result["counts"]["nearby15mReadyFreshUnlinked"], 0)
        self.assertEqual(result["counts"]["reviewableInputHandoffCandidates"], 2)
        self.assertEqual(result["items"][0]["analysisEvidence"],
                         "other-15m-analysis-only-after-gap-unlinked")
        self.assertFalse(result["items"][0]["rootCauseVerified"])

    def test_contradictory_worker_clock_withholds_profiles(self):
        corr, spot, analysis = self.sample()
        worker = {"items": [{"eventAt": 1000000,
            "state": "worker-input-captured-near-gap", "capturedAt": 1006000,
            "timeRelation": "before-or-at-event", "deltaSeconds": 6,
            "profiles": [{"profile": "balanced", "ready": True,
                          "priceFresh": True, "secret": "NO-LEAK"}]}]}
        result = t.assess(corr, spot, analysis, worker)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["counts"]["workerArchiveClockInconsistent"], 1)
        self.assertEqual(result["items"][0]["paperWorkerEvidence"],
                         "worker-archive-clock-inconsistent")
        self.assertIsNone(result["items"][0]["workerCapturedAt"])
        self.assertEqual(result["items"][0]["workerInputProfiles"], [])
        self.assertEqual(result["counts"]["reviewableInputHandoffCandidates"], 1)
        self.assertNotIn("NO-LEAK", json.dumps(result))

    def test_incorrect_source_distance_never_becomes_past_evidence(self):
        corr, spot, analysis = self.sample()
        spot["items"][0]["deltaSeconds"] = 0.001  # actual 0.5 seconds
        result = t.assess(corr, spot, analysis)
        self.assertEqual(result["counts"]["spotArchiveClockInconsistent"], 1)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["items"][0]["productBidVerified"])

    def test_missing_data_redacted_no_false_healthy_claim(self):
        result = t.assess({"recentRecordedGapInstants":[{"recordedAt": 42,
            "affectedVirtualCases": 1, "secret": "DO-NOT-EXPOSE"}]}, None, None)
        self.assertEqual(result["counts"]["spotArchiveUnavailableOrMissing"],1)
        self.assertEqual(result["status"], "observed")
        self.assertNotIn("DO-NOT-EXPOSE", json.dumps(result))
        self.assertFalse(result["items"][0]["rootCauseVerified"])

    def test_integration_reports_triage_only_as_hypothesis(self):
        corr, spot, analysis = self.sample()
        cases = [{
            "status": "inconclusive",
            "events": [{"kind": "data-gap", "recordedAt": row["recordedAt"],
                        "reason": "Aktuelle Goldkursabdeckung fehlt; kein belegter Ausstieg"},
                       {"kind": "deferred-sale"}],
            "secret": "NOT FOR REPORT"}
            for row in corr["recentRecordedGapInstants"]]
        sample = {"status": "observed", "accounts": [
            {"profile": "conservative",
             "recentCases": {"status": "observed", "items": cases}}],
            "spotGapArchive": spot, "analysisGapArchive": analysis}
        data = bob_diagnostics.simulation_evidence_snapshot(sample)
        self.assertEqual(data["gapReview"]["sampledDistinctGapInstants"], 5)
        self.assertEqual(data["gapReview"]["counts"]["reviewableInputHandoffCandidates"], 2)
        self.assertNotIn("NOT FOR REPORT", json.dumps(data))
        flags = bob_diagnostics.triage_snapshot({
            "background": {"status": "ok"},
            "simulationAndPush": sample,
            "simulationEvidence": data})
        findings = [x for x in flags["items"] if x["code"] == "PAPER_INPUT_HANDOFF_REVIEW"]
        self.assertEqual(len(findings), 1)
        self.assertFalse(findings[0]["repairVerified"])
        self.assertFalse(findings[0]["tradeApproval"])


if __name__ == "__main__":
    unittest.main()
