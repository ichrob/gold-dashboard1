import unittest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import product_quotes as q
from urllib.error import HTTPError

ISIN='DE000PJ9NCK0'
NOW=datetime(2026,9,30,16,6,3,tzinfo=timezone.utc)
def snapshot():
    return dict(responseDate='2026-09-30T16:06:02Z',tradingHours=dict(isTradeable=True,tradingStart='2026-09-30T06:00:00Z',tradingEnd='2026-09-30T20:00:00Z'),result=dict(isin=ISIN,productName='GOLD Unlimited Long',issuerCompanyName='BNP Paribas',currency=dict(isoCode='EUR'),first=dict(underlyingISIN='USFX00000XAU',currency=dict(isoCode='USD'),knockOutAbsolute=3978.9026),keyFigures=dict(leverage=22.67,lastUpdate='2026-09-30T16:06:02Z'),config=dict(hasMultipleUnderlying=False,isPublicTradable=True,isMarketClosed=False,isKnockedOut=False,isMaturedOrKnockOut=False,isCanceled=False,isLifeCycleEnded=False,isBidOnly=False,isPercentageQuotation=False),bid=16.19,ask=16.2,bidSize=8000,askSize=8000,leverage=22.67,bidDate='2026-09-30T18:06:00.282',askDate='2026-09-30T18:06:00.282'))

