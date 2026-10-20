import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import signal_history as h
import bob_mcp

class SignalHistoryTests(unittest.TestCase):
 def test_timezone_window_and_invalid_requests(self):
  args=h.arguments({'start':'2026-10-20T16:30:00+02:00','end':'2026-10-20T19:00:00+02:00'})
  self.assertEqual(args['start'],'2026-10-20T14:30:00+00:00')
  for bad in [None,[],{'offset':True},{'offset':5000},{'sql':'SELECT 1'},
              {'start':'2026-10-20T16:30:00'}, {'start':None},
              {'start':'2026-10-19T00:00:00Z','end':'2026-10-21T00:00:00Z'}]:
   with self.assertRaises((ValueError,TypeError)):h.arguments(bad)
 def rows(self,n):
  at=datetime(2026,10,20,14,tzinfo=timezone.utc)
  return [(str(i),at+timedelta(seconds=i),dict(direction='NEUTRAL' if i<50 else 'SHORT',
      origin='background',ruleVersion='v7',priceAt=123,barAt=100,price=4100,
      earlyImpulse={'direction':'SHORT','available':True,'secret':'excluded'},
      products=[{'private':'excluded'}],token='excluded')) for i in range(n)]
 def test_original_evidence_pagination_and_projection(self):
  conn=Mock();conn.execute.return_value.fetchall.return_value=self.rows(105)
  r=h.report(conn,{'offset':0});q=h.report(conn,{**r['window'],'offset':100})
  self.assertEqual(len(r['records']),100);self.assertEqual(r['nextOffset'],100)
  self.assertEqual(len(q['records']),5);self.assertIsNone(q['nextOffset'])
  self.assertEqual([x['id'] for x in r['transitions']],['0','50'])
  self.assertEqual(r['records'][0]['priceAt'],123)
  self.assertNotIn('excluded',json.dumps(r))
  self.assertIn('LIMIT 5001',conn.execute.call_args.args[0])
  self.assertTrue(conn.execute.call_args.args[0].startswith('SELECT'))
 def test_missing_and_scan_truncation(self):
  conn=Mock();conn.execute.return_value.fetchall.return_value=[]
  self.assertEqual(h.report(conn)['status'],'empty')
  conn.execute.return_value.fetchall.return_value=self.rows(5001)
  r=h.report(conn);self.assertTrue(r['scanTruncated']);self.assertIsNone(r['recordsInWindow'])
 def test_streams_and_versions_do_not_merge(self):
  rows=self.rows(4)
  rows[1][2]['origin']='browser';rows[2][2]['ruleVersion']='v6'
  conn=Mock();conn.execute.return_value.fetchall.return_value=rows
  self.assertEqual(len(h.report(conn)['transitions']),3)
 def test_mcp_scope_denial_and_validation_before_read(self):
  read=Mock(return_value={'status':'observed'})
  req={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_signal_history','arguments':{}}}
  _,result=bob_mcp.handle(req,Mock(),signal_history_reader=read)
  self.assertTrue(result['result']['isError']);read.assert_not_called()
  _,result=bob_mcp.handle(req,Mock(),diagnostics_reader=Mock(),signal_history_reader=read)
  self.assertFalse(result['result']['isError']);read.assert_called_once()
  req['params']['arguments']={'offset':-1}
  _,result=bob_mcp.handle(req,Mock(),diagnostics_reader=Mock(),signal_history_reader=read)
  self.assertIn('error',result);self.assertEqual(read.call_count,1)

if __name__=='__main__':unittest.main()
