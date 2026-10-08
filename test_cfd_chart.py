import unittest
from unittest.mock import patch
import investing_card as c
class ChartTest(unittest.TestCase):
 def test_source_times_grouped_without_filling_gaps(self):
  quotes=[{'at':'2026-10-08T12:00:05+00:00','price':4000},{'at':'2026-10-08T12:00:35+00:00','price':4002},{'at':'2026-10-08T12:03:05+00:00','price':3990}]
  with patch.object(c,'_chart_observations',quotes):
   r=c.chart_snapshot('1m')
  self.assertEqual(len(r['bars']),2)
  self.assertEqual(r['bars'][0]['openTime']%60000,0)
  self.assertEqual(r['bars'][0]['high'],4002)
  self.assertEqual(r['bars'][0]['open'],4000)
  self.assertEqual(r['sourceAt'],quotes[-1]['at'])
  self.assertEqual(r['bars'][0]['instrument'],'GOLD-CFD')
 def test_empty_history_does_not_fabricate_prices(self):
  with patch.object(c,'_chart_observations',[]):self.assertEqual(c.chart_snapshot('5m')['bars'],[])
