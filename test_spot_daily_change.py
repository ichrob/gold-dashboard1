import json
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import spot_daily_change as s

NOW=datetime(2026,10,5,10,tzinfo=timezone.utc).timestamp()

class SpotChangeTests(unittest.TestCase):
    def instrument(self):
        return dict(base=dict(id='68',path='/currencies/xau-usd',isCfd=False,type='currency'),
                    name=dict(shortName='XAU/USD'),isFuture=False,
                    price=dict(currency='USD',lastClose=4000,lastUpdateTime=str(int(NOW*1000))))
    def parse(self,i):
        return s.parse('<script id="__NEXT_DATA__">'+json.dumps(dict(props=dict(pageProps=dict(state=dict(currencyStore=dict(instrument=i))))))+'</script>',NOW)
    def test_correct_spot_identity_and_original_source_time(self):
        r=self.parse(self.instrument());self.assertEqual(r['previousClose'],4000);self.assertEqual(r['observedAt'],NOW)
    def test_reject_future_cfd_missing_base_wrong_currency_and_stale(self):
        for field,value in [('lastClose',None),('lastClose',0),('lastClose',True),('currency','EUR'),('lastUpdateTime',str(int((NOW-301)*1000)))]:
            i=self.instrument();i['price'][field]=value
            with self.assertRaises(ValueError):self.parse(i)
        for field,value in [('id','8830'),('isCfd',True),('path','/commodities/gold')]:
            i=self.instrument();i['base'][field]=value
            with self.assertRaises(ValueError):self.parse(i)
        i=self.instrument();i['isFuture']=True
        with self.assertRaises(ValueError):self.parse(i)
    def test_uses_exact_displayed_spot_for_positive_negative_zero(self):
        with patch.object(s,'_reference',self.parse(self.instrument())):
            for price,expected in [(4040,1),(3960,-1),(4000,0)]:
                r=s.change(price,datetime.fromtimestamp(NOW,timezone.utc).isoformat(),NOW)
                self.assertAlmostEqual(r['changePct'],expected)
                self.assertIn('Investing.com',r['changeLabel'])
    def test_stale_reference_or_quote_never_produces_percentage(self):
        with patch.object(s,'_reference',self.parse(self.instrument())):
            self.assertIsNone(s.change(4040,datetime.fromtimestamp(NOW+301,timezone.utc).isoformat(),NOW+301))
            self.assertIsNone(s.change(4040,datetime.fromtimestamp(NOW-121,timezone.utc).isoformat(),NOW))
    def test_daily_rollover_rejects_yesterdays_basis(self):
        end=datetime(2026,10,5,21,tzinfo=timezone.utc).timestamp() # 17:00 New York
        with patch.object(s,'_reference',dict(previousClose=4000,observedAt=end-30)):
            self.assertIsNone(s.change(4040,datetime.fromtimestamp(end+1,timezone.utc).isoformat(),end+1))

if __name__=='__main__':unittest.main()
