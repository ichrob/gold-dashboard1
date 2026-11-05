"""Audit read capacity exhaustion must be retryable without fabricated results."""
import unittest
from unittest.mock import MagicMock, patch

import push_server as server


class AuditReadTimeoutHttpTests(unittest.TestCase):
    def handler(self, path):
        h=object.__new__(server.Handler)
        h.path=path
        h.headers={'X-Bob-Push-Token':'unit-test'}
        return h

    def test_audit_read_admission_timeout_is_explicit_incomplete_503(self):
        h=self.handler('/decision-audit/read')
        sent=[]
        with patch.object(server,'PUSH_SERVICE_TOKEN','unit-test'), \
             patch.object(server,'json_body',return_value={'mode':'review'}), \
             patch.object(server,'read_audit_report',
                          side_effect=TimeoutError('private-data-must-not-leak')) as read, \
             patch.object(server,'send_json',
                          side_effect=lambda _,status,data:sent.append((status,data))), \
             patch('builtins.print') as logs:
            h.do_POST()
        read.assert_called_once_with({'mode':'review'})
        self.assertEqual(len(sent),1)
        code,result=sent[0]
        self.assertEqual(code,503)
        self.assertTrue(result['retryable'])
        self.assertFalse(result['dataComplete'])
        self.assertNotIn('private-data-must-not-leak',str(sent))
        self.assertNotIn('private-data-must-not-leak',str(logs.call_args_list))
        self.assertFalse(any('items' in data for _,data in sent))

    def test_audit_write_timeout_is_not_marked_safe_to_auto_retry(self):
        h=self.handler('/decision-audit/write')
        sent=[]
        conn=MagicMock()
        conn.__enter__.return_value=conn
        with patch.object(server,'PUSH_SERVICE_TOKEN','unit-test'), \
             patch.object(server,'json_body',return_value={'direction':'LONG'}), \
             patch.object(server,'db',return_value=conn), \
             patch.object(server.decision_audit,'handle',
                          side_effect=TimeoutError('original state unknown')), \
             patch.object(server,'send_json',
                          side_effect=lambda _,status,data:sent.append((status,data))), \
             patch('builtins.print'):
            h.do_POST()
        self.assertEqual(sent[0][0],500)
        self.assertNotIn('retryable',sent[0][1])
        self.assertNotIn('original state unknown',str(sent))

    def test_shared_report_timeout_is_typed_as_retryable_read_only_failure(self):
        with patch.object(server.report_admission, 'read',
                          side_effect=TimeoutError('private pool state')):
            with self.assertRaises(server.ReadReportUnavailable):
                server.read_db_report('fixture', lambda conn: {'ok': True})

    def test_get_report_timeout_is_explicit_incomplete_503(self):
        h=self.handler('/product-audit')
        sent=[]
        with patch.object(server,'PUSH_SERVICE_TOKEN','unit-test'), \
             patch.object(server,'read_db_report',
                          side_effect=server.ReadReportUnavailable()), \
             patch.object(server,'send_json',
                          side_effect=lambda _,status,data:sent.append((status,data))), \
             patch('builtins.print') as logs:
            h.do_GET()
        self.assertEqual(sent,[(503,{
            'error':'Lesebericht vorübergehend belegt',
            'retryable':True,'dataComplete':False})])
        self.assertIn('BOB_PUSH database_busy path=/product-audit '
                      'error=ReadReportUnavailable',str(logs.call_args_list))

    def test_post_read_report_timeout_is_explicit_incomplete_503(self):
        h=self.handler('/list-correction')
        sent=[]
        with patch.object(server,'PUSH_SERVICE_TOKEN','unit-test'), \
             patch.object(server,'json_body',return_value={'action':'read'}), \
             patch.object(server,'read_db_report',
                          side_effect=server.ReadReportUnavailable()), \
             patch.object(server,'send_json',
                          side_effect=lambda _,status,data:sent.append((status,data))), \
             patch('builtins.print'):
            h.do_POST()
        self.assertEqual(sent,[(503,{
            'error':'Lesebericht vorübergehend belegt',
            'retryable':True,'dataComplete':False})])
