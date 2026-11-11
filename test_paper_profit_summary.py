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
        early = next(a for a in out['rows'] if a['profile']=='early1000oct')
        self.assertIsNone(early['equityEur'])
        self.assertIsNone(early['modelProfitEur'])
        self.assertIsNone(early['exampleCostsDebitedEur'])
        self.assertIsNone(early['modelReturnPct'])
        self.assertIsNone(early['checkedAt'])
        self.assertIsNone(next(a for a in out['rows'] if a['profile']=='normal1000nov')['initialCapitalEur'])
        json.dumps(out, allow_nan=False)

    def test_november_blockers_are_classified_without_leaking_private_reasons(self):
        self.assertEqual(profit.entry_block_code('Goldkurs nicht aktuell bestätigt; Quellenzeit prüfen'),
                         'source-not-fresh')
        self.assertEqual(profit.entry_block_code('KO-Schutz: Barriere fehlt'),
                         'knockout-protection')
        self.assertEqual(profit.entry_block_code('ABWARTEN: keine bestätigte Richtung'),
                         'no-direction')
        self.assertEqual(profit.entry_block_code(
            'Einstieg wartet: Preis über 1,5 ATR von EMA20 in Trendrichtung entfernt'),
            'ema-stretch')
        self.assertEqual(profit.entry_block_code(
            'Einstieg wartet: Bestätigtes Einstiegssignal älter als 15 Minuten'),
            'signal-age')
        self.assertEqual(profit.entry_block_code(
            'Einstieg wartet: Preis über 1,5 ATR von EMA20 in Trendrichtung entfernt'
            ' · Bestätigtes Einstiegssignal älter als 15 Minuten'),
            'ema-stretch-and-signal-age')
        out = profit.snapshot([
            dict(profile='trend800nov',initialCapital=800,equity=800,
                 reason='Geld-/Briefkurs nicht freigegeben · ISIN PRIVATE-TOKEN'),
            dict(profile='normal1000nov',initialCapital=1000,equity=1000,
                 reason='ABWARTEN: keine bestätigte Richtung')])
        by_id={a['profile']:a for a in out['rows']}
        self.assertEqual(by_id['trend800nov']['latestEntryBlockCode'],'product-quote-missing')
        self.assertEqual(by_id['normal1000nov']['latestEntryBlockCode'],'no-direction')
        self.assertNotIn('PRIVATE-TOKEN',json.dumps(out))
        self.assertFalse(out['netProductReturnsVerified'])
        night = profit.snapshot([dict(profile='trend800nov',
            initialCapital=800,equity=800,
            status='night-paused',reason='DEGIRO-Nachtmodus · Simulation pausiert',
            lastTradingEntryBlockCode='product-quote-missing',
            lastTradingEntryBlockAt=1794360000000)])
        row = next(x for x in night['rows'] if x['profile']=='trend800nov')
        self.assertEqual(row['latestEntryBlockCode'],'product-quote-missing')
        self.assertEqual(row['latestEntryBlockAt'],1794360000000)
        malformed = profit.snapshot([dict(profile='trend800nov',
            initialCapital=800,equity=800,
            lastTradingEntryBlockCode='PRIVATE_TOKEN',
            reason='DEGIRO-Nachtmodus · Simulation pausiert')])
        self.assertEqual(next(x for x in malformed['rows'] if
            x['profile']=='trend800nov')['latestEntryBlockCode'],'not-observed')
        self.assertNotIn('PRIVATE_TOKEN',json.dumps(malformed))
        night_without_trade = profit.snapshot([dict(
            profile='normal1000nov', initialCapital=1000, equity=1000,
            status='night-paused',
            reason='DEGIRO-Produkte nachts nicht handelbar · Simulation pausiert')])
        night_row = next(x for x in night_without_trade['rows']
                         if x['profile'] == 'normal1000nov')
        self.assertEqual(night_row['latestEntryBlockCode'], 'not-observed')
        self.assertIsNone(night_row['latestEntryBlockAt'])


    def test_live_push_projection_keeps_last_trading_block_without_private_text(self):
        # Regression: the paper ledger stores the block, but the private
        # read-only push projection previously omitted both persisted fields.
        from unittest.mock import patch
        import report_admission
        import decision_audit

        controls = {
            'trend800nov': {
                'status': 'night-paused',
                'reason': 'DEGIRO-Nachtmodus · Simulation pausiert',
                'initialCapital': 800, 'equity': 800,
                'lastTradingEntryBlockCode': 'ema-stretch-and-signal-age',
                'lastTradingEntryBlockAt': 1794343500000,
                'privateToken': 'NEVER_EXPOSE_THIS'
            },
            'normal1000nov': {
                'status': 'night-paused',
                'reason': 'DEGIRO-Nachtmodus · Simulation pausiert',
                'initialCapital': 1000, 'equity': 1000,
                'lastTradingEntryBlockCode': 'SECRET_INSTEAD_OF_ENUM',
                'lastTradingEntryBlockAt': float('nan')
            }
        }

        class Cursor:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class Connection:
            def execute(self, sql):
                if 'FROM subscriptions' in sql:
                    return Cursor((0, 0))
                for profile, control in controls.items():
                    if 'FROM paper_control_' + profile in sql:
                        return Cursor((control,))
                raise AssertionError('Unexpected SQL in read-only projection')

        class Portfolios:
            POLICIES = {'trend800nov': {}, 'normal1000nov': {}}

            @staticmethod
            def names(profile):
                return {'bob_paper_control': 'paper_control_' + profile}

        class PaperHealth:
            @staticmethod
            def snapshot(_):
                return {'state': 'paused'}

        class Evaluator:
            @staticmethod
            def status():
                return {'completed': 0, 'failed': 0}

        with patch.object(report_admission, 'status', return_value={}), \
             patch.object(decision_audit, 'prospective_query_probe', return_value={}):
            report = diagnostics.push_snapshot(
                Connection(), Evaluator(), PaperHealth(), Portfolios(),
                extended=False)

        self.assertEqual(len(report['accounts']), 2)
        observed = next(a for a in report['accounts'] if a['profile'] == 'trend800nov')
        self.assertEqual(observed['lastTradingEntryBlockCode'], 'ema-stretch-and-signal-age')
        self.assertEqual(observed['lastTradingEntryBlockAt'], 1794343500000)
        invalid = next(a for a in report['accounts'] if a['profile'] == 'normal1000nov')
        self.assertNotIn('lastTradingEntryBlockCode', invalid)
        self.assertNotIn('lastTradingEntryBlockAt', invalid)
        visible = profit.snapshot(report['accounts'])
        row = next(a for a in visible['rows'] if a['profile'] == 'trend800nov')
        self.assertEqual(row['latestEntryBlockCode'], 'ema-stretch-and-signal-age')
        self.assertEqual(row['latestEntryBlockAt'], 1794343500000)
        self.assertNotIn('NEVER_EXPOSE_THIS', json.dumps(visible))
        self.assertNotIn('SECRET_INSTEAD_OF_ENUM', json.dumps(visible))
        self.assertFalse(visible['netProductReturnsVerified'])
        self.assertFalse(visible['strategyWinnerConfirmed'])

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
