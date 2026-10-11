import unittest
import ko_protection as ko


class KoProtectionTests(unittest.TestCase):
    def test_long_and_short_symmetric(self):
        for direction, barrier in [('LONG', 95.), ('SHORT', 105.)]:
            self.assertEqual(ko.assess(100., barrier, direction, 1.)['level'], 'safe')
            near = 98.5 if direction == 'LONG' else 101.5
            self.assertEqual(ko.assess(100., near, direction, 1.)['level'], 'critical')
            self.assertEqual(ko.assess(100., 100., direction, 1.)['level'], 'crossed')

    def test_warning_and_atr_buffer(self):
        warning = ko.assess(100., 98.2, 'LONG', .5)
        self.assertEqual(warning['level'], 'warning')
        self.assertEqual(warning['protectiveStopGold'], 99.2)
        self.assertEqual(ko.assess(100., 96., 'LONG', 3.)['level'], 'critical')
        self.assertEqual(ko.assess(100., 96., 'LONG', None)['level'], 'safe')

    def test_no_comparison_without_verified_basis(self):
        for values in [
            (100, 90, 'LONG', 1, 'GCZ26'),
            (100, 90, 'NEUTRAL', 1, 'XAU/USD'),
            (100, None, 'LONG', 1, 'XAU/USD'),
            (None, 90, 'LONG', 1, 'XAU/USD'),
        ]:
            self.assertEqual(ko.assess(*values)['level'], 'unknown')

    def test_invalid_atr_does_not_create_false_zero_distance(self):
        status = ko.assess(100, 98.9, 'LONG', float('nan'))
        self.assertEqual(status['level'], 'critical')
        self.assertIsNone(status['atrMultiple'])


if __name__ == '__main__':
    unittest.main()
