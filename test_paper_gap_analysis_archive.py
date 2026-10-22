"""Read-only, bounded comparison of shared paper gaps and prior 15m analysis logs."""
import json
import unittest
from decimal import Decimal
from unittest.mock import Mock
import bob_diagnostics as diag
import paper_gap_analysis_archive as archive


class _Transaction:
    def __enter__(self): return self
    def __exit__(self,*args): return False


def _cases(at):
    return [{'profile':'balanced','recentCases':{'status':'observed','items':[
        {'status':'inconclusive','events':[
            {'kind':'data-gap','recordedAt':at,'reason':'Do not show any raw reason'}]}]}}]


class PaperAnalysisArchiveTests(unittest.TestCase):
    def test_nearby_fresh_analysis_is_observation_not_execution(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Transaction()
        conn.execute.return_value.fetchone.return_value=(Decimal('1002.5'),'true','true','998000')
        out=archive.report(conn,_cases(at),now_ms=at+200000)
        entry=out['items'][0]
        self.assertEqual(out['counts']['nearby15mAnalysis'],1)
        self.assertEqual(out['counts']['readyFresh15mAnalysis'],1)
        self.assertEqual(entry['timeRelation'],'after-event')
        self.assertEqual(entry['deltaSeconds'],2.5)
        self.assertAlmostEqual(entry['sourceAgeAtAnalysisSeconds'],4.5)
        self.assertFalse(out['realOrders'])
        self.assertIn('another worker',out['note'])
        self.assertEqual(conn.execute.call_count,1)
        sql=conn.execute.call_args.args[0].upper()
        self.assertTrue(sql.lstrip().startswith('SELECT'))
        self.assertNotIn('INSERT ',sql)
        self.assertNotIn('UPDATE ',sql)
        self.assertNotIn('DELETE ',sql)
        self.assertNotIn('Do not show any raw reason',json.dumps(out))

    def test_unready_analysis_and_no_match_cannot_validate_exit(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Transaction()
        conn.execute.return_value.fetchone.return_value=(1000.,'false','false',None)
        out=archive.report(conn,_cases(at),now_ms=at+200000)
        self.assertEqual(out['counts']['readyFresh15mAnalysis'],0)
        self.assertEqual(out['items'][0]['ready'],False)
        self.assertIsNone(out['items'][0]['sourceAgeAtAnalysisSeconds'])
        conn.execute.return_value.fetchone.return_value=None
        out=archive.report(conn,_cases(at),now_ms=at+200000)
        self.assertEqual(out['counts']['no15mAnalysisInWindow'],1)

    def test_absent_history_and_exception_are_not_success(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Transaction()
        conn.execute.side_effect=RuntimeError('sensitive exception')
        out=archive.report(conn,_cases(at),now_ms=at+200000)
        self.assertEqual(out['status'],'partial')
        self.assertEqual(out['counts']['queryUnavailable'],1)
        self.assertNotIn('sensitive exception',json.dumps(out))
        conn.execute.reset_mock()
        out=archive.report(conn,_cases(at),now_ms=at+archive.RETENTION_MS+1)
        self.assertEqual(out['counts']['outsideRetention'],1)
        conn.execute.assert_not_called()

    def test_repeated_account_clock_is_one_bounded_query(self):
        at=1000000
        conn=Mock()
        conn.transaction.return_value=_Transaction()
        conn.execute.return_value.fetchone.return_value=(999.,'true','true','NaN')
        accounts=_cases(at)+[{**_cases(at)[0],'profile':'offensive'}]
        out=archive.report(conn,accounts,now_ms=at+200000)
        self.assertEqual(out['sampledDistinctClocks'],1)
        self.assertEqual(conn.execute.call_count,1)
        self.assertIsNone(out['items'][0]['sourceAgeAtAnalysisSeconds'])

    def test_projection_only_allowlisted_fields(self):
        sample={'status':'observed','accounts':_cases(1000000),
            'analysisGapArchive':{'status':'observed','readOnly':True,
                'secret':'do-not-copy','counts':{'nearby15mAnalysis':1,
                                                'secret':'do-not-copy'},
                'items':[{'eventAt':1000000,'state':'nearby-15m-analysis-observed',
                          'analysisAt':1002000,'ready':True,'priceFresh':True,
                          'secret':'do-not-copy'}]}}
        result=diag.simulation_evidence_snapshot(sample)
        self.assertEqual(result['analysisGapArchive']['counts']['nearby15mAnalysis'],1)
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('do-not-copy',json.dumps(result))


if __name__=='__main__':
    unittest.main()
