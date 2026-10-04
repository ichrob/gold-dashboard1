import json
import unittest
import investing_card as c


class InvestingCardTests(unittest.TestCase):
    def fixture(self):
        return dict(instrumentId='8830', instrument=dict(
            base=dict(id='8830', path='/commodities/gold', isCfd=True, isActive=True, isOpen=True),
            commodityData=dict(unit='_instr_unit_troy_ounce'),
            price=dict(currency='USD', last=4170.45, change=-1.65, changePcr=-.04,
                       isDelayed=False, lastUpdateTime='1791153271000')))

    def parse(self, state, age=10):
        body='<script id="__NEXT_DATA__">'+json.dumps(dict(props=dict(pageProps=dict(state=dict(commodityStore=state)))))+'</script>'
        return c.parse(body, 1791153271 + age)

    def test_original_time_and_provider_change(self):
        q=self.parse(self.fixture())
        self.assertEqual(q['at'], '2026-10-04T22:34:31+00:00')
        self.assertEqual(q['changePct'], -.04)
        self.assertTrue(q['realtimeCfd'])
        self.assertFalse(q['isExchangeRealtime'])

    def test_stale_closed_and_delayed_never_realtime(self):
        self.assertFalse(self.parse(self.fixture(), 121)['realtimeCfd'])
        for section, key, value in [('base', 'isOpen', False), ('price', 'isDelayed', True), ('price', 'isDelayed', None)]:
            state=self.fixture(); state['instrument'][section][key]=value
            self.assertFalse(self.parse(state)['realtimeCfd'])

    def test_bad_identity_time_and_price_rejected(self):
        for section, key, value in [('base','id','1'), ('base','isCfd',False),
                                   ('price','currency','EUR'), ('price','last',True),
                                   ('price','last',float('nan')), ('price','lastUpdateTime','00:34:31')]:
            state=self.fixture();state['instrument'][section][key]=value
            with self.assertRaises(ValueError):self.parse(state)
        with self.assertRaises(ValueError):self.parse(self.fixture(), -10)

    def test_absent_percentage_not_invented(self):
        state=self.fixture();del state['instrument']['price']['changePcr']
        self.assertIsNone(self.parse(state)['changePct'])


if __name__ == '__main__':unittest.main()
