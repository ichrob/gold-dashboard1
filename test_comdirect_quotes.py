import copy
from datetime import datetime, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

import comdirect_quotes as q

ISIN = 'DE000FG7N6Z2'
HTML = Path(__file__).with_name('test_fixtures').joinpath('comdirect_sg_quote.html').read_text()


class ComdirectQuoteTests(unittest.TestCase):
    def setUp(self):
        self.quote = q.parse_page(HTML, ISIN, datetime.fromisoformat('2026-10-14T05:00:00+00:00'))
        self.now = datetime.fromisoformat(self.quote['quoteAt'])
        self.primary = dict(isin=ISIN, productVerified=True, found=False,
                            eligible=False, fresh=False, currency='EUR',
                            metadata=dict(status=1, issuerExchangeCode='CBDE'))

    def apply(self, age=0, primary=None):
        with patch.object(q, 'get_observation', return_value=dict(state='observed', quote=self.quote)):
            return q.apply(primary or self.primary, ISIN, self.now+timedelta(seconds=age))

    def test_original_row_not_other_venue_or_fetch_clock(self):
        self.assertEqual((self.quote['bid'], self.quote['ask']), (5.43, 5.44))
        self.assertEqual(self.quote['quoteAt'], '2026-10-13T21:59:00+02:00')
        self.assertFalse(self.quote['isExecutableQuote'])

    def test_rejects_mismatches_missing_dates_delayed_and_crossed(self):
        for old, new in [('DE000FG7N6Z2', 'DE000FG8NHQ3'),
                         ('13.10.26', '--'), ('Realtime Kurs', 'Verzögerter Kurs'),
                         ('5,43', '6,43'), ('data-label="Brief"', 'data-label="Last"')]:
            with self.subTest(old=old), self.assertRaises((ValueError, KeyError)):
                q.parse_page(HTML.replace(old, new), ISIN)

    def test_current_analysis_never_promotes_execution(self):
        out = self.apply(60)
        self.assertEqual(out['analysisQuote']['bid'], 5.43)
        for flag in ('found', 'eligible', 'fresh'):
            self.assertFalse(out[flag])
        self.assertNotIn('analysisQuote', self.primary)

    def test_old_and_future_quotes_remain_historical(self):
        for age in (-1, 91, 86400):
            out = self.apply(age)
            self.assertNotIn('analysisQuote', out)
            self.assertEqual(out['comdirectQuoteBackup']['state'], 'stale')
            self.assertEqual(out['secondaryQuote']['quoteAt'], self.quote['quoteAt'])

    def test_newer_primary_observation_wins(self):
        primary = copy.deepcopy(self.primary)
        primary['analysisQuote'] = dict(askAt=(self.now+timedelta(seconds=30)).isoformat(), ask=9)
        self.assertEqual(self.apply(60, primary)['analysisQuote']['ask'], 9)

    def test_two_sg_routes_are_not_independent_confirmation(self):
        from degiro_product_audit import _market_cross_check
        common = dict(isinBound=True, current=True, currency='EUR',
                      bid=5.43, ask=5.44, bidAt=self.quote['bidAt'],
                      askAt=self.quote['askAt'], upstream='SG')
        result = _market_cross_check([
            dict(common, label='SG-Chart', source='SG · datierter Chartpunkt', venue=''),
            dict(common, label='Vorhandene Vergleichsquelle', source=self.quote['source'], venue=self.quote['venue'])])
        self.assertFalse(result['checked'])
        self.assertTrue(any('derselbe SG-Kursgeber' in r for r in result['reasons']))

    def test_paper_accepts_pair_without_claiming_broker_execution(self):
        import paper_simulation as sim
        raw = self.apply(60)
        before = copy.deepcopy(raw)
        now = (self.now+timedelta(seconds=60)).timestamp()*1000
        projected = sim.paper_quote(raw, now, ISIN)
        accepted = sim.fresh_quote(projected, now, ISIN)
        self.assertEqual(accepted['ask'], 5.44)
        self.assertEqual(accepted['bid'], 5.43)
        self.assertFalse(accepted['isExecutableQuote'])
        self.assertFalse(accepted['degiroExecutable'])
        self.assertIn('Simulationskurs', accepted['paperQuoteLabel'])
        self.assertFalse(projected['eligible'])
        self.assertEqual(accepted['quoteAt'], self.quote['quoteAt'])
        self.assertEqual(raw, before)
        # The ledger uses the observed ask, with no invented fill or midpoint.
        from test_paper_simulation import market
        case = sim.new_case(market(), dict(isin=ISIN), projected, now)
        self.assertEqual(case['entryAsk'], 5.44)
        self.assertEqual(case['quantity'], 18)
        self.assertIn('Simulationskurs', case['entryQuote']['paperQuoteLabel'])

    def test_paper_rejects_bad_secondary_evidence(self):
        import paper_simulation as sim
        now = self.now.timestamp()*1000
        for change in (dict(isin='wrong'), dict(currency='CHF'), dict(bid=None),
                       dict(ask=1), dict(delayed=True), dict(priceKind='issuer-chart'),
                       dict(venue='other'), dict(quoteAt=None),
                       dict(bidAt=(self.now-timedelta(seconds=91)).isoformat())):
            raw = copy.deepcopy(self.primary)
            raw['secondaryQuote'] = dict(self.quote, **change)
            self.assertIsNone(sim.fresh_quote(raw, now, ISIN), change)
        for age in (-1, 91):
            self.assertIsNone(sim.fresh_quote(self.apply(age), now+age*1000, ISIN))
        for change in (dict(sourceDisabled=True), dict(productVerified=False),
                       dict(metadata=dict(status=2, issuerExchangeCode='CBDE'))):
            self.assertIsNone(sim.fresh_quote(dict(self.apply(), **change), now, ISIN))

    def test_wrong_market_currency_inactive_and_disabled_do_not_fetch(self):
        for change in (dict(currency='CHF'), dict(sourceDisabled=True),
                       dict(metadata=dict(status=2, issuerExchangeCode='CBDE')),
                       dict(metadata=dict(status=1, issuerExchangeCode='CBSW'))):
            primary = dict(self.primary, **change)
            with patch.object(q, 'get_observation') as fetch:
                self.assertEqual(q.apply(primary, ISIN), primary)
                fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
