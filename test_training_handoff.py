import unittest,json
from unittest.mock import MagicMock,patch
import training_handoff as h
import bob_assistance as a
import bob_repair_store as store

class HandoffTest(unittest.TestCase):
 def test_only_technical_allowlisted_summary(self):
  conn=MagicMock()
  conn.execute.return_value.fetchall.side_effect=[ [('signal','escalated',300,1,3)], [('title','DE000PRIVATE0',12),('signal','invalidStart',288)], [('signal','invalidStart','escalated',300,1,3)] ]
  conn.execute.return_value.fetchone.return_value=(123456,)
  result=h.summary(conn)
  self.assertNotIn('DE000PRIVATE0',json.dumps(result))
  self.assertEqual(result['groups'][0]['cases'],300)
  self.assertIn({'kind':'signal','reason':'invalidStart','cases':288},result['reasons'])
  h._last_signature=None
  with patch('builtins.print') as log:
   self.assertTrue(h.publish(result,1000));result['problemGroups'][0]['cases']+=15;self.assertFalse(h.publish(result,1001));self.assertTrue(h.publish(result,1600))
   self.assertEqual(log.call_count,2)
   self.assertTrue(log.call_args.args[0].startswith('BOB_TRAINING_HELP '))
 def test_browser_failure_routes_are_accepted_without_private_text(self):
  with patch.object(a.bob_repair_store,'queue_event'):
   for key in ('audit','repairs','portfolios','improve'):
    code='training-'+key+'-unavailable'
    self.assertIn(code,store.EVENT_CODES)
    self.assertEqual(a.report({'code':code})['status'],'queued')
   with self.assertRaises(ValueError):a.report({'code':'training-audit-unavailable','report':'private'})
