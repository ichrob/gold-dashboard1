import json,unittest
from unittest.mock import Mock,patch
import real_trade_journal as j
class JournalTests(unittest.TestCase):
 def trade(self,**kw):return dict(tradeId='real-1',active=True,dir='LONG',entry=100,stop=90,target=120,initialRisk=10,**kw)
 def conn(self,previous=None):
  c=Mock();c.execute.return_value.fetchone.return_value=previous;return c
 def test_test_trade_rejected(self):
  c=self.conn()
  with self.assertRaises(ValueError):j.handle(c,'write',{'trade':self.trade(test=True)})
  c.execute.assert_not_called()
 def test_closed_cannot_reopen(self):
  with self.assertRaises(ValueError):j.handle(self.conn((False,{})),'write',{'trade':self.trade()})
 def test_execution_only_user_values_and_no_short_inversion(self):
  t=self.trade();t.update(active=False,dir='SHORT',actualExecution=dict(entryEUR=2,exitEUR=3,quantity=10,feesEUR=2))
  c=self.conn((True,{}));j.handle(c,'write',{'trade':t})
  saved=json.loads(c.execute.call_args_list[1].args[1][2]);self.assertEqual(saved['actualExecution']['netEUR'],8)
  self.assertFalse(saved['active'])
 def test_observes_without_push_subscription_and_keeps_recommendations(self):
  c=self.conn();settings={'trade':self.trade()};c.execute.return_value.fetchall.return_value=[('real-1',settings,{})]
  with patch.object(j.background_push,'analyze',return_value={'price':101,'dataAt':1}),patch.object(j.background_push,'advance',return_value=({'trade':{'stop':95}},[{'title':'STOP'}])) as advance,patch.object(j,'event') as event:
   j.observe(c,{})
   self.assertEqual(advance.call_args.args[-2:],(False,True))
   self.assertEqual(event.call_args.args[3]['recommendations'],[{'title':'STOP'}])
   self.assertEqual(event.call_args.args[3]['planAfter']['stop'],95)
class PurchaseTests(unittest.TestCase):
 def purchase(self):
  return {'recordOnly':True,'active':False,'dir':'SHORT','product':{'isin':'DE000AA00000','entry':9.73,'quantity':2},'purchase':{'transactionId':'test-42','at':'2026-10-14T10:54:59+02:00','feesCHF':0.52,'totalCHF':18.67}}
 def conn(self):
  c=Mock();c.execute.return_value.fetchone.side_effect=[None,('id',)];return c
 def test_purchase_without_market_model_persists_but_never_activates(self):
  c=self.conn()
  with patch.object(j.background_push,'config') as config:
   r=j.handle(c,'write',{'trade':self.purchase()});config.assert_not_called()
  self.assertTrue(r['recordOnly'])
  saved=json.loads(c.execute.call_args_list[1].args[1][1])
  self.assertFalse(saved['active']);self.assertEqual(saved['monitoringStatus'],'pending-evidence')
  self.assertEqual(saved['product']['entry'],9.73)
 def test_duplicate_is_idempotent_and_conflicts_rejected(self):
  c=self.conn();j.handle(c,'write',{'trade':self.purchase()})
  saved=json.loads(c.execute.call_args_list[1].args[1][1]);c=Mock();c.execute.return_value.fetchone.return_value=(False,saved)
  self.assertTrue(j.handle(c,'write',{'trade':self.purchase()})['duplicate'])
  t=self.purchase();t['product']['entry']=10
  with self.assertRaises(ValueError):j.handle(c,'write',{'trade':t})
 def test_missing_timezone_invalid_quantity_and_active_rejected(self):
  for change in ('timezone','quantity','active'):
   t=self.purchase()
   if change=='timezone':t['purchase']['at']='2026-10-14T10:54:59'
   if change=='quantity':t['product']['quantity']=float('nan')
   if change=='active':t['active']=True
   c=Mock()
   with self.assertRaises(ValueError):j.handle(c,'write',{'trade':t})
   c.execute.assert_not_called()
if __name__=='__main__':unittest.main()
