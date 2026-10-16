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

    def test_bnp_live_trading_and_audit_recovery(self):
        from degiro_product_audit import _backup_pair
        isin = 'DE000PJ9NB98'
        html = HTML.replace(ISIN, isin).replace(ISIN[5:11], isin[5:11]).replace('Société Générale', 'BNP Paribas').replace('LT Societe Generale', 'LT BNP Paribas')
        pair = q.parse_page(html, isin)
        self.assertEqual(pair['source'], 'comdirect · BNP LiveTrading')
        self.assertEqual(pair['upstream'], 'BNP')
        primary = dict(isin=isin, productVerified=True, found=True, eligible=False,
                       currency='EUR', source='BNP Paribas · Emittent OTC',
                       sourceUrl='https://derivate.bnpparibas.com/product-details/'+isin+'/',
                       metadata=dict(status=1))
        with patch.object(q, 'get_observation', return_value=dict(state='observed', quote=pair)):
            out = q.apply(primary, isin, self.now)
        self.assertEqual(_backup_pair(out, isin, self.now.timestamp()*1000), pair)
        self.assertEqual(out['analysisQuote'], pair)
        from leverage_backup import select_analysis_quote
        self.assertEqual(select_analysis_quote(out, self.now), pair)
        from degiro_product_audit import examine
        out.update(bid=5, ask=5.01, bidAt=(self.now-timedelta(minutes=3)).isoformat(),
                   askAt=(self.now-timedelta(minutes=3)).isoformat())
        item = examine(dict(isin=isin, direction='LONG'), out, self.now.timestamp()*1000)
        self.assertNotIn('quote-time', item['missing'])
        self.assertEqual(item['dataQuoteSource'], pair['source'])
        self.assertIsNone(_backup_pair(out, isin, (self.now+timedelta(seconds=91)).timestamp()*1000))
        self.assertFalse(out['eligible'])
        self.assertNotIn('leverageAt', out)
        for change in (dict(sourceUrl='https://example.com/'), dict(source='SG'),
                       dict(currency='CHF'), dict(metadata=dict(status=2))):
            self.assertIsNone(_backup_pair(dict(out, **change), isin, self.now.timestamp()*1000))
        with self.assertRaises(ValueError):
            q.parse_page(html.replace('LT BNP Paribas', 'LT Societe Generale'), isin)

    def test_currency_treatment_requires_explicit_matched_field(self):
        from comdirect_fields import parse_page
        for raw, expected in [('Nein', False), ('Ja', True)]:
            page=HTML.replace('gesichert Nein', 'gesichert '+raw)
            self.assertIs(parse_page(page, ISIN)['observations']['quanto']['value'], expected)
        self.assertNotIn('quanto', parse_page(HTML.replace('gesichert Nein', 'gesichert --'), ISIN)['observations'])

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

    def test_newer_comdirect_row_replaces_retained_secondary_with_original_clock(self):
        primary=copy.deepcopy(self.primary)
        primary['secondaryQuote']={**self.quote,'ask':7,'quoteAt':(self.now-timedelta(minutes=30)).isoformat()}
        out=self.apply(primary=primary)
        self.assertEqual(out['secondaryQuote'],self.quote)
        self.assertEqual(primary['secondaryQuote']['ask'],7)
        primary['secondaryQuote']={**self.quote,'ask':9,'quoteAt':(self.now+timedelta(seconds=30)).isoformat()}
        self.assertEqual(self.apply(primary=primary)['secondaryQuote']['ask'],9)

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

    def test_paper_harvests_completed_backup_while_primary_slots_are_busy(self):
        import paper_simulation as sim
        from concurrent.futures import Future
        from unittest.mock import Mock
        raw=copy.deepcopy(self.primary)
        raw.update(priceKind='issuer-chart',isExecutableQuote=False)
        raw['secondaryQuote']={**self.quote,'quoteAt':(self.now-timedelta(minutes=3)).isoformat()}
        before=copy.deepcopy(raw)
        busy={str(i):Future() for i in range(4)}
        pool=Mock()
        now=self.now.timestamp()*1000+30000
        with patch.object(sim,'_pool',pool),patch.object(sim,'_pending',busy), \
             patch.object(sim,'_quotes',{ISIN:raw}),patch.object(sim,'_requested',{}), \
             patch.object(q,'get_observation',return_value=dict(state='observed',quote=self.quote)), \
             patch.object(q,'datetime') as clock:
            clock.now.return_value=self.now+timedelta(seconds=30)
            clock.fromisoformat=datetime.fromisoformat
            clock.min=datetime.min
            result=sim.quote_cache([dict(isin=ISIN)],[],now)[ISIN]
        pool.submit.assert_not_called()
        accepted=sim.fresh_quote(result,now,ISIN)
        self.assertEqual(accepted['ask'],self.quote['ask'])
        self.assertEqual(accepted['quoteAt'],self.quote['quoteAt'])
        self.assertFalse(accepted['degiroExecutable'])
        self.assertEqual(raw,before)

    def test_expired_backup_has_specific_reason_and_still_blocks(self):
        import paper_simulation as sim
        raw=self.apply(120)
        raw.update(priceKind='issuer-chart',isExecutableQuote=False)
        now=self.now.timestamp()*1000+120000
        self.assertIsNone(sim.fresh_quote(raw,now,ISIN))
        self.assertIn('comdirect-Geld-/Briefkurs älter als 90 Sekunden',sim.quote_block_reason(raw,now,ISIN))


if __name__ == '__main__':
    unittest.main()