class ProductQuoteTests(unittest.TestCase):
    def setUp(self):
        self.backup = patch('onvista_backup.fetch', return_value=None)
        self.backup.start()
        self.addCleanup(self.backup.stop)

    def fetch_bnp(self, data):
        with patch.object(q, 'urlopen') as network:
            response = network.return_value.__enter__.return_value
            response.url = q.ORIGIN+'apiv2/api/v1/product/header/'+ISIN
            response.read.return_value = json.dumps(data).encode()
            return q.get_bnp_quote(ISIN)

    def test_bnp_missing_quote_time_preserves_only_verified_conditions(self):
        data = snapshot()
        data['result']['first'].update(ratio=.1, strikeAbsolute=3978.9026,
                                      determinationDate='2099-01-01T00:00:00')
        data['result']['keyFigures']['maturityDateTimestamp'] = -1
        data['result']['derivativeTypeName'] = 'Unlimited Long'
        del data['result']['bidDate']
        result = self.fetch_bnp(data)
        self.assertTrue(result['productVerified'])
        self.assertFalse(result['found']); self.assertFalse(result['eligible'])
        self.assertEqual(result['quoteFailureCode'], 'MISSING_QUOTE_TIME')
        self.assertIn('Geldkurs', result['reason'])
        self.assertEqual(result['conditions']['ratio']['value'], .1)
        self.assertEqual(result['conditions']['maturity']['value'], 'Open End')
        self.assertNotIn('ko', result['conditions']); self.assertNotIn('strike', result['conditions'])
        self.assertFalse(result['metadata']['termsDated'])
        self.assertIsNone(result['observedTerms']['effectiveAt'])
        for key in ('bid', 'ask', 'quoteAt', 'bidAt', 'askAt', 'leverageAt'):
            self.assertNotIn(key, result)
        self.assertFalse(q.freshness(result)['eligible'])

    def test_bnp_wrong_identity_never_retains_conditions(self):
        data = snapshot(); data['result']['isin'] = 'DE000PJ9NB98'
        result = self.fetch_bnp(data)
        self.assertFalse(result['productVerified'])
        self.assertTrue(result['sourceFailure']); self.assertNotIn('conditions', result)

    def test_bnp_dated_quote_does_not_date_terms(self):
        result = self.fetch_bnp(snapshot())
        self.assertTrue(result['found']); self.assertTrue(result['productVerified'])
        self.assertFalse(result['metadata']['termsDated'])
        self.assertIsNone(result['observedTerms']['effectiveAt'])
        self.assertFalse(result['fresh'])  # historical regression input

    def test_bnp_diagnostic_survives_routing_cache_and_comdirect(self):
        data = snapshot(); del data['result']['bidDate']
        failure = self.fetch_bnp(data)
        terms = dict(isin=ISIN, productVerified=True, found=False, eligible=False,
                     metadata={'status':1}, source='comdirect', reason='Stammdaten vorhanden')
        with patch.dict(q._CACHE, {}, clear=True), patch.object(q, 'get_bnp_quote', return_value=failure) as fetch, \
                patch('public_product_terms.get_product', return_value=terms):
            first = q.get_quote(ISIN); second = q.get_quote(ISIN)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(second['quoteFailureCode'], 'MISSING_QUOTE_TIME')
        self.assertEqual(first['conditions'], failure['conditions'])
        self.assertIn('Geldkurs', second['reason']); self.assertIn('BNP Paribas', second['source'])

    def test_bnp_direct_metadata_survives_secondary_source(self):
        data = snapshot()
        data['result'].update(derivativeTypeName='Unlimited Long')
        data['result']['first'].update(ratio=.1, strikeAbsolute=3978.9026)
        primary = q.bnp_product_data(data, ISIN, NOW)
        with patch.object(q, 'get_issuer_quote', return_value=primary), patch('public_product_terms.get_product') as secondary:
            result = q._get_quote_primary(ISIN)
        secondary.assert_not_called()
        self.assertTrue(result['metadata']['simpleTurbo'])
        self.assertEqual(result['metadata']['quantoState'], 'unknown')
        self.assertFalse(result['metadata']['simpleNonQuantoTurbo'])
        self.assertFalse(result['metadata']['termsDated'])

    def test_bnp_terms_survive_comdirect_outage_without_quote_approval(self):
        data = snapshot(); del data['result']['askDate']
        failure = self.fetch_bnp(data)
        with patch.object(q, 'get_issuer_quote', return_value=failure), \
                patch('public_product_terms.get_product', return_value={'productVerified':False}):
            result = q.get_quote(ISIN)
        self.assertTrue(result['productVerified']); self.assertFalse(result['eligible'])
        self.assertIn('Briefkurs', result['reason'])

    def test_bnp_confirmed_terminal_status_overrides_secondary_active_status(self):
        data = snapshot(); data['result']['config']['isKnockedOut'] = True
        failure = self.fetch_bnp(data)
        with patch.object(q, 'get_issuer_quote', return_value=failure), \
                patch('public_product_terms.get_product', return_value={'productVerified':True, 'metadata':{'status':1}}):
            result = q.get_quote(ISIN)
        self.assertEqual(result['metadata']['status'], 2); self.assertFalse(result['eligible'])

    def test_bnp_network_diagnostics_do_not_expose_raw_error(self):
        error = HTTPError('https://private.invalid/?secret=x', 429, 'private', {}, None)
        with patch.object(q, 'urlopen', side_effect=error):
            result = q.get_bnp_quote(ISIN)
        self.assertEqual(result['quoteFailureCode'], 'HTTP_429')
        self.assertNotIn('secret', result['reason']); self.assertNotIn('private', result['reason'])

    def test_bnp_cache_parameter_changes_but_cannot_refresh_source_clocks(self):
        with patch.object(q, 'get_bnp_dated_terms', side_effect=ValueError('no page')), patch.object(q, 'urlopen') as network, patch.object(q.time, 'time', return_value=1500):
            response = network.return_value.__enter__.return_value
            response.url = q.ORIGIN+'apiv2/api/v1/product/header/'+ISIN
            response.read.return_value = json.dumps(snapshot()).encode()
            first = q.get_bnp_quote(ISIN)
            self.assertTrue(network.call_args.args[0].full_url.endswith('?_=1500000'))
            with patch.object(q.time, 'time', return_value=1516):
                second = q.get_bnp_quote(ISIN)
            self.assertTrue(network.call_args.args[0].full_url.endswith('?_=1515000'))
        self.assertEqual(first['quoteAt'], second['quoteAt'])
        self.assertFalse(second['fresh']); self.assertFalse(second['eligible'])

    def test_stale_response_is_distinguished_from_closed_market(self):
        stale = q.parse_bnp(snapshot(), ISIN, NOW+timedelta(minutes=3))
        self.assertFalse(stale['eligible'])
        self.assertEqual(stale['quoteFailureCode'], 'STALE_OR_INVALID_SOURCE_TIME')
        self.assertIn('Kursantwort veraltet', stale['reason'])
        closed = snapshot()
        closed['tradingHours']['isTradeable'] = False
        self.assertIn('markt geschlossen', q.parse_bnp(closed, ISIN, NOW)['reason'])
        self.assertEqual(stale['bidAt'], q.parse_bnp(snapshot(), ISIN, NOW)['bidAt'])

    def test_known_sg_failure_is_not_replaced_by_bnp_miss(self):
        isin='DE000FA06UL6'
        with patch.dict(q.SG_DIRECT_PRODUCTS, {}, clear=True), patch.dict(q._CACHE, {isin:(__import__('time').monotonic(),{'found':True,'source':'SG'})}, clear=True), patch.object(q,'get_bnp_quote') as bnp, patch.object(q,'issuer_json') as sg:
            out=q.get_issuer_quote(isin)
        self.assertTrue(out['sourceDisabled']);self.assertFalse(out['found'])
        bnp.assert_not_called();sg.assert_not_called()

    def test_sg_errors_expose_only_fixed_stage_and_http_status(self):
        error=HTTPError('https://private.invalid/?secret=value',429,'private body',{'Authorization':'secret'},None)
        reason=q.sg_source_error(error,'identity')
        self.assertIn('HTTP 429',reason);self.assertNotIn('secret',reason)
        with patch.dict(q.SG_DIRECT_PRODUCTS, {}, clear=True), patch.object(q,'issuer_json') as fetch:
            out=q.get_sg_quote('DE000FA06UL6')
        fetch.assert_not_called();self.assertTrue(out['sourceDisabled'])

    def sg_snapshot(self):
        product = dict(Id=7069123, Isin='DE000FG4JXV7', ExchangeCode='CBDE',
                       AssetNMP='XAUUSD', AssetIsin='XD0002747026', AssetCurrency='USD',
                       Currency='EUR', Status=65, Name='Gold Classic Turbo')
        props = [dict(Name='Isin', Value=product['Isin']), dict(Name='PutOrCall', Value='Put'),
                 dict(Name='BarrierTurboCertificate', Value=4460, Suffix=' USD'),
                 dict(Name='TimeStamp', Value='2026-10-01T06:46:42.997'),
                 dict(Name='Bid', Value=22.36), dict(Name='Offer', Value=22.37),
                 dict(Name='CurrentLeverage', Value=15.52)]
        return product, props

    def test_sg_chart_dates_only_research_and_expires_without_quote_promotion(self):
        product, _ = self.sg_snapshot()
        points = [dict(Bid=10.50, Ask=10.51, Date='2026-09-30T18:06:00+02:00')]
        result = q.parse_sg_chart_research(product, points, product['Isin'], NOW)
        self.assertTrue(result['chartEvidence']['current'])
        self.assertEqual(result['chartEvidence']['ageSeconds'], 3)
        self.assertFalse(result['found']); self.assertFalse(result['eligible'])
        self.assertNotIn('bidAt', result); self.assertNotIn('leverage', result)
        old = q.parse_sg_chart_research(product, points, product['Isin'], NOW+timedelta(minutes=2))
        self.assertFalse(old['chartEvidence']['current'])
        self.assertFalse(q.freshness(result, NOW)['eligible'])

    def test_sg_chart_rejects_wrong_identity_zone_future_and_crossed_prices(self):
        product, _ = self.sg_snapshot()
        for point in [dict(Bid=10, Ask=11, Date='2026-09-30T16:06:00'),
                      dict(Bid=10, Ask=11, Date='2026-09-30T16:07:00Z'),
                      dict(Bid=11, Ask=10, Date='2026-09-30T16:06:00Z'),
                      dict(Bid=True, Ask=11, Date='2026-09-30T16:06:00Z')]:
            with self.assertRaises((ValueError, TypeError)):
                q.parse_sg_chart_research(product, [point], product['Isin'], NOW)
        product['Id'] = 7127448
        with self.assertRaises(ValueError):
            q.parse_sg_chart_research(product, [dict(Bid=10, Ask=11, Date='2026-09-30T16:06:00Z')], product['Isin'], NOW)

    def test_newly_confirmed_sg_id_routes_direct_without_bnp_cache(self):
        isin = 'DE000FG7K283'
        with patch.dict(q._CACHE, {isin:(__import__('time').monotonic(), {'found':True,'source':'BNP Paribas'})}, clear=True), patch.object(q,'get_bnp_quote') as bnp, patch.object(q, 'get_sg_quote', return_value={'importActive':True}) as sg:
            result=q.get_issuer_quote(isin)
        bnp.assert_not_called(); sg.assert_called_once_with(isin)
        self.assertTrue(result['importActive'])

    def test_sg_direct_conditions_survive_secondary_enrichment(self):
        direct = dict(found=False, productVerified=True, importActive=True,
                      conditions={'ratio': {'value':.1}}, metadata={'status':65})
        with patch('public_product_terms.get_product', return_value={'productVerified':True,'metadata':{'status':1}}), patch.object(q, 'get_issuer_quote', return_value=direct):
            result=q.get_quote('DE000FG7K283')
        self.assertEqual(result['conditions'], direct['conditions'])
        self.assertTrue(result['importActive'])

    def chart_gearing_fixture(self):
        product, props = self.sg_snapshot()
        product['ProductClassificationId'] = 43
        props += [dict(Name='Ratio', Value=10, Suffix=':1'),
                  dict(Name='IsQuanto', Value='Nein')]
        points = [dict(Bid=10.50, Ask=10.51, Date='2026-09-30T18:06:00+02:00')]
        spot = dict(stale=False, data_state=dict(status='fresh'),
                    xau=dict(currency='USD', unit='troy_oz'),
                    spot_usd_oz=4154, price_as_of='2026-09-30T16:05:58Z')
        fx = dict(result='success', base='USD', source='live', sources=dict(EUR='live'),
                  market_session='open', rates=dict(EUR=.884),
                  data_updated_at='2026-09-30T16:05:59Z',
                  effective_at=dict(EUR='2026-09-30T16:05:57Z'))
        return product, props, points, spot, fx

    def test_chart_gearing_needs_no_issuer_leverage_clock_and_keeps_oldest_input(self):
        data = self.chart_gearing_fixture()
        data[1][-3]['Value'] = 999999  # undated issuer leverage is ignored
        result=q.parse_sg_chart_gearing(*data, data[0]['Isin'], NOW)
        evidence=result['gearingEvidence']
        self.assertAlmostEqual(evidence['value'], 4154*.884*.1/10.51)
        self.assertEqual(evidence['ratio'], .1)
        self.assertEqual(evidence['at'], '2026-09-30T16:05:57+00:00')
        self.assertFalse(result['eligible']); self.assertFalse(result['found'])
        self.assertFalse(q.freshness(result, NOW)['eligible'])

    def test_chart_gearing_rejects_stale_skewed_unknown_units_and_future_contracts(self):
        for mutation in ('old-fx','undated-fx','skew','ratio-units','future','quanto','inactive'):
            data = self.chart_gearing_fixture()
            p, props, points, spot, fx = data
            if mutation == 'old-fx': fx['effective_at']['EUR']='2026-09-30T16:00:00Z'
            elif mutation == 'undated-fx': fx['effective_at']['EUR']='2026-09-30T16:05:57'
            elif mutation == 'skew': spot['price_as_of']='2026-09-30T16:05:40Z'
            elif mutation == 'ratio-units': props[-2]['Suffix']=''
            elif mutation == 'future': p['AssetNMP']='C_CMX_GOLD_F_Z26'
            elif mutation == 'quanto': props[-1]['Value']='Ja'
            elif mutation == 'inactive': p['Status']=8
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                q.parse_sg_chart_gearing(*data, p['Isin'], NOW)

    def test_sg_metadata_never_becomes_undated_live_quote(self):
        product, props = self.sg_snapshot()
        x = q.parse_sg(product, props, product['Isin'], NOW)
        self.assertTrue(x['productVerified'])
        self.assertFalse(x['found']); self.assertFalse(x['eligible'])
        self.assertEqual(x['metadata']['direction'], 'SHORT')
        self.assertEqual(x['metadata']['ko'], 4460)
        for key in ('price', 'bid', 'ask', 'leverage', 'quoteAt', 'leverageAt'):
            self.assertNotIn(key, x)
        self.assertFalse(q.freshness(x, NOW)['eligible'])

    def test_sg_barrier_update_is_independent_of_quote_time(self):
        product, props = self.sg_snapshot()
        props.append(dict(Name='StrikeBarrierUpdateTime', Value='2026-09-30T01:12:16.267'))
        result = q.parse_sg(product, props, product['Isin'], NOW)
        evidence = result['metadata']['koEvidence']
        self.assertEqual(evidence['value'], 4460)
        self.assertEqual(evidence['currency'], 'USD')
        self.assertEqual(evidence['updatedAtRaw'], '2026-09-30T01:12:16.267')
        self.assertFalse(evidence['timezoneKnown'])
        self.assertEqual(evidence['retrievedAt'], NOW.isoformat())
        self.assertFalse(result['found']); self.assertFalse(result['eligible'])
        for value in (None, 12, '2026-02-30T01:00:00', 'not a timestamp'):
            props[-1]['Value'] = value
            self.assertIsNone(q.parse_sg(product, props, product['Isin'], NOW)['metadata']['koEvidence'])
        props[-1]['Value'] = '2026-09-30T01:12:16Z'
        self.assertTrue(q.parse_sg(product, props, product['Isin'], NOW)['metadata']['koEvidence']['timezoneKnown'])

    def test_sg_identity_currency_barrier_and_duplicates_rejected(self):
        for key, value in [('Isin', ISIN), ('AssetNMP', 'GOLD-FUTURE'), ('Currency', 'USD'), ('Status', True)]:
            product, props = self.sg_snapshot(); product[key] = value
            with self.assertRaises(ValueError): q.parse_sg(product, props, 'DE000FG4JXV7', NOW)
        product, props = self.sg_snapshot(); props.append(props[0])
        with self.assertRaises(ValueError): q.parse_sg(product, props, product['Isin'], NOW)
        product, props = self.sg_snapshot(); props[2]['Suffix'] = ' EUR'
        with self.assertRaises(ValueError): q.parse_sg(product, props, product['Isin'], NOW)

    def test_sg_knockout_is_explicitly_blocked(self):
        product, props = self.sg_snapshot(); product['Status'] = 8
        x = q.parse_sg(product, props, product['Isin'], NOW)
        self.assertFalse(x['eligible']); self.assertIn('Barriere getroffen', x['reason'])

    def test_sg_adapter_and_issuer_selection(self):
        with patch.dict(q.SG_DIRECT_PRODUCTS, {}, clear=True), patch.object(q,'urlopen') as network:
            for isin in ('DE000FA06UL6',):
                result=q.get_issuer_quote(isin)
                self.assertTrue(result['sourceDisabled']);self.assertFalse(result['eligible'])
            network.assert_not_called()

    def test_sg_future_is_identified_but_never_uses_spot_enrichment(self):
        with patch.object(q,'issuer_json',side_effect=TimeoutError()) as fetch, patch('sg_quotes.get_quote') as enrich:
            result=q.get_sg_quote('DE000FG309G0')
        self.assertFalse(result['productVerified']);self.assertTrue(result['importActive'])
        enrich.assert_not_called()
        # BNP can still be researched; unknown ISINs never probe SG.
        with patch.dict(q._CACHE,{},clear=True), patch.object(q,'get_sg_quote') as sg, patch.object(q,'get_bnp_quote',return_value={'found':False}) as bnp:
            q.get_issuer_quote(ISIN)
        bnp.assert_called_once_with(ISIN);sg.assert_not_called()

    def test_current_snapshot_and_oldest_component_timestamp(self):
        x=q.parse_bnp(snapshot(),ISIN,NOW)
        self.assertTrue(x['eligible']);self.assertEqual(x['ageSeconds'],2.7)
        self.assertEqual(x['price'],16.2);self.assertEqual(x['spread'],.01)
        self.assertEqual(x['ko'],3978.9026);self.assertFalse(x['isDegiroQuote'])
    def test_inclusive_90_second_product_freshness(self):
        x=q.parse_bnp(snapshot(),ISIN,NOW)
        for key in ('quoteAt','bidAt','askAt','leverageAt','snapshotAt'):x[key]=NOW.isoformat()
        self.assertTrue(q.freshness(x,NOW+timedelta(seconds=90))['eligible'])
        self.assertFalse(q.freshness(x,NOW+timedelta(seconds=90.001))['eligible'])
    def test_stale_cached_quote_expires_without_refetch(self):
        x=q.parse_bnp(snapshot(),ISIN,NOW)
        self.assertFalse(q.freshness(x,NOW+timedelta(seconds=90))['eligible'])
    def test_future_missing_closed_knocked_out_and_expired_hours(self):
        self.assertFalse(q.parse_bnp(snapshot(),ISIN,NOW-timedelta(seconds=10))['eligible'])
        for key in ['isMarketClosed','isKnockedOut']:
            data=snapshot();data['result']['config'][key]=True
            self.assertFalse(q.parse_bnp(data,ISIN,NOW)['eligible'])
        data=snapshot();data['tradingHours']['tradingEnd']='2026-09-30T16:00:00Z'
        self.assertFalse(q.parse_bnp(data,ISIN,NOW)['eligible'])
        data=snapshot();del data['result']['bidDate']
        with self.assertRaises(KeyError):q.parse_bnp(data,ISIN,NOW)
    def test_wrong_identity_crossed_quotes_and_currency(self):
        for key,val in [('isin','DE000FC1CHB7'),('ask',16),('leverage',23),('currency',{'isoCode':'USD'}),('bid',float('nan'))]:
            data=snapshot();data['result'][key]=val
            with self.assertRaises(ValueError):q.parse_bnp(data,ISIN,NOW)
    def test_checksum_and_arbitrary_url_blocked(self):
        with patch.object(q,'urlopen') as fetch:
            for value in ['https://localhost','DEOOOPJONB98','DE000PJ9NCK1']:
                self.assertFalse(q.get_issuer_quote(value)['eligible'])
            fetch.assert_not_called()
    def test_every_component_must_be_dated_and_current(self):
        for key in ['bidDate','askDate']:
            data=snapshot();data['result'][key]='2026-09-30T17:55:00'
            self.assertFalse(q.parse_bnp(data,ISIN,NOW)['eligible'])
        data=snapshot();data['result']['keyFigures']['lastUpdate']='2026-09-30T15:55:00Z'
        self.assertFalse(q.parse_bnp(data,ISIN,NOW)['eligible'])
        data=snapshot();data['responseDate']='2026-09-30T16:06:20Z'
        self.assertFalse(q.parse_bnp(data,ISIN,NOW)['eligible'])

