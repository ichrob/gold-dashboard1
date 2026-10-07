import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import sg_direct as sg
import product_quotes as q

ISIN = 'DE000FG7K283'
class DirectTests(unittest.TestCase):
    def setUp(self):
        sg._CACHE.clear(); sg._TERMS.clear()
        self.product = dict(Id=7127448, Isin=ISIN, ExchangeCode='CBDE', AssetNMP='XAUUSD',
            AssetCurrency='USD', Currency='EUR', Status=65, ProductClassificationId=47,
            MaturityDate=None)
        self.props = [dict(Name=k, Value=v, Suffix=s) for k,v,s in (
            ('Isin',ISIN,''), ('PutOrCall','Put',''), ('BarrierTurboCertificate',4400,'USD'),
            ('Ratio',10,':1'), ('Strike',4400,'USD'),
            ('ClassificationName','BEST Turbo (Open-End)',''))]
        self.at = (datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()
        self.points = [dict(Bid=10, Ask=10.01, Date=self.at)]
    def test_import_cache_and_no_false_trade_release(self):
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]) as fetch:
            out=sg.get_quote(ISIN); cached=sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(out['conditions']['ratio']['value'],.1)
        self.assertEqual(cached['chartEvidence']['pointAt'],out['chartEvidence']['pointAt'])
        self.assertFalse(out['eligible']); self.assertFalse(out['found'])
        self.assertNotIn('leverageAt',out); self.assertNotIn('strike',out['conditions'])
        self.assertEqual(out['observedTerms']['strike'],4400)
    def test_identity_mismatch_stops_before_properties(self):
        self.product['Isin']='DE000FG4JXV7'
        with patch.object(q,'issuer_json',return_value=self.product) as fetch:
            out=sg.get_quote(ISIN); sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,1); self.assertFalse(out['productVerified'])
    def test_bad_chart_keeps_verified_terms(self):
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,TimeoutError()]):
            out=sg.get_quote(ISIN)
        self.assertTrue(out['productVerified']); self.assertIn('ratio',out['conditions'])
        self.assertFalse(out['eligible']); self.assertNotIn('chartEvidence',out)
    def test_inactive_product_never_requests_chart(self):
        self.product['Status']=8
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props]) as fetch:
            out=sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,2); self.assertFalse(out['eligible'])
    def test_rate_limit_expires_after_thirty_seconds(self):
        with patch.object(sg.time,'monotonic',return_value=0), patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]):
            sg.get_quote(ISIN)
        with patch.object(sg.time,'monotonic',return_value=29), patch.object(q,'issuer_json') as fetch:
            sg.get_quote(ISIN); fetch.assert_not_called()
        with patch.object(sg.time,'monotonic',return_value=30), patch.object(q,'issuer_json',return_value=self.points) as fetch:
            sg.get_quote(ISIN); self.assertEqual(fetch.call_count,1)
    def test_cache_age_is_recomputed_without_changing_clock(self):
        self.points[0]['Date']=(datetime.now(timezone.utc)-timedelta(seconds=100)).isoformat()
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]):
            out=sg.get_quote(ISIN)
        self.assertFalse(out['chartEvidence']['current']); self.assertIn('veraltet',out['reason'])
