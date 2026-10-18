import copy
import unittest
from unittest.mock import Mock,patch
import decision_audit as audit
import improvement_status as status
from test_improvement_tracker import at

class SignalStatusTests(unittest.TestCase):
    def test_bad_start_never_begins_background_trial_but_coverage_is_recorded(self):
        import push_server
        now=at();market=dict(analysisBarAt=now-300000,priceFresh=True,price=4000,dataAt=now)
        for changed in ({'priceFresh':False},{'dataAt':now-60001},{'dataAt':now+1},{'price':None}):
            conn=Mock();conn.transaction.return_value.__enter__=Mock();conn.transaction.return_value.__exit__=Mock()
            with patch('push_server.time.time',return_value=now/1000),patch('metric_quality.capture') as coverage,patch.object(audit,'write') as write:
                self.assertFalse(push_server.record_market_observation(conn,{**market,**changed},{}))
                coverage.assert_called_once();write.assert_not_called()

    def test_recent_lane_runs_before_archive_without_rewriting_results(self):
        calls=[]
        with patch.object(audit,'_harvest_at',0),patch.object(audit.time,'time',return_value=100),patch.object(audit,'_harvest_recent',side_effect=lambda c,h:calls.append(('new',h))),patch.object(audit,'_harvest_horizon',side_effect=lambda c,h:calls.append(('old',h))):
            audit.harvest(Mock())
        self.assertEqual([x[0] for x in calls],['new']*6+['old']*6)
        conn=Mock();conn.execute.return_value.fetchall.return_value=[('new-id',)]
        audit._harvest_recent(conn,15)
        query,params=conn.execute.call_args_list[0].args
        self.assertIn('LIMIT 128',query);self.assertIn("payload->>'marketEvaluable'='true'",query)
        insert=conn.execute.call_args_list[1].args[0]
        self.assertIn('ON CONFLICT DO NOTHING',insert)
        self.assertIn("stream='gold-api-xau-usd-v1'",insert)

    def test_pending_is_not_missing_and_error_types_are_not_cases(self):
        now=at(19,11);r=dict(recordedAt=now-20*60000,marketEvaluable=True,price=4000,direction='LONG')
        report=dict(repairQuality=dict(status='ok',testProblemTypes=2,testCases=5209))
        result=status.summarize(report,dict(state='ok',accountsChecked=5,accountsTotal=5),[(r,{15:dict(at=r['recordedAt']+900000,price=4010)})],now)
        self.assertEqual(result['counts'],dict(evaluated=1,pending=2,invalidStart=0,missingFollowup=0))
        self.assertEqual(result['openErrorTypes'],2);self.assertEqual(result['affectedCases'],5209)
        self.assertEqual(result['cards'][1]['state'],'ok')
        self.assertEqual(result['cards'][0]['state'],'waiting')
        self.assertEqual(result['cards'][3]['state'],'waiting')
        missing=status.summarize(report,{},[(r,{})],now)
        self.assertEqual(missing['counts']['missingFollowup'],1)
        self.assertEqual(missing['cards'][1]['state'],'open')

    def test_weekend_no_data_and_partial_products_never_show_live_success(self):
        now=at(18,22)
        r=status.summarize({},dict(state='paused'),[],now)
        self.assertEqual(r['cards'][0]['state'],'paused');self.assertEqual(r['cards'][1]['state'],'waiting')
        self.assertIsNone(r['openErrorTypes'])
        now=at(19,11)
        report=dict(reliability=dict(lastAt=now),dataQuality=dict(status='ok',total=2,freshPct=100,completePct=50))
        self.assertEqual(status.summarize(report,{},[],now)['cards'][0]['state'],'waiting')
        report['dataQuality']['completePct']=100
        self.assertEqual(status.summarize(report,{},[],now)['cards'][0]['state'],'ok')
