import json
import threading
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import degiro_sync
from degiro_sync_data import read_snapshot
from degiro_readonly_worker import permitted


def portfolio(size=2, price=12.3):
    return {'portfolio':{'value':[{'id':'123','value':[
        {'name':'positionType','value':'PRODUCT'}, {'name':'size','value':size},
        {'name':'price','value':price},{'name':'value','value':24.6}]}]}}


class SyncTests(unittest.TestCase):
    def test_read_only_details_and_no_order(self):
        self.assertTrue(permitted('POST','https://trader.degiro.nl/product_search/secure/v5/products/info'))
        self.assertFalse(permitted('POST','https://trader.degiro.nl/trading/secure/v5/order'))
        self.assertFalse(permitted('POST','https://evil.example/product_search/secure/v5/products/info'))

    def test_valuation_never_promoted_to_quote(self):
        api=Mock()
        api.get_products_info.return_value={'data':{'123':{'id':'123','isin':'DE000PJ9NB98','name':'Example','currency':'EUR','SECRET':'hidden'}}}
        result=read_snapshot(api,portfolio())
        row=result['holdings'][0]
        self.assertEqual(row['quantity'],2)
        self.assertEqual(row['valuationPrice'],12.3)
        self.assertIsNone(row['sourceAt'])
        self.assertFalse(row['tradeApproved'])
        self.assertFalse(result['liveQuotes'])
        self.assertNotIn('SECRET',json.dumps(result))

    def test_empty_is_authoritative_but_invalid_is_not(self):
        api=Mock()
        self.assertEqual(read_snapshot(api,{'portfolio':{'value':[]}})['holdings'],[])
        api.get_products_info.assert_not_called()
        for bad in [None,{}, {'portfolio':{'value':None}},portfolio(size='bad')]:
            with self.assertRaises(ValueError):read_snapshot(api,bad)

    def test_wrong_product_identity_rejected(self):
        api=Mock();api.get_products_info.return_value={'data':{'123':{'id':'456'}}}
        with self.assertRaises(ValueError):read_snapshot(api,portfolio())

    def test_stale_and_stopped_never_current(self):
        now=datetime.now(timezone.utc)
        proc=Mock();proc.poll.return_value=None
        with patch.object(degiro_sync,'_PROCESS',proc),patch.object(degiro_sync,'_STATE',{'code':'READ_OK','snapshot':{'observedAt':now.isoformat(),'holdings':[]}}):
            self.assertTrue(degiro_sync.status()['fresh'])
            degiro_sync._STATE['snapshot']['observedAt']=(now-timedelta(seconds=91)).isoformat()
            self.assertFalse(degiro_sync.status()['fresh'])
            degiro_sync._STATE['snapshot']['observedAt']=now.isoformat();proc.poll.return_value=0
            self.assertFalse(degiro_sync.status()['fresh'])

    def test_start_no_credentials_never_launches(self):
        with patch.object(degiro_sync,'_PROCESS',None),patch.object(degiro_sync.degiro_readonly,'status',return_value={'ready':False}),patch.object(degiro_sync.subprocess,'Popen') as launch:
            self.assertEqual(degiro_sync.start()['code'],'SETUP_REQUIRED');launch.assert_not_called()

    def test_real_sdk_reuses_session_and_logs_out(self):
        import os, requests
        import degiro_readonly_worker as worker
        calls=[]; stop=threading.Event(); emitted=[]
        def send(session,request,**kwargs):
            calls.append(request.url)
            if '/login/' in request.url: payload={'sessionId':'SECRET_SESSION','status':0}
            elif '/pa/secure/client' in request.url: payload={'data':{'intAccount':123}}
            elif '/update/' in request.url: payload=portfolio()
            elif '/products/info' in request.url: payload={'data':{'123':{'id':'123','isin':'DE000PJ9NB98','currency':'EUR'}}}
            else: payload={}
            response=requests.Response();response.status_code=200;response._content=json.dumps(payload).encode();response.request=request
            return response
        def emit(data): emitted.append(data);stop.set()
        with patch.dict(os.environ,{'BOB_DEGIRO_USERNAME':'fake','BOB_DEGIRO_PASSWORD':'fake'}),patch.object(requests.Session,'send',send):
            result=worker.run('',emit,stop)
        self.assertEqual(result['code'],'STOPPED');self.assertTrue(result['logoutConfirmed'])
        self.assertEqual(len([c for c in calls if '/login/' in c]),1)
        self.assertEqual(emitted[0]['snapshot']['holdings'][0]['quantity'],2)
        self.assertNotIn('SECRET_SESSION',json.dumps(emitted))
