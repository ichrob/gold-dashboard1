"""Read-only study diagnostics: historical debt is not a current incident."""
import unittest

from bob_diagnostics import new_studies_brief
from paper_profit_summary import entry_block_code

NOW = 1794834000000


def paper(checks, invalid=1112, quality_checked_at=NOW):
    quality = {
        "status": "collecting",
        "checkedAt": quality_checked_at,
        "studies": [{
            "id": "reaction", "cycles": 27322, "original": 26210,
            "invalid": invalid, "workerErrors": 0,
            "recentOriginalChecks": checks,
            "recentOriginalOutcomes": [],
        }],
        "modeledSimulation": {"status": "collecting", "studies": []},
    }
    return {
        "paper": {"sessionMode": "trading"},
        "qualityCampaign": quality,
        "shadowStudies": {"status": "observed", "studies": [],
                          "entryExitComparison": {"status": "collecting"}},
        "intradayTimingStudy": {"status": "collecting", "variants": []},
        "rapidLeverageStudy": {"status": "collecting"},
    }


def checks(n, *, invalid_indices=(), base=NOW):
    return [dict(at=base - (n-i)*30000, valid=i not in invalid_indices)
            for i in range(n)]


class RecentStudyDiagnosticsTests(unittest.TestCase):
    def test_historical_invalids_stay_visible_without_a_false_current_warning(self):
        observed = new_studies_brief(paper(checks(30)), NOW)
        reaction = observed["quality"]["studies"][0]
        recent = observed["quality"]["recentOriginalInput"]
        self.assertEqual(reaction["invalid"], 1112)
        self.assertEqual(reaction["cycles"], 27322)
        self.assertEqual(recent["status"], "observed")
        self.assertEqual(recent["invalidChecks"], 0)
        self.assertEqual(recent["sampledChecks"], 30)
        self.assertFalse(recent["currentInputAlert"])
        self.assertEqual(observed["attention"], [])
        self.assertEqual(observed["attentionStatus"], "no-current-study-alert")
        self.assertFalse(observed["realOrders"])

    def test_sustained_new_original_failures_trigger_a_recent_warning(self):
        bad = set(range(4, 16))
        observed = new_studies_brief(paper(checks(20, invalid_indices=bad)), NOW)
        self.assertEqual(observed["quality"]["recentOriginalInput"]["invalidChecks"], 12)
        self.assertIn("STUDY_ORIGINAL_INPUT_GAPS",
                      [x["code"] for x in observed["attention"]])
        self.assertIn("12/20", observed["attention"][0]["detail"])
        self.assertEqual(observed["attentionStatus"], "needs-attention")

    def test_old_or_missing_samples_never_count_as_proven_current_health(self):
        old = checks(20, invalid_indices=range(20), base=NOW - 30*60000)
        for values in (old, [], "private", [dict(at=NOW, valid="False")]):
            with self.subTest(values=values):
                d = new_studies_brief(paper(values), NOW)
                r = d["quality"]["recentOriginalInput"]
                self.assertEqual(r["status"], "insufficient-recent-evidence")
                self.assertFalse(r["currentInputAlert"])
                self.assertFalse(any(x["code"] == "STUDY_ORIGINAL_INPUT_GAPS"
                                     for x in d["attention"]))

    def test_inactive_worker_does_not_invent_new_source_failures(self):
        d = new_studies_brief(paper(checks(20, invalid_indices=range(20)),
                                    quality_checked_at=NOW-300000), NOW)
        self.assertFalse(d["quality"]["recentOriginalInput"]["currentInputAlert"])
        self.assertIn("STUDY_WORKER_OBSERVATION_STALE",
                      [x["code"] for x in d["attention"]])


class PaperMarketWaitClassifications(unittest.TestCase):
    def test_weak_trend_or_neutral_5m_are_known_waits(self):
        reasons = [
            "Einstieg wartet: Haupttrend geschwächt – Fortsetzung nicht bestätigt; kein bestätigter Ausstieg. · 5m-Kursindikatoren neutral oder widersprüchlich",
            "Einstieg wartet: Haupttrend SHORT intakt · Zeitebenen bestätigen die Richtung nicht: 15m-Setup neutral",
            "Einstieg wartet: Trendstärke schwach: zweite Schlusskerze zur Bestätigung erforderlich",
        ]
        self.assertEqual([entry_block_code(x) for x in reasons],
                         ["no-direction"]*3)

    def test_pullback_without_fresh_continuation_is_wait_not_fake_entry(self):
        self.assertEqual(entry_block_code(
            "Einstieg wartet: Haupttrend SHORT intakt · kurzfristiger Rücksetzer; Einstieg abwarten"),
            "plan-not-ready")
        self.assertEqual(entry_block_code("KO-Schutz: heutiger Nachweis fehlt"),
                         "knockout-protection")


if __name__ == "__main__":
    unittest.main()
