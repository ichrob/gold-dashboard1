import unittest
import background_push as b

class PersonalRiskTests(unittest.TestCase):
 def test_budget_alert_and_guards(self):
  model=dict(simpleSpotTurbo=True,referenceConfirmed=True,currency='EUR',direction='LONG',isin='DE0000000001',bid=10,goldReference=100,fxReference=1,fxScenario=1,ratio=1,strike=50,ko=50,entry=10,quantity=5,source='test',referenceAt='2026-10-04T17:00:00Z')
  trade=dict(active=True,tradeId='risk-test',instrument='XAU/USD',dir='LONG',entry=100,stop=90,initialRisk=10,product=model,personalRisk=dict(account=500,percent=1))
  cfg=b.config(dict(trade=trade));m=dict(ready=True,priceFresh=True,price=99,direction='LONG',mtf='LONG')
  def alerts(state,cfg,m):
   state,events=b.advance(state,cfg,m,False,True)
   return state,[e for e in events if e['data']['eventKind']=='personal-risk']
  state,events=alerts({},cfg,m);self.assertEqual(len(events),1);self.assertIn('5.00 EUR',events[0]['body'])
  self.assertEqual(alerts(state,cfg,m)[1],[])
  self.assertEqual(alerts({},cfg,{**m,'price':99.1})[1],[])
  self.assertEqual(alerts({},cfg,{**m,'priceFresh':False})[1],[])
  for key in ('personalRisk','product'):
   clean=b.config(dict(trade={**trade,key:None}));self.assertEqual(alerts({},clean,m)[1],[])
  short=b.config(dict(trade={**trade,'dir':'SHORT','stop':110,'product':{**model,'direction':'SHORT','ko':150}}))
  self.assertEqual(len(alerts({},short,{**m,'price':101})[1]),1)
 def test_invalid_budget(self):
  from test_background_push import BackgroundRules
  x=BackgroundRules();x.setUp()
  for p in ({'account':0,'percent':1},{'account':500,'percent':101}):
   with self.assertRaises(ValueError):b.config({'trade':{**x.settings['trade'],'personalRisk':p}})
if __name__=='__main__':unittest.main()
