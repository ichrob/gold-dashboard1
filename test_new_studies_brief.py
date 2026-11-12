"""Synthetic regression for size-limited current research diagnostics.

No live network, database, trading or historical outcome claims.
"""
import copy
import json
import unittest

import bob_diagnostics as diag


class NewStudiesBriefTests(unittest.TestCase):
    def test_compact_new_studies_are_not_mistaken_for_profitable_results(self):
        paper={
            'qualityCampaign':{'status':'collecting','checkedAt':9000,
              'studies':[{'id':'reaction','cycles':50,'original':45,'workerErrors':0},
                         {'id':'entry-delay','started':4,'complete':1,'inconclusive':1,'open':2},
                         {'id':'sideways-filter','started':2,'complete':0},
                         {'id':'warning-confirmed','started':3,'complete':1}],
              'modeledSimulation':{'status':'collecting','checkedAt':9000},
              'private':'SENSITIVE_TOKEN'},
            'shadowStudies':{'status':'observed',
              'studies':[{'study':'regime-routing','status':'retired','checkedAt':8000,
                          'casesStarted':8,'raw':'SENSITIVE_TOKEN'},
                         {'study':'wait-vs-enter','status':'retired','casesStarted':10},
                         {'study':'product-e2e','status':'retired','openCases':0}],
              'entryExitComparison':{'status':'waiting-for-first-episode',
                                      'episodesSampled':0,'checkedAt':5000,
                                      'inputObservation':{'checkedAt':9020,
                                        'reason':'waiting-for-direction',
                                        'inputQuality':{'verified':True,
                                            'token':'SENSITIVE_TOKEN'}},
                                      'variants':{str(i):{}
                                        for i in range(18)},
                                      'raw':'SENSITIVE_TOKEN'}},
            'intradayTimingStudy':{'status':'collecting','checkedAt':9010,
                                  'variants':[{'name':'a'}]*48,
                                  'secret':'SENSITIVE_TOKEN'},
        }
        before=copy.deepcopy(paper)
        result=diag.new_studies_brief(paper)
        self.assertEqual(paper,before)
        self.assertEqual(result['quality']['status'],'collecting')
        self.assertEqual(result['quality']['studies'][1]['started'],4)
        self.assertEqual(result['quality']['modeled']['status'],'collecting')
        self.assertEqual(result['shadow']['studies'][0]['status'],'retired')
        self.assertEqual(result['entryExit']['variantsObserved'],18)
        self.assertEqual(result['entryExit']['checkedAt'],5000)
        self.assertEqual(result['entryExit']['workerInputCheckedAt'],9020)
        self.assertEqual(result['entryExit']['workerInputReason'],'waiting-for-direction')
        self.assertTrue(result['entryExit']['workerInputVerified'])
        self.assertEqual(result['intraday']['variantsObserved'],48)
        self.assertFalse(result['strategyWinnerConfirmed'])
        self.assertFalse(result['fullOriginalHistoryVerified'])
        self.assertNotIn('SENSITIVE_TOKEN',json.dumps(result))
        self.assertLess(len(json.dumps(result).encode()),2300)

    def test_estimated_study_results_remain_distinct_and_invalid_inputs_warn(self):
        paper={
            'paper':{'sessionMode':'trading'},
            'qualityCampaign':{
              'status':'collecting','checkedAt':900000,
              'studies':[{'id':'reaction','cycles':1000,'original':969,
                          'invalid':31,'workerErrors':0},
                         {'id':'warning-confirmed','started':20,'complete':4,
                          'inconclusive':15,'open':1},
                         {'id':'entry-delay','started':20,'complete':5,
                          'inconclusive':15,'open':0},
                         {'id':'sideways-filter','started':4,'complete':1,
                          'inconclusive':3,'open':0}],
              'modeledSimulation':{
                'status':'collecting','checkedAt':900000,
                'studies':[{'id':'reaction','cycles':1000,'original':969,
                            'invalid':4,'estimated':27,'workerErrors':0},
                           {'id':'warning-confirmed','started':20,'complete':13,
                            'inconclusive':6,'open':1,'estimatedComplete':8},
                           {'id':'entry-delay','started':20,'complete':14,
                            'inconclusive':6,'open':0,'estimatedComplete':9}]}},
            'shadowStudies':{
              'status':'observed',
              'studies':[{'study':'product-e2e','status':'retired'}],
              'entryExitComparison':{
                  'status':'collecting',
                  'inputObservation':{'checkedAt':900000,
                                      'reason':'waiting-for-direction',
                                      'inputQuality':{'verified':True}},
                  'variants':{}}},
            'intradayTimingStudy':{
                'status':'collecting','checkedAt':900000,'variants':[]},
        }
        original=copy.deepcopy(paper)
        report=diag.new_studies_brief(paper,now_ms=920000)
        self.assertEqual(paper,original)
        m=report['quality']['modeled']['studies']
        self.assertEqual(m[0]['estimated'],27)
        self.assertEqual(m[1]['estimatedComplete'],8)
        self.assertEqual(report['quality']['studies'][1]['complete'],4)
        self.assertEqual(report['attentionStatus'],'needs-attention')
        codes=[x['code'] for x in report['attention']]
        self.assertIn('STUDY_ORIGINAL_INPUT_GAPS',codes)
        self.assertIn('STUDY_OUTCOMES_INCONCLUSIVE',codes)
        self.assertNotIn('STUDY_WORKER_OBSERVATION_STALE',codes)
        self.assertNotIn('STUDY_MODEL_FALLBACK_NOT_RUNNING',codes)
        self.assertFalse(report['strategyWinnerConfirmed'])
        self.assertFalse(report['fullOriginalHistoryVerified'])

    def test_closed_history_is_not_a_current_repair_alert_but_new_cases_are(self):
        paper={'qualityCampaign':{'studies':[{'id':'entry-delay','complete':3,'inconclusive':12}],
            'historicalReview':{'status':'observed','counts':{'reviewed':12,'modeled':7,'unavailable':5},
                                'byStudy':{'entry-delay':12},'truncated':False}}}
        out=diag.new_studies_brief(paper)
        self.assertNotIn('STUDY_OUTCOMES_INCONCLUSIVE',[x['code'] for x in out['attention']])
        self.assertEqual(out['quality']['studies'][0]['inconclusive'],12)
        self.assertEqual(out['quality']['historicalReview']['counts']['modeled'],7)
        paper['qualityCampaign']['studies'][0]['inconclusive']=13
        out=diag.new_studies_brief(paper)
        self.assertIn('STUDY_OUTCOMES_INCONCLUSIVE',[x['code'] for x in out['attention']])

    def test_worker_stale_only_in_trading_and_valid_wait_is_not_an_error(self):
        paper={
            'paper':{'sessionMode':'trading'},
            'qualityCampaign':{'status':'collecting','checkedAt':700000,
               'studies':[{'id':'reaction','cycles':110,'original':109,
                           'invalid':1}],
               'modeledSimulation':{'status':'collecting','checkedAt':900000}},
            'shadowStudies':{'status':'observed',
              'entryExitComparison':{'status':'collecting',
                'inputObservation':{'checkedAt':900000,
                                    'reason':'waiting-for-direction',
                                    'inputQuality':{'verified':True}}}},
            'intradayTimingStudy':{'status':'collecting','checkedAt':900000},
        }
        report=diag.new_studies_brief(paper,now_ms=910000)
        self.assertEqual([x['study'] for x in report['attention']],['quality'])
        paper['paper']['sessionMode']='night'
        report=diag.new_studies_brief(paper,now_ms=910000)
        self.assertEqual(report['attention'],[])
        self.assertEqual(report['attentionStatus'],'no-current-study-alert')

    def test_failed_modeled_branch_is_highlighted_without_fake_recovery(self):
        report=diag.new_studies_brief({
            'qualityCampaign':{'status':'collecting','studies':[
                {'id':'reaction','cycles':300,'original':300,'invalid':0}],
                'modeledSimulation':{'status':'unavailable'}},
            'shadowStudies':{'status':'observed',
                'entryExitComparison':{'status':'collecting'}},
            'intradayTimingStudy':{'status':'collecting'}},now_ms=900000)
        self.assertEqual(report['quality']['modeled']['status'],'unavailable')
        self.assertIn('STUDY_MODEL_FALLBACK_NOT_RUNNING',
                      [x['code'] for x in report['attention']])
        self.assertFalse(report['fullOriginalHistoryVerified'])

    def test_unrelated_old_synthetic_report_does_not_gain_size_overhead(self):
        self.assertIsNone(diag.new_studies_brief({'accounts':[{'cash':100}]}))

    def test_invalid_or_missing_study_reports_not_healthy(self):
        result=diag.new_studies_brief({'qualityCampaign':{'status':'unavailable'}})
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['quality']['status'],'unavailable')
        self.assertIsNone(result['intraday']['variantsObserved'])
        self.assertEqual(result['entryExit']['workerInputReason'],'unavailable')
        self.assertIsNone(result['entryExit']['workerInputCheckedAt'])


if __name__ == '__main__':
    unittest.main()