if __name__=='__main__':unittest.main()


class BnpDatedTermsTests(unittest.TestCase):
    now = datetime(2026, 10, 6, 7, 30, tzinfo=timezone.utc)
    meta = {'ko':3997.1452, 'strike':3997.1452}
    page = '<script type="application/ld+json">{"@type":"FinancialProduct","identifier":"DE000PJ9NCK0"}</script><table><caption>Stammdaten</caption><tr><th><button>Knock-Out Schwelle (06.10.2026)</button></th><td>3.997,1452 USD</td></tr><tr><th>Basispreis (06.10.2026)</th><td>3.997,1452 USD</td></tr></table>'

    def test_exact_today_rows_without_invented_time(self):
        terms = q.parse_bnp_dated_terms(self.page, ISIN, self.meta, self.now)
        self.assertEqual(terms['strike']['value'],3997.1452)
        self.assertEqual(terms['ko']['dateText'],'06.10.2026')
        self.assertIsNone(terms['ko']['at'])

    def test_wrong_identity_stale_future_conflict_currency_and_duplicate_rejected(self):
        for page in [self.page.replace(ISIN,'DE000PJ9NB98'), self.page.replace('06.10.2026','05.10.2026'), self.page.replace('06.10.2026','07.10.2026'), self.page.replace('3.997,1452','3.997,1453'), self.page.replace('USD','EUR'), self.page.replace('</table>','<tr><th>Basispreis (06.10.2026)</th><td>3.997,1452 USD</td></tr></table>')]:
            with self.subTest(page=page), self.assertRaises(ValueError):
                q.parse_bnp_dated_terms(page, ISIN, self.meta, self.now)
        with self.assertRaises(ValueError):
            q.parse_bnp_dated_terms(self.page, ISIN, self.meta, self.now+timedelta(days=1))

    def test_dated_issuer_terms_survive_secondary_undated_terms(self):
        direct = dict(isin=ISIN,productVerified=True,found=False,eligible=False,metadata=dict(self.meta,termsDated=True,status=1),conditions=q.parse_bnp_dated_terms(self.page,ISIN,self.meta,self.now))
        secondary = dict(productVerified=True,metadata={'status':1,'termsDated':False})
        with patch.object(q,'get_issuer_quote',return_value=direct), patch('public_product_terms.get_product',return_value=secondary):
            result=q.get_quote(ISIN)
        self.assertTrue(result['metadata']['termsDated'])
        self.assertEqual(result['conditions'],direct['conditions'])
        self.assertFalse(result['eligible'])
