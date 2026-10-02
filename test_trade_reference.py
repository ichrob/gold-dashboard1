import unittest
from trade_reference import align, screenshot_interval

class ReferenceTests(unittest.TestCase):
    def fixture(self, raw='02/10/2026 19:49'):
        s,e=screenshot_interval(raw)
        g={'symbol':'xau','currency':'USD','unit':'troy_oz','points':[{'t':s+69,'p':4138.9}]}
        f={'chart':{'result':[{'meta':{'symbol':'EURUSD=X','currency':'USD','instrumentType':'CURRENCY','dataGranularity':'1m'},'timestamp':[s],'indicators':{'quote':[{'close':[1.125745]}]}}]}}
        return s,g,f

    def test_original_minute_and_inverse(self):
        s,g,f=self.fixture();r=align('02/10/2026 19:49',g,f,s+3600)
        self.assertTrue(r['available']);self.assertFalse(r['isExchangeRealtime'])
        self.assertEqual(r['originalTime'],'02/10/2026 19:49')
        self.assertAlmostEqual(r['fxReference'],1/1.125745)
        self.assertEqual(r['maxSkewSeconds'],69)

    def test_far_pair_no_daily_or_present_substitution(self):
        s,g,f=self.fixture();g['points'][0]['t']=s-120
        self.assertFalse(align('02/10/2026 19:49',g,f,s+3600)['available'])

    def test_unfinished_fx_bar_and_null(self):
        s,g,f=self.fixture();self.assertFalse(align('02/10/2026 19:49',g,f,s+30)['available'])
        f['chart']['result'][0]['indicators']['quote'][0]['close']=[None]
        self.assertFalse(align('02/10/2026 19:49',g,f,s+3600)['available'])

    def test_wrong_instrument(self):
        s,g,f=self.fixture();g['symbol']='gc'
        with self.assertRaises(ValueError):align('02/10/2026 19:49',g,f,s+3600)

    def test_timezone_and_seconds(self):
        a,b=screenshot_interval('02/10/2026 19:46:08');self.assertEqual(a,b)
        self.assertEqual(a,1790963168)
        for raw in ['25/10/2026 02:30','29/03/2026 02:30','32/10/2026 19:49','19:49']:
            with self.assertRaises(ValueError):screenshot_interval(raw)

if __name__=='__main__':unittest.main()
