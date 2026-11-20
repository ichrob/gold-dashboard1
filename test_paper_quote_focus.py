"""Only quote-refresh priority changes; no entry approvals or new network capacity."""
import copy
import unittest

import paper_simulation


class PaperQuoteFocusTests(unittest.TestCase):
    def setUp(self):
        self.products = [
            {'isin': 'SHORT1', 'productDirection': 'SHORT', 'name': 'Turbo Short'},
            {'isin': 'SHORT2', 'productDirection': 'SHORT', 'name': 'Turbo Short'},
            {'isin': 'SHORT3', 'productDirection': 'SHORT', 'name': 'Turbo Short'},
            {'isin': 'SHORT4', 'productDirection': 'SHORT', 'name': 'Turbo Short'},
            {'isin': 'LONG1', 'productDirection': 'LONG', 'name': 'Turbo Long'},
            {'isin': 'FACTOR', 'productDirection': 'SHORT', 'name': 'Faktor Short'},
            {'isin': 'KNOCK', 'productDirection': 'SHORT', 'name': 'Turbo Short',
             'knockedOut': True},
        ]
        self.base = dict(ready=True, priceFresh=True, direction='NEUTRAL')
    
    def test_confirmed_short_prepares_all_four_not_just_first_three(self):
        before = copy.deepcopy(self.products)
        side = paper_simulation.quote_focus(
            self.products, {**self.base, 'direction': 'SHORT'})
        self.assertEqual(side, ['SHORT1','SHORT2','SHORT3','SHORT4'])
        self.assertEqual(self.products, before)

    def test_neutral_intact_short_trend_prepares_without_entry(self):
        result = paper_simulation.quote_focus(self.products, {
            **self.base,
            'entryPreparation': {'direction': 'NEUTRAL'},
            'trendContext': {'available': True, 'intact': True,
                             'direction': 'SHORT'},
        })
        self.assertEqual(result, ['SHORT1','SHORT2','SHORT3','SHORT4'])
        self.assertEqual(self.base['direction'], 'NEUTRAL')

    def test_preparation_direction_has_priority_over_trend(self):
        self.assertEqual(
            paper_simulation.quote_focus(self.products, {
                **self.base, 'entryPreparation': {'direction': 'LONG'},
                'trendContext': {'available': True, 'intact': True,
                                 'direction': 'SHORT'}}),
            ['LONG1'])

    def test_unconfirmed_trend_or_stale_market_never_prewarmed(self):
        incomplete = {**self.base, 'trendContext': {
            'available': True, 'intact': False, 'direction': 'SHORT'}}
        self.assertEqual(paper_simulation.quote_focus(self.products, incomplete), [])
        incomplete['priceFresh'] = False
        self.assertEqual(paper_simulation.quote_focus(self.products, incomplete), [])
        incomplete['priceFresh'] = True
        incomplete['ready'] = False
        self.assertEqual(paper_simulation.quote_focus(self.products, incomplete), [])


if __name__ == '__main__':
    unittest.main()
