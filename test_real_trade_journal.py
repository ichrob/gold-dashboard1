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
if __name__=='__main__':unittest.main()
