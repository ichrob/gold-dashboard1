import copy
import unittest
from unittest.mock import patch
import product_source_recovery as sources
import product_repair_learning as learning
import repair_supervision as supervision
import bob_issue_watchdog as watchdog

class ExtendedRecoveryTests(unittest.TestCase):
    def setUp(self):
        sources._FAILURES.clear();sources._SOURCE_FAILURES.clear();sources._SOURCE_PAUSES.clear()
        learning._PLANS.clear()
    def tearDown(self):
        self.setUp()

    def test_shared_failure_pauses_only_affected_adapter_and_resumes(self):
        events=[]
        def broken():raise RuntimeError('private upstream')
        for i in ('a','b','c'):
            sources.attempt('comdirect-fetch',i,broken,{},events,now=100)
        sources.attempt('comdirect-fetch','d',lambda:self.fail('shared outage'),{},events,now=110)
        self.assertEqual(events[-1]['scope'],'source')
        self.assertEqual(sources.health(110)['pausedStages'],['comdirect-fetch'])
        self.assertEqual(sources.attempt('swissquote-fetch','d',lambda:{'ok':True},{},events,now=110),{'ok':True})
        sources.attempt('comdirect-fetch','d',lambda:{}, {},events,now=221)
        self.assertFalse(sources.health(221)['pausedStages'])
        self.assertNotIn('private upstream',str(events))

    def test_bad_repair_rolls_back_all_mutations_without_redating(self):
        original={'isin':'a','bidAt':'old','metadata':{'ratio':1}}
        def bad(value,isin):
            value['isin']='b';value['bidAt']='new';value['metadata']['ratio']=99
            return value
        result=sources.enrich('comdirect-terms','a',bad,original,[])
        self.assertEqual(result,original)
        self.assertEqual(original['metadata']['ratio'],1)
        result['metadata']['ratio']=2
        self.assertEqual(original['metadata']['ratio'],1)

    def test_learning_penalizes_new_failure_once_and_keeps_other_success(self):
        prior={'repairLearning':{'sourceSuccesses':{'comdirect':3,'swissquote':2}}}
        item={'missing':['quote'],'sourceRecovery':[{'stage':'comdirect-fetch','state':'failed'}]}
        one=learning.update(item,prior,100)
        self.assertEqual(one['sourceSuccesses'],{'comdirect':2,'swissquote':2})
        two=learning.update(item,{'repairLearning':one},200)
        self.assertEqual(two['sourceSuccesses'],one['sourceSuccesses'])

    def test_repair_priority_preserves_overdue_fairness_and_active_positions(self):
        learning._PLANS={'broken':{'status':'repairing','incidents':{'quotes':{}}}}
        isins=['normal','broken','active','overdue']
        requested={'normal':70000,'broken':70000,'active':70000,'overdue':10000}
        self.assertEqual(learning.request_order(isins,['active'],requested,100000),['overdue','active','broken','normal'])

    def test_retained_video_resume_preserves_publication_and_scope(self):
        import gold_research
        good={'kind':'YouTube','channelId':gold_research.MCO_CHANNEL,'title':'Gold heute',
              'url':'https://www.youtube.com/watch?v=wjLMQ7QfMiM','publishedAt':'original','current':False}
        other=dict(good,channelId='other')
        def enrich(item):item.update(publishedAt='incorrect',transcriptAnalyzed=True)
        with patch('youtube_research.enrich',side_effect=enrich) as call:
            gold_research.resume_retained([good,other])
            self.assertEqual(call.call_count,1)
        self.assertEqual(good['publishedAt'],'original')
        self.assertFalse(good['current'])
        self.assertTrue(good['transcriptAnalyzed'])

    def test_monitor_requires_completed_cycle_and_external_watchdog_detects_stall(self):
        with patch.object(supervision,'_STARTED',0),patch.object(supervision,'_LAST',None):
            self.assertEqual(supervision.health(True,90)['state'],'starting')
            self.assertEqual(supervision.health(True,151)['state'],'stalled')
            supervision.completed(160)
            self.assertEqual(supervision.health(True,200)['state'],'ok')
            state=supervision.health(True,311)
            self.assertEqual(state['state'],'stalled')
            codes=watchdog.classify({'status':'ok','repairSupervision':state},{'status':'ok'},{'ok':True},market_open=False)
            self.assertIn('repair-watch-stalled',codes)
            self.assertEqual(supervision.health(False,200)['state'],'stopped')

if __name__=='__main__':unittest.main()
