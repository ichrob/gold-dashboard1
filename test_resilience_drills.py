"""Run in a credential-free child process; no live outage or live push."""
import json,unittest,subprocess,sys
from unittest.mock import patch,MagicMock
import background_push as b

class Drills(unittest.TestCase):
    def setUp(self):
        self.settings=b.config({'trade':{'active':True,'tradeId':'drill','instrument':'XAU/USD','dir':'LONG','entry':100,'stop':90,'initialRisk':10,'target':150}})
        self.market=dict(ready=True,priceFresh=True,price=105,dataAt=1792396800000,direction='LONG',mtf='LONG',score=80,atr=4)
    def test_quote_recovery(self):
        state={}
        for t in (0,30000,60000):
            state,events=b.advance(state,self.settings,{**self.market,'priceFresh':False,'price':180},False,True,now=t)
            self.assertFalse(any(e['data']['eventKind']=='target' for e in events))
        self.assertIn('data-unavailable',[e['data']['eventKind'] for e in events])
        state,_=b.advance(state,self.settings,self.market,False,True,now=90000)
        _,events=b.advance(state,self.settings,self.market,False,True,now=120000)
        self.assertIn('data-recovered',[e['data']['eventKind'] for e in events])
    def test_transport_recovery(self):
        from test_background_push import BackgroundDelivery
        case=BackgroundDelivery('test_background_failure_keeps_checkpoint_and_success_persists')
        result=unittest.TestResult();case.run(result)
        self.assertTrue(result.wasSuccessful(),str(result.errors+result.failures))
    def test_restart(self):
        state,events=b.advance({},self.settings,{**self.market,'price':89},False,True)
        self.assertIn('stop-hit',[e['data']['eventKind'] for e in events])
        restored=json.loads(json.dumps(state))
        script="import json,sys,background_push as b; p=json.load(sys.stdin); s,e=b.advance(p['state'],p['settings'],p['market'],False,True,log=False); print(json.dumps(e))"
        result=subprocess.run([sys.executable,'-c',script],input=json.dumps(dict(state=restored,settings=self.settings,market={**self.market,'price':89})),text=True,capture_output=True,timeout=5,check=True)
        events=json.loads(result.stdout)
        self.assertNotIn('stop-hit',[e['data']['eventKind'] for e in events])
        self.assertEqual(restored['trade']['stop'],state['trade']['stop'])
