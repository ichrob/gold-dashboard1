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

    def test_friday_close_cfd_stays_visible_without_false_stale_label(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest.mock import patch
        tz = ZoneInfo('Europe/Zurich')
        stamp = lambda day, hour, minute: datetime(2026, 10, day, hour, minute, tzinfo=tz).timestamp()
        friday = stamp(9, 23, 1)
        saturday = stamp(10, 6, 0)
        q = {'at': datetime.fromtimestamp(friday, ZoneInfo('UTC')).isoformat(),
             'price': 4200., 'realtimeCfd': False, 'note': 'CFD-Kurs nicht aktuell'}
        closed = c.aged(q, now=saturday)
        self.assertEqual(closed['note'], 'Markt geschlossen · letzter CFD-Kurs')
        self.assertFalse(closed['realtimeCfd'])
        self.assertEqual(c.aged(q, now=stamp(12, 0, 0))['note'], 'CFD-Kurs nicht aktuell')
        with patch.object(c, '_health', {'state': 'stale', 'sourceAt': q['at'], 'lastCheckedAt': friday}), patch.object(c.time, 'time', return_value=saturday):
            self.assertEqual(c.health()['state'], 'closed')
        # A source outage is still a genuine service error during the weekend.
        with patch.object(c, '_health', {'state': 'unavailable', 'sourceAt': q['at'], 'lastCheckedAt': friday}), patch.object(c.time, 'time', return_value=saturday):
            self.assertEqual(c.health()['state'], 'unavailable')

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

    def test_display_cfd_requires_explicit_december_identity_for_study(self):
        state=self.fixture()
        self.assertIsNone(self.parse(state)['declaredContract'])
        state['keyMetrics']=dict(month='Dez. 2026', settlement_day='2026-12-29T00:00:00Z', last_rollover_day='2026-08-27T00:00:00Z')
        self.assertEqual(self.parse(state)['declaredContract'], 'GCZ26')
        state['keyMetrics']['month']='Feb. 2027'
        self.assertIsNone(self.parse(state)['declaredContract'])


if __name__ == '__main__':unittest.main()
