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
