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
    def test_sq02jq_mini_direct_route(self):
        isin = 'DE000SQ02JQ6'
        self.product.update(Id=2829392, Isin=isin, ProductClassificationId=45)
        for prop in self.props:
            if prop['Name'] == 'Isin': prop['Value'] = isin
            if prop['Name'] == 'ClassificationName': prop['Value'] = 'Unlimited Turbo-Optionsscheine (Mini)'
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]):
            out=sg.get_quote(isin)
        self.assertTrue(out['productVerified'])
        self.assertEqual(out['conditions']['maturity']['value'], 'Open End')
        self.assertEqual(out['chartEvidence']['ask'], 10.01)

    def test_import_cache_and_no_false_trade_release(self):
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]) as fetch:
            out=sg.get_quote(ISIN); cached=sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(out['conditions']['ratio']['value'],.1)
        self.assertEqual(cached['chartEvidence']['pointAt'],out['chartEvidence']['pointAt'])
        self.assertFalse(out['eligible']); self.assertFalse(out['found'])
        self.assertNotIn('leverageAt',out); self.assertNotIn('strike',out['conditions'])
        self.assertEqual(out['observedTerms']['strike'],4400)
        self.assertEqual(out['metadata']['status'],1)
        self.assertEqual(out['metadata']['sgStatus'],65)
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
        self.assertEqual(out['metadata']['status'],2)
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

    def test_screenshot_products_route_to_verified_sg_ids(self):
        for isin, product_id in [('DE000FG5GUT0',6933892), ('DE000FG7EPT1',7102845),
                                 ('DE000FC1CHB7',5906476), ('DE000FG7K275',7127358)]:
            with self.subTest(isin=isin):
                product = dict(self.product, Isin=isin, Id=product_id)
                props = [dict(p, Value=isin) if p['Name']=='Isin' else dict(p) for p in self.props]
                with patch.object(q,'issuer_json',side_effect=[product,props,self.points]) as fetch, patch.object(q,'get_bnp_quote') as bnp:
                    out=q.get_issuer_quote(isin)
                bnp.assert_not_called()
                self.assertIn('productId='+str(product_id),fetch.call_args.args[0])
                self.assertTrue(out['productVerified'])
                self.assertIn('chartEvidence',out)
                self.assertFalse(out['eligible'])

    def test_today_term_date_does_not_invent_a_quote_clock(self):
        today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self.props.append(dict(Name='StrikeBarrierUpdateTime',Value=today+'T03:35:31.247'))
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]):
            out=sg.get_quote(ISIN)
        self.assertTrue(out['metadata']['termsDated'])
        self.assertEqual(out['conditions']['ko']['value'],4400)
        self.assertIsNone(out['conditions']['ko']['at'])
        self.assertFalse(out['eligible'])
        self.assertNotIn('leverageAt',out)

    def test_yesterday_and_future_term_dates_remain_unconfirmed(self):
        for offset in (-1,1):
            sg._CACHE.clear();sg._TERMS.clear()
            date=(datetime.now(timezone.utc)+timedelta(days=offset)).strftime('%Y-%m-%d')
            props=self.props+[dict(Name='StrikeBarrierUpdateTime',Value=date+'T03:35:31')]
            with patch.object(q,'issuer_json',side_effect=[self.product,props,self.points]):
                out=sg.get_quote(ISIN)
            self.assertFalse(out['metadata']['termsDated'])
            self.assertNotIn('strike',out['conditions'])

    def test_future_contract_is_preserved_without_spot_release(self):
        isin='DE000FG309G0';c=q.SG_GOLD_FUTURES[isin]
        product=dict(self.product,Isin=isin,Id=7032167,AssetNMP=c['nmp'],AssetRic=c['ric'],AssetIsin=c['isin'],AssetName=c['name'])
        props=[dict(p,Value=isin) if p['Name']=='Isin' else p for p in self.props]
        with patch.object(q,'issuer_json',side_effect=[product,props,self.points]):
            out=sg.get_quote(isin)
        self.assertEqual(out['conditions']['contract']['value'],'GCZ26')
        self.assertIn('chartEvidence',out)
        self.assertFalse(out['eligible'])

    def test_classic_fixed_terms_keep_expiry_without_fabricated_date(self):
        expiry=(datetime.now(timezone.utc)+timedelta(days=60)).strftime('%Y-%m-%d')
        product=dict(self.product,ProductClassificationId=43,MaturityDate=expiry+'T00:00:00')
        props=[dict(p,Value='Classic Turbo-Optionsscheine') if p['Name']=='ClassificationName' else p for p in self.props]
        with patch.object(q,'issuer_json',side_effect=[product,props,self.points]):
            out=sg.get_quote(ISIN)
        self.assertTrue(out['metadata']['termsFixed'])
        self.assertIsNone(out['conditions']['ko']['at'])
        self.assertNotIn('dateText',out['conditions']['ko'])
        self.assertEqual(out['conditions']['ko']['validUntil'],expiry)
        self.assertFalse(out['eligible'])

    def test_factor_identity_excluded_without_quote_or_properties_requests(self):
        isin='DE000FE4UF01';c=q.SG_GOLD_FUTURES['DE000FG309G0']
        product=dict(self.product,Isin=isin,Id=6628472,ProductClassificationId=44100,
            AssetNMP=c['nmp'],AssetRic=c['ric'],AssetIsin=c['isin'],AssetName=c['name'])
        with patch.object(q,'issuer_json',return_value=product) as fetch:
            out=sg.get_quote(isin)
        fetch.assert_called_once()
        self.assertTrue(out['excluded']);self.assertTrue(out['productVerified'])
        self.assertFalse(out['eligible'])

    def test_different_products_do_not_share_network_lock(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        first=threading.Event();release=threading.Event()
        other='DE000FG5GUT0'
        def fetch(url,origin,timeout):
            if url.endswith('/Products/'+ISIN):
                first.set();release.wait(2);raise TimeoutError()
            raise TimeoutError()
        with patch.object(q,'issuer_json',side_effect=fetch), ThreadPoolExecutor(max_workers=2) as pool:
            blocked=pool.submit(sg.get_quote,ISIN)
            self.assertTrue(first.wait(1))
            try:
                out=pool.submit(sg.get_quote,other).result(timeout=1)
                self.assertTrue(out['sourceFailure'])
            finally:release.set()
            blocked.result(timeout=1)

    def test_terms_first_does_not_wait_for_quotes_or_hide_later_quotes(self):
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props]) as fetch:
            out=sg.get_quote(ISIN,terms_only=True)
        self.assertEqual(fetch.call_count,2)
        self.assertTrue(out['productVerified']);self.assertEqual(out['conditions']['ratio']['value'],.1)
        self.assertNotIn('chartEvidence',out);self.assertFalse(out['eligible'])
        with patch.object(q,'issuer_json',return_value=self.points) as fetch:
            full=sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,1)
        self.assertIn('chartEvidence',full)
