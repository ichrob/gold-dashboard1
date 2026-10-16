import unittest,json
from datetime import datetime,timezone
from unittest.mock import Mock,patch
import trade_learning_review as r
import real_trade_journal as j

class LearningReviewTests(unittest.TestCase):
 def snapshot(self):
  return dict(tradeId='test',active=False,dir='LONG',product=dict(entry=10,currency='EUR'),
   purchase=dict(executedLocal='01.10.2026 10:00:00'),
   exitReceipt=dict(executedLocal='01.10.2026 11:00:00'),
   settlement=dict(purchaseTotalCHF=20,saleTotalCHF=18))
 def test_window_and_full_extrema_with_stop_trace(self):
  s=self.snapshot();c=Mock();start,end,assumed=r.window(s)
  c.execute.return_value.fetchone.return_value=(900,8,12,start,end)
  c.execute.return_value.fetchall.return_value=[(start,dict(ready=True,priceFresh=True,direction='SHORT',planAfter=dict(stop=9),recommendations=[{}])),(end,dict(planAfter=dict(stop=8)))]
  out=r.review(c,s)
  self.assertEqual(out['realizedNetCHF'],-2)
  self.assertEqual(out['modelObservations'],900)
  self.assertEqual((out['modelMaePct'],out['modelMfePct']),(-20,20))
  self.assertEqual(out['trace']['stopLoosenings'],1)
  self.assertEqual(out['trace']['adverseObservations'],1)
  self.assertTrue(assumed);self.assertFalse(out['learning']['automaticRuleChange'])
  for call in c.execute.call_args_list:
   self.assertIn('<=%s',call.args[0]);self.assertEqual(call.args[1][1:3],(start,end))
  self.assertEqual(start.astimezone(timezone.utc).hour,8)
 def test_missing_execution_window_does_not_query_post_sale_data(self):
  s=self.snapshot();s['exitReceipt']={};c=Mock()
  self.assertEqual(r.review(c,s)['modelObservations'],0);c.execute.assert_not_called()
 def test_late_settlement_preserves_closed_state(self):
  s=self.snapshot();s.pop('settlement');c=Mock()
  c.execute.return_value.fetchall.side_effect=[[('test',s)],[]]
  pair=dict(purchaseTotalCHF=20,saleTotalCHF=18,netCHF=-2)
  s['exitReceipt']['orderIdDigest']='a'*64
  with patch.object(j,'sale_matches',return_value=True),patch.object(j,'matched_email_chf_settlement',return_value=pair),patch.object(j,'event'):
   self.assertEqual(j.recover_closed_settlements(c),1)
  update=next(x for x in c.execute.call_args_list if x.args[0].startswith('UPDATE'))
  saved=json.loads(update.args[1][0])
  self.assertFalse(saved['active']);self.assertEqual(saved['evaluation']['realizedNetCHF'],-2)
  query=c.execute.call_args_list[0].args[0]
  self.assertIn("snapshot->'actualExecution' IS NULL",query)
  self.assertIn("snapshot->'settlement' IS NULL",query)
 def test_recovery_no_eligible_trades_is_noop(self):
  c=Mock();c.execute.return_value.fetchall.return_value=[]
  self.assertEqual(j.recover_closed_settlements(c),0);self.assertEqual(c.execute.call_count,1)

if __name__=='__main__':unittest.main()
