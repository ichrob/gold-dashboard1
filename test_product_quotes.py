import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import product_quotes as q

ISIN='DE000PJ9NCK0'
NOW=datetime(2026,9,30,16,6,3,tzinfo=timezone.utc)
def snapshot():
    return dict(responseDate='2026-09-30T16:06:02Z',tradingHours=dict(isTradeable=True,tradingStart='2026-09-30T06:00:00Z',tradingEnd='2026-09-30T20:00:00Z'),result=dict(isin=ISIN,productName='GOLD Unlimited Long',issuerCompanyName='BNP Paribas',currency=dict(isoCode='EUR'),first=dict(underlyingISIN='USFX00000XAU',currency=dict(isoCode='USD'),knockOutAbsolute=3978.9026),keyFigures=dict(leverage=22.67,lastUpdate='2026-09-30T16:06:02Z'),config=dict(hasMultipleUnderlying=False,isPublicTradable=True,isMarketClosed=False,isKnockedOut=False,isMaturedOrKnockOut=False,isCanceled=False,isLifeCycleEnded=False,isBidOnly=False,isPercentageQuotation=False),bid=16.19,ask=16.2,bidSize=8000,askSize=8000,leverage=22.67,bidDate='2026-09-30T18:06:00.282',askDate='2026-09-30T18:06:00.282'))

class ProductQuoteTests(unittest.TestCase):
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
        product, props = self.sg_snapshot()
        with patch.object(q, 'issuer_json', side_effect=[product, props]) as fetch, \
             patch('sg_quotes.get_quote', return_value=q.parse_sg(product, props, product['Isin'])):
            x = q.get_sg_quote(product['Isin'])
            self.assertTrue(x['productVerified'])
            self.assertIn('/Products/AllProperties/7069123', fetch.call_args_list[1].args[0])
        q._CACHE.clear()
        with patch.object(q, 'get_bnp_quote', return_value={'found':False}), patch.object(q, 'get_sg_quote', return_value=x):
            result = q.get_quote(product['Isin'])
            self.assertTrue(result['productVerified']); self.assertFalse(result['eligible'])
        q._CACHE.clear()

    def test_sg_future_is_identified_but_never_uses_spot_enrichment(self):
        product, _ = self.sg_snapshot()
        product['AssetNMP'] = 'C_CMX_GOLD_F_Z26'
        with patch.object(q, 'issuer_json', return_value=product) as fetch, \
             patch('sg_quotes.get_quote') as enrich:
            result = q.get_sg_quote(product['Isin'])
        self.assertTrue(result['productVerified'])
        self.assertFalse(result['eligible'])
        self.assertIn('kein XAU/USD-Spot', result['reason'])
        self.assertEqual(fetch.call_count, 1)
        enrich.assert_not_called()

    def test_current_snapshot_and_oldest_component_timestamp(self):
        x=q.parse_bnp(snapshot(),ISIN,NOW)
        self.assertTrue(x['eligible']);self.assertEqual(x['ageSeconds'],2.7)
        self.assertEqual(x['price'],16.2);self.assertEqual(x['spread'],.01)
        self.assertEqual(x['ko'],3978.9026);self.assertFalse(x['isDegiroQuote'])
    def test_stale_cached_quote_expires_without_refetch(self):
        x=q.parse_bnp(snapshot(),ISIN,NOW)
        self.assertFalse(q.freshness(x,NOW+timedelta(seconds=60))['eligible'])
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
                self.assertFalse(q.get_quote(value)['eligible'])
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
