import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import fx_data as f

class FxFailoverTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,8,16,0,tzinfo=timezone.utc)
        self.at=(self.now-timedelta(seconds=20)).isoformat()
        self.primary=dict(result='success',base='USD',rates=dict(EUR=.9,CHF=.8),
            effective_at=dict(EUR=self.at,CHF=self.at),data_updated_at=self.at,
            source='live',sources=dict(EUR='live',CHF='live'),market_session='open')
    def tick(self,symbol):
        return dict(symbol=symbol,bid=1.1 if symbol=='EURUSD' else .8,
            ask=1.1 if symbol=='EURUSD' else .8,lastQuoteAt=self.at,
            timestamp=self.now.isoformat(),stale=False,marketState='open')
    def test_fresh_primary_no_backup(self):
        fetch=Mock(return_value=self.primary)
        self.assertEqual(f.fetch_rates(fetch,now=self.now)['rates']['EUR'],.9)
        self.assertEqual(fetch.call_count,1)
    def test_stale_primary_switch_and_inversion(self):
        old=(self.now-timedelta(minutes=16)).isoformat()
        self.primary.update(data_updated_at=old,effective_at=dict(EUR=old,CHF=old))
        def fetch(url,*a,**kw):
            return self.primary if 'exchangerate' in url else self.tick(url.rsplit('/',1)[1])
        out=f.fetch_rates(fetch,now=self.now)
        self.assertTrue(out['backupActive'])
        self.assertAlmostEqual(out['rates']['EUR'],1/1.1)
        self.assertEqual(out['effective_at']['EUR'],self.at)
    def test_all_down_retain_original_clock(self):
        out=f.fetch_rates(Mock(side_effect=OSError('offline')),self.primary,self.now)
        self.assertEqual(out['data_updated_at'],self.at)
        self.assertEqual(len(out['fetchDiagnostics']),2)
    def test_reject_stale_wrong_future_closed_crossed(self):
        for change in [dict(lastQuoteAt=(self.now-timedelta(minutes=6)).isoformat()),
                       dict(lastQuoteAt=(self.now+timedelta(seconds=1)).isoformat()),
                       dict(symbol='XAUUSD'),dict(stale=True),dict(marketState='closed'),
                       dict(bid=2,ask=1),dict(bid=float('nan')),dict(lastQuoteAt='2026-10-08T16:00:00')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                f.parse_tick({**self.tick('EURUSD'),**change},'EURUSD',self.now)
    def test_old_backup_cannot_replace_newer_saved(self):
        out=f.fetch_rates(Mock(side_effect=OSError('offline')),self.primary,self.now)
        self.assertEqual(out['rates'],self.primary['rates'])
