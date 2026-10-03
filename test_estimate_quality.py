import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import estimate_quality as e

NOW=datetime(2026,10,1,12,tzinfo=timezone.utc)
def at(s):return (NOW+timedelta(seconds=s)).isoformat()

class QualityTests(unittest.TestCase):
 def setUp(self):
  for name in ('_pending','_errors','_seen','_truth_receipts'):
   p=patch.object(e,name,{});p.start();self.addCleanup(p.stop)
 def test_frozen_prediction_matches_once_and_separates_horizons(self):
  e.record('x',102,at(60),at(0),at(61));e.record('x',100,at(60),at(0),at(62))
  e.observe('x',100,at(60),at(80));e.observe('x',99,at(60),at(81))
  q=e.quality('x',60,NOW+timedelta(seconds=90))
  self.assertEqual(q['sampleCount'],1);self.assertEqual(q['maxAbsoluteError'],2)
  self.assertEqual(e.quality('x',120,NOW+timedelta(seconds=90))['sampleCount'],0)
 def test_readiness_needs_distinct_times_span_and_recent_validation(self):
  for i in range(21):
   s=60+i*30;e.record('x',102,at(s),at(s-45),at(s));e.observe('x',100,at(s),at(s+10))
  q=e.quality('x',45,NOW+timedelta(seconds=700));self.assertTrue(q['ready']);self.assertFalse(q['isConfidenceInterval'])
  self.assertFalse(e.quality('x',45,NOW+timedelta(seconds=2500))['ready'])
 def test_wrong_time_future_and_after_receipt_not_matched(self):
  e.record('x',102,at(60),at(0),at(100))
  e.observe('x',100,at(60),at(80));e.observe('x',100,at(66),at(110))
  self.assertEqual(e.quality('x',60,NOW+timedelta(seconds=120))['sampleCount'],0)
  e.observe('x',100,at(60),at(110));self.assertEqual(e.quality('x',60,NOW+timedelta(seconds=120))['sampleCount'],0)

 def test_truth_before_prediction_cannot_be_reused_after_later_poll(self):
  e.observe('x',100,at(60),at(80))
  e.record('x',100,at(60),at(0),at(90))
  e.observe('x',100,at(60),at(100))
  self.assertEqual(e.quality('x',60,NOW+timedelta(seconds=110))['sampleCount'],0)
  e.record('x',102,at(120),at(60),at(121))
  e.observe('x',100,at(120),at(140))
  self.assertEqual(e.quality('x',60,NOW+timedelta(seconds=150))['sampleCount'],1)

 def test_durable_comparisons_restore_without_refreshing_receipt_or_duplicates(self):
  from bob_validation_store import KEY
  pairs=[dict(bucket='0–60s',predictionAt=at(60+i*30),prediction=102,referenceAt=at(15+i*30),
              predictionReceivedAt=at(61+i*30),truthAt=at(60+i*30),truth=100,truthReceivedAt=at(70+i*30)) for i in range(21)]
  now=NOW+timedelta(seconds=700)
  e.restore_durable(pairs,now);q=e.quality(KEY,45,now)
  self.assertTrue(q['ready']);self.assertEqual(q['sampleCount'],21);self.assertEqual(q['maxAbsoluteError'],2)
  e.restore_durable(pairs,now);self.assertEqual(e.quality(KEY,45,now)['sampleCount'],21)
  self.assertEqual(q['lastValidationAt'],at(670))
  self.assertFalse(e.quality(KEY,45,NOW+timedelta(seconds=2500))['ready'])
  with self.assertRaises(ValueError):e.restore_durable([dict(pairs[0],predictionReceivedAt=at(71))],now)
  self.assertEqual(e.quality(KEY,45,now)['sampleCount'],21)
  with self.assertRaises(ValueError):e.restore_durable([dict(pairs[0],truthAt=at(66))],now)

 def test_archive_validation_rejects_other_contract_stale_predictions_and_future_times(self):
  import bob_validation_store as s
  p=dict(key=s.KEY,type='prediction',value=4200,at=at(-30),referenceAt=at(-120))
  self.assertEqual(s.event(p,NOW)[-1],'61–300s')
  for wrong in (dict(p,key='future:GC=F'),dict(p,value=True),dict(p,at=at(-91)),dict(p,at=at(1)),dict(p,referenceAt=at(-2000))):
   with self.assertRaises(ValueError):s.event(wrong,NOW)

 def test_overnight_archive_retains_errors_without_granting_stale_readiness(self):
  from bob_validation_store import KEY
  pairs=[dict(bucket='0–60s',predictionAt=at(60+i*30),prediction=102,referenceAt=at(15+i*30),
              predictionReceivedAt=at(61+i*30),truthAt=at(60+i*30),truth=100,truthReceivedAt=at(70+i*30)) for i in range(21)]
  morning=NOW+timedelta(days=6)
  e.restore_durable(pairs,morning)
  result=e.quality(KEY,45,morning)
  self.assertEqual(result['sampleCount'],21)
  self.assertFalse(result['ready'])
  expired=NOW+timedelta(days=7,hours=1)
  e.restore_durable(pairs,expired)
  self.assertEqual(e.quality(KEY,45,expired)['sampleCount'],0)

 def test_all_horizon_counts_visible_without_borrowing_readiness(self):
  for i in range(21):
   t=60+i*30;e.record('x',102,at(t),at(t-45),at(t));e.observe('x',100,at(t),at(t+10))
  q=e.quality('x',120,NOW+timedelta(seconds=700))
  self.assertFalse(q['ready']);self.assertEqual(q['sampleCount'],0)
  summary={s['horizonBucket']:s for s in q['horizonSummaries']}
  self.assertEqual(summary['0–60s']['sampleCount'],21)
  self.assertEqual(summary['0–60s']['meanAbsoluteError'],2)
  self.assertEqual(summary['61–300s']['sampleCount'],0)

 def test_restore_uses_time_after_network_receipt(self):
  import bob_validation_store as s
  import time
  pair=dict(bucket='0–60s',predictionAt=at(-20),prediction=102,referenceAt=at(-60),
            predictionReceivedAt=at(-10),truthAt=at(-20),truth=100,truthReceivedAt=at(10))
  with patch.object(s,'_queue',[]),patch.object(s,'_active_until',time.monotonic()+120),patch.object(s,'_status',''),patch.object(s,'request',return_value={'pairs':[pair]}),patch.object(s,'datetime') as clock,patch.object(s.threading.Event,'wait',side_effect=StopIteration):
   clock.now.side_effect=[NOW,NOW+timedelta(seconds=20)]
   with self.assertRaises(StopIteration):s._sync()
   self.assertIn('dauerhaft gesichert',s.status())
   self.assertEqual(e.quality(s.KEY,40,NOW+timedelta(seconds=20))['sampleCount'],1)

class ArchiveTransitTests(unittest.TestCase):
 def test_expiry_during_network_read_does_not_discard_newer_rows(self):
  from bob_validation_store import KEY
  def pair(offset):
   return dict(bucket='0–60s',predictionAt=at(offset),prediction=102,referenceAt=at(offset-45),predictionReceivedAt=at(offset),truthAt=at(offset),truth=100,truthReceivedAt=at(offset+10))
  with patch.object(e,'_errors',{}),patch.object(e,'_seen',{}),patch.object(e,'_pending',{}):
   e.restore_durable([pair(-604811),pair(-20)],NOW)
   self.assertEqual(e.quality(KEY,45,NOW)['sampleCount'],1)
