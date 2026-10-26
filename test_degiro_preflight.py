import json
import logging
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
import requests
import degiro_preflight as parent
import degiro_preflight_worker as worker

PAYLOAD = {'isin':'DE000FG7Q3A9','side':'BUY','quantity':1,'price':10.0,'currency':'EUR','otp':'001234'}


class PreflightTests(unittest.TestCase):
    def tearDown(self):
        logging.disable(logging.NOTSET)

    def exercise(self, scenario='ok'):
        calls=[]
        def send(session, request, **kwargs):
            calls.append(request)
            self.assertEqual(kwargs['timeout'],(5,8));self.assertFalse(kwargs['allow_redirects'])
            path=urlsplit(request.url).path
            status=200
            product={'id':'123','isin':PAYLOAD['isin'],'currency':'EUR'}
            if '/login/secure/' in path:
                data={'sessionId':'FAKE_SESSION','status':0}
                if scenario=='auth':status=400;data={'status':6,'secret':'NEVER_SHOW'}
            elif path=='/pa/secure/client':data={'data':{'intAccount':123}}
            elif path.endswith('/lookup'):
                data={'products':[product,product] if scenario=='ambiguous' else [product]}
            elif path.endswith('/info'):
                if scenario=='identity':product['isin']='DE000BY4TLN0'
                if scenario=='currency':product['currency']='CHF'
                data={'data':{'123':product}}
            elif '/checkOrder;' in path:
                body=json.loads(request.body)
                self.assertEqual(body,{'buySell':'BUY','orderType':0,'productId':123,'size':1,'price':10.0,'timeType':1})
                data={'data':{'confirmationId':'NEVER_SHOW'}}
                if scenario=='rejected':status=400;data={'errors':[{'message':'NEVER_SHOW'}]}
                if scenario=='invalid':data={'data':{}}
                if scenario=='redirect':status=302;data={}
            elif '/logout;' in path:data={}
            else:raise AssertionError('Unexpected request '+path)
            r=requests.Response();r.status_code=status;r._content=json.dumps(data).encode();r.request=request
            return r
        with patch.dict('os.environ',{'BOB_DEGIRO_USERNAME':'fake','BOB_DEGIRO_PASSWORD':'NEVER_SHOW'}),patch.object(requests.Session,'send',send):
            result=worker.run(PAYLOAD)
        self.assertNotIn('NEVER_SHOW',json.dumps(result))
        self.assertFalse(any('/v5/order' in r.url for r in calls))
        return result,calls

    def test_positive_single_preview_and_logout(self):
        result,calls=self.exercise()
        self.assertEqual(result['code'],'PRECHECK_RESPONSE')
        self.assertTrue(result['logoutConfirmed'])
        self.assertEqual(sum('/checkOrder;' in r.url for r in calls),1)

    def test_unconfirmed_identity_never_reaches_check(self):
        for case in ('identity','currency','ambiguous'):
            with self.subTest(case=case):
                result,calls=self.exercise(case)
                self.assertEqual(result['code'],'IDENTITY_UNCONFIRMED')
                self.assertFalse(any('/checkOrder;' in r.url for r in calls))

    def test_negative_invalid_redirect_and_auth_do_not_promote(self):
        for case,code in [('rejected','BROKER_REJECTED'),('invalid','UNVERIFIED_RESPONSE'),('redirect','UNVERIFIED_RESPONSE'),('auth','AUTH_REQUIRED')]:
            with self.subTest(case=case):
                result,calls=self.exercise(case)
                self.assertEqual(result['code'],code)
                self.assertLessEqual(sum('/checkOrder;' in r.url for r in calls),1)

    def test_transport_rejects_confirmation_modification_deletion_and_redirect_hosts(self):
        base='https://trader.degiro.nl'
        for method,path in [('POST','/trading/secure/v5/order'),('POST','/trading/secure/v5/order/token;jsessionid=abc'),('PUT','/trading/secure/v5/order/1'),('DELETE','/trading/secure/v5/order/1'),('GET','/trading/secure/v5/checkOrder;jsessionid=abc'),('POST','/trading/secure/v5/checkOrder;jsessionid=abc/extra')]:
            self.assertFalse(worker.permitted(method,base+path))
        for base in ('http://trader.degiro.nl','https://trader.degiro.nl.evil.example','https://user@trader.degiro.nl'):
            self.assertFalse(worker.permitted('POST',base+'/trading/secure/v5/checkOrder;jsessionid=abc'))

    def test_invalid_inputs_and_unconfigured_do_not_launch(self):
        for delta in ({'quantity':True},{'price':float('nan')},{'side':'SHORT'},{'confirm':True},{'isin':'DE0000000000'},{'otp':'123'}):
            with self.assertRaises(ValueError):parent.validate(dict(PAYLOAD,**delta))
        with patch('degiro_sync.status',return_value={'running':False}),patch.object(parent.degiro_readonly,'status',return_value={'ready':False}),patch.object(parent.subprocess,'run') as launch:
            self.assertEqual(parent.probe(PAYLOAD)['code'],'SETUP_REQUIRED');launch.assert_not_called()

    def test_parent_strips_tokens_and_never_grants_trade_approval(self):
        parent._LAST=0
        with patch('degiro_sync.status',return_value={'running':False}),patch.object(parent.degiro_readonly,'status',return_value={'ready':True}),patch.object(parent.degiro_readonly,'_LAST_ATTEMPT',0),patch.object(parent.subprocess,'run') as launch:
            launch.return_value.stdout=json.dumps({'code':'PRECHECK_RESPONSE','confirmationId':'NEVER_SHOW','ordersEnabled':True})
            launch.return_value.returncode=0
            result=parent.probe(PAYLOAD)
        self.assertFalse(result['tradeApproved']);self.assertFalse(result['ordersEnabled'])
        self.assertNotIn('NEVER_SHOW',json.dumps(result));self.assertNotIn('otp',result)
