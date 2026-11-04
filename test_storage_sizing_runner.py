import contextlib
import io
import json
import os
import sys
import unittest
from unittest.mock import patch
import storage_sizing_runner as runner


class RunnerTests(unittest.TestCase):
    def run_child(self, code, timeout=5):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            status=runner.supervise([sys.executable,'-c',code],timeout)
        return status,json.loads(out.getvalue())

    def test_failure_keeps_exit_status_without_leaking_stderr(self):
        status,result=self.run_child("import sys; sys.stderr.write('secret'); sys.exit(7)")
        self.assertEqual(status,7)
        self.assertEqual(result['stderrBytes'],6)
        self.assertNotIn('secret',json.dumps(result))

    def test_signal_is_reported(self):
        status,result=self.run_child('import os,signal; os.kill(os.getpid(),signal.SIGTERM)')
        self.assertEqual(status,143)
        self.assertEqual(result['signal'],15)

    def test_timeout_terminates_child(self):
        status,result=self.run_child('import time; time.sleep(30)',0.05)
        self.assertEqual(status,124)
        self.assertTrue(result['timedOut'])

    @patch.dict(os.environ,{},clear=True)
    def test_default_refuses_execution(self):
        with self.assertRaises(RuntimeError): runner.require_dedicated_runtime()

    @patch.dict(os.environ,{'BOB_SIZING_DEDICATED_RUNTIME':'1'})
    @patch.object(runner,'Path')
    def test_serving_process_refused_despite_opt_in(self,path):
        process=path.return_value.iterdir.return_value=[unittest.mock.Mock()]
        process[0].name='123'
        process[0].__truediv__=unittest.mock.Mock(return_value=unittest.mock.Mock())
        (process[0]/'cmdline').read_bytes.return_value=b'python\0push_server.py\0'
        path.return_value.name='push_server.py'
        with self.assertRaises(RuntimeError): runner.require_dedicated_runtime()


if __name__=='__main__': unittest.main()
