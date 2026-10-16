import json,unittest
from datetime import datetime,timezone
from unittest.mock import Mock
import background_push as b
import real_trade_journal as journal
from trade_reference import align
from test_trade_reference import ReferenceTests

class ChfTradeTests(unittest.TestCase):
 def model(self):
  return dict(isin='CH0000000000',currency='CHF',direction='LONG',simpleSpotTurbo=True,referenceConfirmed=True,bid=20,goldReference=4200,fxReference=.8,fxScenario=.8,ratio=.1,strike=4000,ko=4000,entry=21,quantity=10,source='original',referenceAt='2026-10-15T10:00:00Z')
 def test_native_model_and_ko(self):
  m=b.product_model(self.model(),'LONG')
  self.assertEqual(b.product_price(m,4250),24)
  self.assertIsNone(b.product_price(m,4000))
  self.assertIn('CHF/Stück',b.level_text({'product':m},4250))
 def test_reference_is_direct_usd_chf_and_rejects_eur(self):
  s,g,f=ReferenceTests().fixture()
  with self.assertRaises(ValueError):align('02/10/2026 19:49',g,f,s+3600,currency='CHF')
  f['chart']['result'][0]['meta'].update(symbol='USDCHF=X',currency='CHF')
  f['chart']['result'][0]['indicators']['quote'][0]['close']=[.8]
  x=align('02/10/2026 19:49',g,f,s+3600,currency='CHF')
  self.assertEqual(x['currency'],'CHF');self.assertEqual(x['fxReference'],.8)
 def test_background_uses_chf_fx(self):
  now=int(datetime(2026,10,15,10,tzinfo=timezone.utc).timestamp()*1000)
  settings=b.config({'trade':dict(active=True,tradeId='CHF-test',instrument='XAU/USD',dir='LONG',entry=4200,stop=4100,initialRisk=100,target=4250,product=self.model())})
  market=dict(ready=True,priceFresh=True,price=4255,dataAt=now,direction='LONG',mtf='LONG',score=80,atr=4,fx={'rate':.95,'fetchedAt':'2026-10-15T10:00:00Z'})
  _,events=b.advance({},settings,market,False,True,now=now,log=False)
  text=' '.join(x['body'] for x in events)
  self.assertIn('CHF/Stück',text);self.assertIn('24.0000',text)
  market['fxByCurrency']={'CHF':{'rate':.82,'fetchedAt':'2026-10-15T10:00:00Z'}}
  _,events=b.advance({},settings,market,False,True,now=now,log=False)
  self.assertIn('24.5000',' '.join(x['body'] for x in events))
 def test_actual_execution_native_and_currency_immutable(self):
  t=dict(tradeId='CHF-test',active=False,dir='LONG',product=self.model(),actualExecution=dict(entryCHF=21,exitCHF=24,quantity=10,feesCHF=2))
  c=Mock();c.execute.return_value.fetchall.return_value=[];c.execute.return_value.fetchone.return_value=(True,{'product':self.model()})
  journal.handle(c,'write',{'trade':t})
  call=next(x for x in c.execute.call_args_list if 'INSERT INTO bob_real_trades' in x.args[0])
  self.assertEqual(json.loads(call.args[1][2])['actualExecution']['netCHF'],28)
  t['actualExecution']=dict(entryEUR=21,exitEUR=24,quantity=10,feesEUR=2)
  with self.assertRaises(ValueError):journal.handle(c,'write',{'trade':t})
  t.pop('actualExecution');t['product']={**self.model(),'currency':'EUR'}
  with self.assertRaises(ValueError):journal.handle(c,'write',{'trade':t})
if __name__=='__main__':unittest.main()
