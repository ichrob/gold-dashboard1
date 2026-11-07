import json
import unittest

import paper_profit_summary as profit
import bob_diagnostics as diagnostics


class PaperProfitSummaryTests(unittest.TestCase):
    def test_existing_controls_are_ordered_and_not_verified_profit(self):
        rows = [
            dict(profile='normal1000oct', status='completed',
                 initialCapital=1000, equity=970, cash=970,
                 totalProfit=-30, realizedProfit=-30,
                 costsDebitedEur=3.75, checkedAt=1793993990000,
                 privateToken='DO-NOT-EXPOSE', isin='PRIVATE'),
            dict(profile='early1000oct', status='completed',
                 initialCapital=1000, equity=1025, cash=1025,
                 totalProfit=25, realizedProfit=25,
                 costsDebitedEur=4.50, checkedAt=1793993990000),
            dict(profile='trend800', status='completed',
                 initialCapital=800, equity=760, totalProfit=-40),
        ]
        original = json.dumps(rows, sort_keys=True)
        out = profit.snapshot(rows)
        self.assertEqual(json.dumps(rows, sort_keys=True), original)
        self.assertEqual([a['profile'] for a in out['rows']], list(profit.PROFILES))
        self.assertEqual(out['status'], 'partial')
        self.assertFalse(out['strategyWinnerConfirmed'])
        self.assertFalse(out['netProductReturnsVerified'])
        self.assertFalse(out['fullHistoryRead'])
        early = next(a for a in out['rows'] if a['profile']=='early1000oct')
        normal = next(a for a in out['rows'] if a['profile']=='normal1000oct')
        self.assertEqual(early['modelReturnPct'], 2.5)
        self.assertEqual(normal['modelReturnPct'], -3)
        self.assertEqual(early['exampleCostsDebitedEur'], 4.5)
        self.assertEqual(next(a for a in out['rows'] if a['profile']=='trend800')['modelReturnPct'], -5)
        self.assertNotIn('PRIVATE', json.dumps(out))
        self.assertNotIn('DO-NOT-EXPOSE', json.dumps(out))

    def test_missing_and_invalid_funds_never_become_zero_trades(self):
        missing = profit.snapshot(None)
        self.assertEqual(missing['status'], 'unavailable')
        self.assertFalse(missing['strategyWinnerConfirmed'])
        values = [dict(profile='early1000oct', initialCapital=1000,
                       equity=float('nan'), totalProfit=float('inf'),
                       costsDebitedEur='1', checkedAt=-100)]
        out = profit.snapshot(values)
        early = out['rows'][-2]
        self.assertIsNone(early['equityEur'])
        self.assertIsNone(early['modelProfitEur'])
        self.assertIsNone(early['exampleCostsDebitedEur'])
        self.assertIsNone(early['modelReturnPct'])
        self.assertIsNone(early['checkedAt'])
        self.assertIsNone(next(a for a in out['rows'] if a['profile']=='normal1000nov')['initialCapitalEur'])
        json.dumps(out, allow_nan=False)

    def test_visibility_survives_focused_and_bounded_reports(self):
        source = {'status': 'observed', 'accounts': [
            {'profile': 'trend800', 'initialCapital': 800,
             'equity': 700, 'totalProfit': -100}]}
        report = diagnostics.collect({'simulationAndPush': lambda: source})
        self.assertIn('paperProfitEvidence', report['areas'])
        focused = diagnostics.focused_report(report, 'simulation')
        self.assertIn('paperProfitEvidence', focused['areas'])
        self.assertFalse(focused['areas']['paperProfitEvidence']['strategyWinnerConfirmed'])
        reduced = diagnostics.bounded_report(report, 8000)
        self.assertIn('paperProfitEvidence', reduced['areas'])


if __name__ == '__main__':
    unittest.main()
