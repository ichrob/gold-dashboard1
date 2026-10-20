import json
import unittest
from unittest.mock import Mock, patch
import bob_diagnostics as diagnostics
import bob_mcp
import research_readout as readout


class ResearchReadoutTests(unittest.TestCase):
    def test_saved_metrics_and_original_clocks_survive_without_private_fields(self):
        report=dict(mode='RESEARCH_ONLY',status='evaluated',approved=False,
            credentials='excluded-secret',closedBars=1000,rangeMs=[1,1000],
            outOfSampleByStrategy={'baseline':{'trades':30,'meanFoldNetPct':-.5}},
            learningCycle={'status':'shadow','proposal':{'strategy':'breakout','frozenAtBar':900,
                'protocol':{'baseline':'baseline','costBpsPerSide':{'standard':8,'stress':24}}},
                'prospective':{'sessions':2,'costScenarios':{'standard':{'candidate':{'index':1.01}}}}})
        conn=Mock();conn.execute.return_value.fetchall.return_value=[({'day':'2026-10-20',
            'calculatedAt':'original-clock','lastBarAt':1000,'report':report,'account':'excluded-account'},)]
        out=readout.read(conn);r=out['items'][0]
        self.assertEqual(r['calculatedAt'],'original-clock')
        self.assertEqual(r['report']['outOfSampleByStrategy']['baseline']['meanFoldNetPct'],-.5)
        self.assertEqual(r['report']['learningCycle']['proposal']['frozenAtBar'],900)
        self.assertNotIn('excluded',json.dumps(out))
        sql=conn.execute.call_args.args[0]
        self.assertTrue(sql.startswith('SELECT'));self.assertIn('LIMIT 1',sql)
        self.assertEqual(conn.execute.call_count,1)

    def test_empty_archive_is_explicit(self):
        c=Mock();c.execute.return_value.fetchall.return_value=[]
        self.assertEqual(readout.read(c)['status'],'empty')

    def test_report_survives_dropping_large_details_and_history(self):
        stored={'status':'observed','items':[{'day':'2026-10-20','report':{'closedBars':1000}}]}
        original=diagnostics.collect({'simulationAndPush':lambda:{'status':'observed',
            'history':{'raw':'x'*20000},'details':{'raw':'x'*20000},'researchReports':stored}})
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_diagnostics'}}
        with patch.object(bob_mcp,'_MAX_RESULT_BYTES',3000):
            _,response=bob_mcp.handle(request,Mock(),lambda:original)
        self.assertFalse(response['result']['isError'])
        result=json.loads(response['result']['content'][0]['text'])
        self.assertEqual(result['areas']['simulationAndPush']['researchReports'],stored)
        self.assertEqual(result['areas']['simulationAndPush']['omittedSections'],['history','details'])
        self.assertIn('history',original['areas']['simulationAndPush'])

    def test_existing_diagnostics_scope_still_required(self):
        req={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_diagnostics'}}
        _,res=bob_mcp.handle(req,Mock())
        self.assertTrue(res['result']['isError'])
        self.assertIn('insufficient_scope',res['result']['_meta']['mcp/www_authenticate'][0])

    def test_existing_extended_reader_exposes_stored_report(self):
        portfolios=Mock(POLICIES=[]);conn=Mock()
        conn.execute.return_value.fetchone.return_value=(0,)
        health=Mock();health.snapshot.return_value={}
        details={'status':'observed','areas':{'learning':{'status':'observed','items':[]}}}
        with patch.object(diagnostics,'stored_details',return_value=details), \
             patch('diagnostic_history.report',return_value={}),patch('signal_history.report',return_value={'records':[]}):
            out=diagnostics.push_snapshot(conn,Mock(),health,portfolios,extended=True)
        self.assertEqual(out['researchReports'],details['areas']['learning'])


if __name__=='__main__':unittest.main()
