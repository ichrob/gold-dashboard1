import unittest
from datetime import datetime, timezone, timedelta
from android_telemetry import validate_report, PIN_RESULTS, BOOLS

class PinTelemetry(unittest.TestCase):
    def report(self):
        return dict(reportId='a'*32, observedAt=datetime.now(timezone.utc).isoformat(),
            appVersionCode=10315, lastCode='NONE', lastEventAt=None, **{k:False for k in BOOLS})
    def probe(self):
        return dict(runId='b'*32, endedAt=datetime.now(timezone.utc).isoformat(),
                    result='NO_WINDOW', completed=True)
    def test_legacy_reports_remain_valid(self):
        self.assertNotIn('pinProbe', validate_report(self.report()))
    def test_all_fixed_results_roundtrip_without_touching_product_code(self):
        for code in PIN_RESULTS:
            report=self.report(); report['pinProbe']={**self.probe(), 'result':code}
            self.assertEqual(validate_report(report)['pinProbe']['result'], code)
            self.assertEqual(validate_report(report)['lastCode'], 'NONE')
    def test_rejects_credentials_free_text_bad_types_and_stale_results(self):
        cases=[{**self.probe(), 'pin':'12345'}, {**self.probe(), 'screenText':'example'},
               {**self.probe(), 'result':'12345'}, {**self.probe(), 'completed':1},
               {**self.probe(), 'runId':'user'}, {**self.probe(), 'result':[]},
               {**self.probe(), 'endedAt':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}]
        for probe in cases:
            report=self.report(); report['pinProbe']=probe
            with self.subTest(probe=probe), self.assertRaises(ValueError):
                validate_report(report)
    def test_stopped_run_is_not_reported_as_completed(self):
        report=self.report(); report['pinProbe']={**self.probe(), 'completed':False}
        self.assertFalse(validate_report(report)['pinProbe']['completed'])

if __name__ == '__main__':
    unittest.main()
