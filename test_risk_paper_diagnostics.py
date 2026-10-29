import ast
import copy
import json
from pathlib import Path
import unittest
import bob_diagnostics as diag


class RiskPaperDiagnosticsTests(unittest.TestCase):
    def state(self):
        return {'version':'risk-paper-2000-v1', 'realOrders':False,
                'startedAt':1000, 'checkedAt':1000000,
                'accounts':{str(d):{'delaySeconds':d, 'cash':2000,
                    'equity':2000, 'reason':'Warte auf bestätigtes Risiko-Signal',
                    'position':None, 'pending':None, 'recent':[{'secret':'hidden'}]}
                    for d in (0,30,60)}}

    def test_fresh_waiting_accounts_and_redaction(self):
        raw=self.state()
        raw['accounts']['0']['position']={'private':'secret-position'}
        raw['accounts']['30']['pending']={'private':'secret-pending'}
        original=copy.deepcopy(raw)
        result=diag.risk_paper_snapshot(raw,1001000)
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['ageSeconds'],1)
        self.assertEqual(len(result['accounts']),3)
        self.assertTrue(result['accounts'][0]['positionOpen'])
        self.assertTrue(result['accounts'][1]['entryPending'])
        self.assertFalse(result['continuousExecutionVerified'])
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('recent',json.dumps(result))
        self.assertEqual(raw,original)

    def test_stale_is_not_running(self):
        result=diag.risk_paper_snapshot(self.state(),1120001)
        self.assertEqual(result['status'],'stale')
        focused=diag.focused_report({'areas':{'riskPaper':result}},'simulation')
        self.assertEqual(focused['status'],'partial')
        self.assertEqual(focused['areas']['riskPaper'],result)

    def test_entry_policy_and_signal_stage_are_visible_without_private_payloads(self):
        raw=self.state()
        raw.update(entryPolicy='risk-early-intraday-v2',entryPolicyStartedAt=999000,
                   signal={'ready':True,'direction':'SHORT','stage':'VORWARNUNG',
                           'at':1000000,'reason':'Kurzer Rücksetzer',
                           'private':{'token':'hidden'}})
        result=diag.risk_paper_snapshot(raw,1001000)
        self.assertEqual(result['entryPolicyStartedAt'],999000)
        self.assertEqual(result['entryPolicy'],'risk-early-intraday-v2')
        self.assertEqual(result['signal']['stage'],'VORWARNUNG')
        self.assertNotIn('hidden',json.dumps(result))

    def test_absent_invalid_and_future_clock(self):
        for at in (None,True,float('nan'),float('inf'),1000002,0):
            state=self.state();state['checkedAt']=at
            result=diag.risk_paper_snapshot(state,1000001)
            self.assertEqual(result['status'],'unavailable')
            self.assertIsNone(result['ageSeconds'])

    def test_missing_account_does_not_claim_complete(self):
        state=self.state();del state['accounts']['30']
        result=diag.risk_paper_snapshot(state,1000001)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['accounts'][1]['status'],'unavailable')

    def test_missing_and_foreign_payloads(self):
        for raw in (None,{}, {'status':'not-started'},
                    {'version':'risk-paper-2000-v1','realOrders':True}):
            self.assertEqual(diag.risk_paper_snapshot(raw)['status'],'unavailable')

    def test_failure_does_not_erase_other_simulations(self):
        def failed():
            raise RuntimeError('secret')
        report=diag.collect({'riskPaper':failed,
                             'simulationAndPush':lambda:{'status':'observed','paper':{'state':'ok'}}})
        focused=diag.focused_report(report,'simulation')
        self.assertEqual(focused['areas']['riskPaper']['status'],'unavailable')
        self.assertEqual(focused['areas']['simulationAndPush']['paper']['state'],'ok')
        self.assertNotIn('secret',json.dumps(focused))

    def test_actual_server_reader_is_wired_to_existing_read_route(self):
        tree=ast.parse(Path('server.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                and n.name=='read_diagnostics_for_mcp')
        collectors=[n for n in ast.walk(fn) if isinstance(n,ast.Dict)]
        reader=next(v for d in collectors for k,v in zip(d.keys,d.values)
                    if isinstance(k,ast.Constant) and k.value=='riskPaper')
        calls=[]
        class Projector:
            risk_paper_snapshot=staticmethod(lambda value:('projected',value))
        env={'bob_diagnostics':Projector,
             'read_private_report_for_mcp':lambda route:calls.append(route) or {'stored':True}}
        actual=eval(compile(ast.Expression(reader),'<reader>','eval'),env)()
        self.assertEqual(calls,['/risk-paper'])
        self.assertEqual(actual,('projected',{'stored':True}))


if __name__ == '__main__':
    unittest.main()

