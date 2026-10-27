import unittest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
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
    def test_shared_leverage_reason_does_not_claim_missing_timestamp(self):
        self.props.append(dict(Name='CurrentLeverage', Value='18,25', Suffix=''))
        with patch.object(q, 'issuer_json', side_effect=[self.product, self.props, self.points]):
            out = sg.get_quote(ISIN)
        self.assertIn('gemeinsamem Zeitbezug', out['reason'])
        self.assertNotIn('kein separat datierter Hebel', out['reason'])
        self.assertFalse(out['eligible'])
        self.assertIsNone(out['issuerLeverageReference']['sourceAt'])

    def test_swiss_gearing_alias_retains_provenance_and_shared_time(self):
        self.props.append(dict(Name='Gearing', Value=17.944,
                               RealtimeFieldName='current_leverage'))
        with patch.object(q, 'issuer_json', side_effect=[self.product, self.props, self.points]):
            out = sg.get_quote(ISIN)
        ref = out['issuerLeverageReference']
        self.assertEqual(ref['value'], 17.944)
        self.assertEqual(ref['source'], 'SG · AllProperties.Gearing')
        self.assertEqual(ref['sharedContextAt'], self.at)
        self.assertIsNone(ref['sourceAt'])
        self.assertFalse(out['eligible'])

    def test_conflicting_leverage_aliases_are_not_selected(self):
        self.props.extend([dict(Name='Gearing', Value=17.944, RealtimeFieldName='current_leverage'),
                           dict(Name='CurrentLeverage', Value=18.0)])
        with patch.object(q, 'issuer_json', side_effect=[self.product, self.props, self.points]):
            out = sg.get_quote(ISIN)
        self.assertNotIn('issuerLeverageReference', out)
        self.assertIn('leverageReferenceIssue', out)

    def test_missing_leverage_reason_names_missing_value(self):
        with patch.object(q, 'issuer_json', side_effect=[self.product, self.props, self.points]):
            out = sg.get_quote(ISIN)
        self.assertIn('von der Quelle nicht geliefert', out['reason'])
        self.assertNotIn('issuerLeverageReference', out)

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

    def test_new_fb_series_requests_sg_before_bnp_with_exact_identity(self):
        # Synthetic issuer product ID: a screenshot/WKN is a discovery hint
        # only. The ID must come from the official SG Products/<ISIN> reply.
        isin = 'DE000FB0CVV9'
        self.assertTrue(q.sg_on_demand_candidate(isin))
        self.assertFalse(q.sg_on_demand_candidate('DE000FB0CVV0'))
        product = dict(self.product, Isin=isin, Id=8765432, Currency='EUR',
                       ExchangeCode='CBDE', ProductClassificationId=47)
        props = [dict(p, Value=isin) if p['Name']=='Isin' else dict(p)
                 for p in self.props]
        for p in props:
            if p['Name'] == 'BarrierTurboCertificate' or p['Name'] == 'Strike':
                p['Value'] = 4089.3179
        with patch.object(q, 'issuer_json', side_effect=[product, props, self.points]) as network, \
             patch.object(q, 'get_bnp_quote') as bnp:
            received = q.get_issuer_quote(isin)
        bnp.assert_not_called()
        self.assertTrue(received['productVerified'])
        self.assertEqual(received['isin'], isin)
        self.assertEqual(received['metadata']['currency'], 'EUR')
        self.assertEqual(received['metadata']['direction'], 'SHORT')
        self.assertEqual(received['chartEvidence']['pointAt'], self.at)
        self.assertFalse(received['found'])
        self.assertFalse(received['eligible'])
        urls = [c.args[0] for c in network.call_args_list]
        self.assertEqual(urls[0], 'https://www.sg-zertifikate.de/EmcWebApi/api/Products/'+isin)
        self.assertTrue(urls[1].endswith('/Products/AllProperties/8765432'))
        self.assertTrue(urls[2].endswith('/Prices/Live?productId=8765432'))

    def test_fb_wrong_identity_is_never_sg_verified(self):
        isin='DE000FB0CVV9'
        for override in (dict(Isin='DE000FG7K283'), dict(Currency='CHF'),
                         dict(ExchangeCode='CBSW'), dict(AssetNMP='GOLD-FUTURE')):
            with self.subTest(override=override):
                sg._CACHE.clear(); sg._TERMS.clear()
                wrong=dict(self.product, Isin=isin, Id=8765432)
                wrong.update(override)
                with patch.object(q, 'issuer_json', side_effect=[wrong, []]), \
                     patch.object(q, 'get_bnp_quote',return_value={'found':False,'productVerified':False}):
                    got=q.get_issuer_quote(isin)
                self.assertFalse(got.get('productVerified'))
                self.assertFalse(got.get('eligible',False))

    def test_fb0cvv_known_sg_does_not_mask_issuer_404_with_bnp(self):
        from urllib.error import HTTPError
        isin = 'DE000FB0CVV9'
        self.assertIn(isin, q.SG_DISCOVERY_PRODUCTS)
        failed = HTTPError('https://www.sg-zertifikate.de/',404,'Not Found',{},None)
        with patch.object(q, 'issuer_json', side_effect=failed) as network, \
             patch.object(q, 'get_bnp_quote') as bnp:
            out = q.get_issuer_quote(isin)
        bnp.assert_not_called()
        self.assertEqual(network.call_count, 1)
        self.assertTrue(network.call_args.args[0].endswith('/Products/'+isin))
        self.assertEqual(out['source'],'Société Générale · Direktimport')
        self.assertEqual(out['quoteFailureCode'],'SG_SOURCE_UNAVAILABLE')
        self.assertIn('SG Produktidentität',out['reason'])
        self.assertIn('HTTP 404',out['reason'])
        self.assertFalse(out['productVerified'])
        self.assertFalse(out['eligible'])
        self.assertFalse(out['found'])
        self.assertNotIn('bid',out)
        self.assertNotIn('leverage',out)

    def test_missing_list_products_route_to_sg(self):
        for isin, product_id, classification in [('DE000FG5GUN3',6934161,47), ('DE000FG7HZY3',7151899,43), ('DE000FG7Q3N2',7152436,47)]:
            with self.subTest(isin=isin):
                self.product.update(Isin=isin, Id=product_id, ProductClassificationId=classification)
                for prop in self.props:
                    if prop['Name']=='Isin': prop['Value']=isin
                with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]), patch.object(q,'get_bnp_quote') as bnp:
                    out=q.get_issuer_quote(isin)
                bnp.assert_not_called()
                self.assertTrue(out['productVerified'])
                self.assertEqual(out['chartEvidence']['ask'],10.01)
                self.assertFalse(out['eligible'])

    def test_quanto_explicit_flags_and_undated_reference_are_not_trade_proofs(self):
        for value in (False, 0, 'Nein', 'No', 'false', '0'):
            with self.subTest(value=value):
                sg._CACHE.clear(); sg._TERMS.clear()
                props=self.props+[dict(Name='IsQuanto', Value=value, Suffix=''),
                                  dict(Name='CurrentLeverage', Value='18,25', Suffix='')]
                with patch.object(q, 'issuer_json', side_effect=[self.product, props, self.points]):
                    got=sg.get_quote(ISIN)
                self.assertEqual(got['metadata']['quantoState'], 'non-quanto')
                self.assertTrue(got['metadata']['simpleNonQuantoTurbo'])
                self.assertEqual(got['issuerLeverageReference']['value'], 18.25)
                self.assertEqual(got['issuerLeverageReference']['sharedContextAt'], got['chartEvidence']['pointAt'])
                self.assertEqual(got['sharedTimeContext']['isin'], ISIN)
                self.assertIn('Referenzhebel', got['sharedTimeContext']['fields'])
                self.assertIn('ko', got['sharedTimeContext']['fields'])
                self.assertEqual(got['conditions']['ko']['contextAt'], got['chartEvidence']['pointAt'])
                # Every observed SG value has the same verified observation
                # context. Original source clocks and term validity remain separate.
                observed=got['sharedValueObservations']
                self.assertEqual(set(observed), set(got['sharedTimeContext']['fields']))
                for key in ('ISIN','Geld','Brief','direction','currency',
                            'underlying','status','ko','strike','ratio',
                            'Referenzhebel'):
                    self.assertIn(key,observed)
                    self.assertEqual(observed[key]['contextAt'],got['chartEvidence']['pointAt'])
                    self.assertEqual(observed[key]['isin'],ISIN)
                self.assertEqual(observed['Geld']['sourceAt'],got['chartEvidence']['pointAt'])
                self.assertIsNone(observed['Referenzhebel']['sourceAt'])
                self.assertIsNone(observed['ko']['sourceAt'])
                self.assertIsNone(got['conditions']['ko']['at'])
                self.assertIsNone(got['issuerLeverageReference']['sourceAt'])
                self.assertFalse(got['issuerLeverageReference']['eligible'])
                self.assertNotIn('leverageAt', got)
                self.assertNotIn('leverage', got)
                self.assertFalse(got['found'])
                self.assertFalse(got['eligible'])

    def test_missing_conflicting_or_quanto_true_never_enables_model(self):
        cases=(
            ([], 'unknown'),
            ([dict(Name='IsQuanto', Value='perhaps', Suffix='')], 'unknown'),
            ([dict(Name='IsQuanto', Value='Nein', Suffix=''),
              dict(Name='Quanto', Value='Ja', Suffix='')], 'unknown'),
            ([dict(Name='Quanto', Value='Yes', Suffix='')], 'quanto'),
        )
        for extra, expected in cases:
            with self.subTest(expected=expected, extra=extra):
                sg._CACHE.clear(); sg._TERMS.clear()
                with patch.object(q, 'issuer_json', side_effect=[self.product, self.props+extra, self.points]):
                    got=sg.get_quote(ISIN)
                self.assertEqual(got['metadata']['quantoState'], expected)
                self.assertFalse(got['metadata']['simpleNonQuantoTurbo'])
                self.assertFalse(got['eligible'])

    def test_product_level_quanto_must_not_contradict_property(self):
        sg._CACHE.clear(); sg._TERMS.clear()
        product=dict(self.product,IsQuanto=True)
        props=self.props+[dict(Name='IsQuanto',Value=False,Suffix='')]
        with patch.object(q, 'issuer_json', side_effect=[product, props, self.points]):
            got=sg.get_quote(ISIN)
        self.assertEqual(got['metadata']['quantoState'],'unknown')
        self.assertFalse(got['metadata']['simpleNonQuantoTurbo'])

    def test_import_cache_and_no_false_trade_release(self):
        with patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]) as fetch:
            out=sg.get_quote(ISIN); cached=sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(out['conditions']['ratio']['value'],.1)
        self.assertEqual(cached['chartEvidence']['pointAt'],out['chartEvidence']['pointAt'])
        self.assertFalse(out['eligible']); self.assertFalse(out['found'])
        self.assertNotIn('leverageAt',out); self.assertEqual(out['conditions']['strike']['value'],4400)
        self.assertIsNone(out['conditions']['strike']['at'])
        self.assertFalse(out['conditions']['strike']['conditionVerified'])
        self.assertEqual(out['observedTerms']['strike'],4400)
        self.assertEqual(out['metadata']['status'],1)
        self.assertEqual(out['metadata']['sgStatus'],65)
    def test_term_series_refreshes_only_after_reobserving_same_product(self):
        with patch.object(sg.time,'monotonic',return_value=0), patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]):
            first=sg.get_quote(ISIN)
        # A new 30-second cycle re-fetches ALL SG values; unlike a chart
        # refresh alone, it produces new provenance for newly observed terms.
        with patch.object(sg.time,'monotonic',return_value=31), patch.object(q,'issuer_json',side_effect=[self.product,self.props,self.points]) as fetch:
            refreshed=sg.get_quote(ISIN)
        self.assertEqual(fetch.call_count,3)
        for key in ('strike','ko'):
            before=first['conditions'][key]['validitySeries']
            after=refreshed['conditions'][key]['validitySeries']
            self.assertEqual(before['observedAt'],first['termsCheckedAt'])
            self.assertEqual(after['observedAt'],refreshed['termsCheckedAt'])
            self.assertEqual(after['isin'],ISIN)
            self.assertIsNone(refreshed['conditions'][key]['at'])
            self.assertFalse(refreshed['conditions'][key]['conditionVerified'])
        self.assertFalse(refreshed['metadata']['termsDated'])
        self.assertFalse(refreshed['eligible'])

    def test_slightly_newer_chart_within_same_collection_keeps_context_only(self):
        # Official point observation may follow the properties response by
        # a few seconds while both were collected for the exact same ISIN.
        point_at = datetime.now(timezone.utc) - timedelta(seconds=2)
        props_at = point_at - timedelta(seconds=3)
        result = dict(isin=ISIN, productVerified=True,
            termsCheckedAt=props_at.isoformat(),
            chartEvidence={'pointAt': point_at.isoformat()},
            conditions={'strike': {'value': 4400}},
            issuerLeverageReference={'value': 18.25, 'sourceAt': None,
                                     'dated': False, 'eligible': False})
        sg.associate_shared_observation(result)
        self.assertEqual(result['sharedTimeContext']['at'], point_at.isoformat())
        self.assertEqual(result['issuerLeverageReference']['sharedContextAt'], point_at.isoformat())
        self.assertIsNone(result['issuerLeverageReference']['sourceAt'])
        self.assertFalse(result['issuerLeverageReference']['eligible'])
        self.assertNotIn('leverageAt', result)
        self.assertIsNone(result['conditions']['strike'].get('at'))
        # More than five seconds of inverted timing is not the same context.
        result.pop('sharedTimeContext')
        result['termsCheckedAt'] = (point_at - timedelta(seconds=6)).isoformat()
        result['issuerLeverageReference'].pop('sharedContextAt')
        sg.associate_shared_observation(result)
        self.assertNotIn('sharedTimeContext', result)

    def test_stale_sg_chart_cannot_date_reference_or_static_conditions(self):
        self.points = [dict(Bid=10, Ask=10.01,
            Date=(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat())]
        props = self.props + [dict(Name='CurrentLeverage', Value='31.4', Suffix='')]
        with patch.object(q,'issuer_json',side_effect=[self.product, props, self.points]):
            old = sg.get_quote(ISIN)
        self.assertNotIn('sharedTimeContext', old)
        self.assertNotIn('sharedContextAt', old['issuerLeverageReference'])
        self.assertIsNone(old['issuerLeverageReference']['sourceAt'])
        self.assertIsNone(old['conditions']['ko']['at'])
        self.assertFalse(old['eligible'])

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
        today=datetime.now(ZoneInfo('Europe/Zurich')).strftime('%Y-%m-%d')
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
            date=(datetime.now(ZoneInfo('Europe/Zurich'))+timedelta(days=offset)).strftime('%Y-%m-%d')
            props=self.props+[dict(Name='StrikeBarrierUpdateTime',Value=date+'T03:35:31')]
            with patch.object(q,'issuer_json',side_effect=[self.product,props,self.points]):
                out=sg.get_quote(ISIN)
            self.assertFalse(out['metadata']['termsDated'])
            self.assertEqual(out['conditions']['strike']['value'],4400)
            self.assertIsNone(out['conditions']['strike']['at'])
            self.assertFalse(out['conditions']['strike']['conditionVerified'])

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
        self.assertEqual(out['metadata']['type'],'FACTOR')
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
