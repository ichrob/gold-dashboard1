import unittest
from degiro_product_probe import collect, evidence, validate_isins
from degiro_readonly_worker import permitted

class ProbeTests(unittest.TestCase):
    def test_validation(self):
        for values in ('DE0000000000', ['bad'], ['DE0000000000']*4):
            with self.assertRaises(ValueError): validate_isins(values)

    def test_fields_keep_original_time_and_strip_secrets(self):
        self.assertEqual(evidence({'bid':1.2,'ask':1.3,'bidTime':'original','sessionId':'secret'}),
                         {'bid':1.2,'ask':1.3,'bidTime':'original'})

    def test_transport(self):
        root='https://trader.degiro.nl'
        self.assertTrue(permitted('GET',root+'/product_search/secure/v5/products/lookup?q=x'))
        self.assertTrue(permitted('POST',root+'/product_search/secure/v5/products/info'))
        for method in ('GET','POST','PUT','DELETE'):
            self.assertFalse(permitted(method,root+'/trading/secure/v5/order'))
        self.assertFalse(permitted('GET',root+'/arbitrary'))
        self.assertFalse(permitted('GET','https://charting.vwdservices.com/other'))

    def test_collection_exact_isin_and_missing_quote(self):
        class API:
            def product_search(self, **kwargs):
                return {'products':[{'id':'1','isin':'DE0000000000','bid':1.2,'tradingStatus':'source-value'},
                                    {'id':'2','isin':'WRONG'}]}
            def get_products_info(self, **kwargs):
                return {'data':{'1':{'isin':'DE0000000000','ask':1.3}}}
        report=collect(API(), None, ['DE0000000000'])
        match=report['products'][0]['matches'][0]
        self.assertEqual(len(report['products'][0]['matches']),1)
        self.assertEqual(match['product']['bid'],1.2)
        self.assertEqual(match['product']['ask'],1.3)
        self.assertEqual(match['quote'],{})
        self.assertEqual(report['approval'],'UNVERIFIED')
