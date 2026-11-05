import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import termux_maintenance as t
import bob_termux_runner as runner

NOW=10000
SID='b'*32
RID='c'*32

def state():
    return t.exchange({},dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=None),NOW)[0]

def job(script='printf ok'):
    return dict(deviceId='a'*12,sessionId=SID,requestId=RID,script=script)

class Policy(unittest.TestCase):
    def test_duplicate_cannot_execute_twice_and_changed_script_rejected(self):
        s=state();t.enqueue(s,job(),NOW)
        s,response=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=None),NOW+1)
        self.assertEqual(response['command']['requestId'],RID)
        self.assertEqual(t.enqueue(s,job(),NOW+2)['status'],'delivered')
        s,response=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=None),NOW+2)
        self.assertIsNone(response['command'])
        with self.assertRaises(ValueError):t.enqueue(s,job('different'),NOW+2)
        self.assertNotIn('script',t.public_job(s['jobs'][0]))
    def test_stopped_expired_wrong_session_and_busy_fail_closed(self):
        s=state();self.assertEqual(t.enqueue(s,{**job(),'sessionId':'d'*32},NOW)['status'],'session-missing')
        self.assertEqual(t.enqueue(s,job(),NOW+31)['status'],'session-offline')
        t.enqueue(s,job(),NOW)
        self.assertEqual(t.enqueue(s,{**job(),'requestId':'d'*32},NOW)['status'],'busy')
        s,reply=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=False,result=None),NOW+1)
        self.assertIsNone(reply['command']);self.assertEqual(s['jobs'][0]['status'],'expired')
        self.assertEqual(t.enqueue(s,{**job(),'requestId':'e'*32},NOW+1)['status'],'session-offline')
    def test_stopped_session_cannot_reopen_from_delayed_heartbeat(self):
        s=state()
        s,_=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=False,result=None),NOW+1)
        s,_=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=None),NOW+2)
        self.assertFalse(s['active'])

    def test_deadline_cannot_be_extended(self):
        s=state();s,_=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1810,active=True,result=None),NOW+10)
        self.assertEqual(s['expiresAt'],NOW+1800)
    def test_results_need_delivered_job_and_size_bound(self):
        s=state();t.enqueue(s,job(),NOW)
        result=dict(requestId=RID,status='completed',output='ok',exitCode=0)
        s,_=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=result),NOW+1)
        self.assertEqual(s['jobs'][0]['status'],'delivered')
        s,_=t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=result),NOW+2)
        self.assertEqual(s['jobs'][0]['status'],'completed')
        self.assertNotIn('script',s['jobs'][0])
        bad={**result,'output':'x'*8193}
        with self.assertRaises(ValueError):t.exchange(s,dict(sessionId=SID,expiresAt=NOW+1800,active=True,result=bad),NOW+3)
    def test_no_phone_scope_upgrade(self):
        import bob_mcp
        request=dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='bob_termux_execute',arguments=job()))
        _,reply=bob_mcp.handle(request,lambda:{},remote_termux=True,remote_phone=True,phone_handler=lambda *_:self.fail('phone scope upgraded'))
        self.assertIn(t.SCOPE,json.dumps(reply))
        calls=[]
        _,reply=bob_mcp.handle(request,lambda:{},remote_termux=True,termux_handler=lambda n,a:calls.append(a) or {'status':'queued'})
        self.assertEqual(calls,[job()])
        self.assertFalse(reply['result']['isError'])
    def test_schema_and_unknown_arguments(self):
        self.assertEqual(t.arguments(t.TOOLS[1],job()),job())
        for extra in ({'password':'x'},{'timeout':999}):
            with self.assertRaises(ValueError):t.arguments(t.TOOLS[1],{**job(),**extra})
        import bob_oauth_store as oauth
        self.assertTrue(oauth.valid_scope(t.SCOPE))
        self.assertNotEqual(oauth.PHONE_SCOPE,t.SCOPE)
        tools=__import__('bob_mcp').tool_definitions(remote_termux=True)
        self.assertEqual(next(x for x in tools if x['name']==t.TOOLS[1])['securitySchemes'][0]['scopes'],[t.SCOPE])
    def test_signed_asset_matches(self):
        self.assertEqual(Path('bob_termux_runner.py').read_bytes(),Path('android_companion/app/src/main/assets/bob_termux_runner.py').read_bytes())

class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'HOME':self.tmp.name,'PREFIX':'/usr','BOB_TEST_PRIVATE_SECRET':'do-not-inherit'})
        self.env.start();self.addCleanup(self.env.stop)
    def test_output_exit_workdir_and_no_inherited_secret(self):
        result=runner.execute('printf "%s" "${BOB_TEST_PRIVATE_SECRET-unset}"; pwd; exit 7')
        self.assertEqual(result['status'],'completed');self.assertEqual(result['exitCode'],7)
        self.assertIn('unset',result['output']);self.assertIn('/bob-work',result['output'])
    def test_timeout_output_limit_and_no_stdin(self):
        self.assertEqual(runner.execute('sleep 5',timeout=.05)['status'],'timeout')
        r=runner.execute('yes x',output_limit=100)
        self.assertEqual(r['status'],'output-limit');self.assertLessEqual(len(r['output'].encode()),100)
        self.assertNotEqual(runner.execute('read secret')['exitCode'],0)
    def test_background_pipe_does_not_block_return_forever(self):
        self.assertEqual(runner.execute('sleep 5 & wait',timeout=.05)['status'],'timeout')

if __name__=='__main__':unittest.main()
