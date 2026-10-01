import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import estimate_quality as e

NOW=datetime(2026,10,1,12,tzinfo=timezone.utc)
def at(s):return (NOW+timedelta(seconds=s)).isoformat()

class QualityTests(unittest.TestCase):
 def setUp(self):
  for name in ('_pending','_errors','_seen'):
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
  e.observe('x',100,at(60),at(110));self.assertEqual(e.quality('x',60,NOW+timedelta(seconds=120))['sampleCount'],1)

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
