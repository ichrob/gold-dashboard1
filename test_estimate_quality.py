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
