import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,patch
import trade_stop_review as s

class StopReviewTests(unittest.TestCase):
 def test_changed_stops_and_confirmations_keep_model_separate(self):
  at=datetime(2026,10,14,10,tzinfo=timezone.utc);c=Mock()
  proposal=dict(planAfter=dict(stop=100),productEvidence=dict(stop=9,price=10,currency='EUR'))
  c.execute.return_value.fetchall.return_value=[
   (3,at+timedelta(minutes=1),'broker-stop-confirmation',dict(recommendationSeq=1,action='filled',price=8.8,at=(at+timedelta(seconds=30)).isoformat())),
   (2,at+timedelta(seconds=20),'observation',proposal),(1,at,'observation',proposal)]
  c.execute.return_value.fetchone.return_value=({},)
  out=s.read(c,'t')['rows']
  self.assertEqual(len(out),1);self.assertEqual(out[0]['confirmations'][0]['reactionSeconds'],30)
  self.assertEqual(out[0]['confirmations'][0]['differenceFromProposal'],-.2)
  self.assertFalse(out[0]['brokerVerified'])
 def test_confirmation_never_closes_or_places_order(self):
  at=datetime(2026,10,14,10,tzinfo=timezone.utc);c=Mock()
  c.execute.return_value.fetchone.side_effect=[(at,dict(planAfter=dict(stop=100))),({'product':{'currency':'EUR'}},)]
  payload=dict(tradeId='t',recommendationSeq=1,action='set',price=9,currency='EUR',at='2026-10-14T10:01:00Z',userConfirmed=True)
  with patch('real_trade_journal.event') as event:
   out=s.confirm(c,payload);self.assertFalse(out['ordersPlaced']);event.assert_called_once()
  self.assertTrue(all(x.args[0].startswith('SELECT') for x in c.execute.call_args_list))
 def test_missing_confirmation_rejected(self):
  with self.assertRaises(ValueError):s.confirm(Mock(),dict(tradeId='t',recommendationSeq=1,action='set'))
 def test_after_sale_observations_excluded(self):
  c=Mock();at=datetime(2026,10,14,12,tzinfo=timezone.utc)
  c.execute.return_value.fetchall.return_value=[(1,at,'observation',dict(planAfter=dict(stop=100)))]
  c.execute.return_value.fetchone.return_value=({'purchase':{'at':'2026-10-14T10:00:00Z'},'exitReceipt':{'executedAt':'2026-10-14T11:00:00Z'}},)
  self.assertEqual(s.read(c,'t')['rows'],[])

class ConfirmationValidationTests(unittest.TestCase):
 def test_invalid_price_clock_currency_and_future_rejected(self):
  base=dict(tradeId='t',recommendationSeq=1,action='set',price=9,currency='EUR',at='2026-10-14T10:01:00Z',userConfirmed=True)
  for change in ({'price':float('nan')},{'currency':'CHF'},{'at':'2026-10-14T10:01:00'},{'at':'2099-10-14T10:01:00Z'},{'at':'2026-10-14T09:59:00Z'}):
   c=Mock();c.execute.return_value.fetchone.side_effect=[(datetime(2026,10,14,10,tzinfo=timezone.utc),dict(planAfter=dict(stop=100))),({'product':{'currency':'EUR'}},)]
   with patch('real_trade_journal.event') as event:
    with self.assertRaises(ValueError):s.confirm(c,{**base,**change})
    event.assert_not_called()
 def test_swiss_time_picker_converts_explicit_user_zone(self):
  c=Mock();c.execute.return_value.fetchone.side_effect=[(datetime(2026,10,14,10,tzinfo=timezone.utc),dict(planAfter=dict(stop=100))),({'product':{'currency':'EUR'}},)]
  with patch('real_trade_journal.event') as event:
   s.confirm(c,dict(tradeId='t',recommendationSeq=1,action='set',price=9,currency='EUR',localAt='2026-10-14T12:01:00',timezone='Europe/Zurich',userConfirmed=True))
  self.assertEqual(event.call_args.args[3]['at'],'2026-10-14T12:01:00+02:00')
