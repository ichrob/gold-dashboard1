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
                                      'episodesSampled':0,'variants':{str(i):{}
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
        self.assertEqual(result['intraday']['variantsObserved'],48)
        self.assertFalse(result['strategyWinnerConfirmed'])
        self.assertFalse(result['fullOriginalHistoryVerified'])
        self.assertNotIn('SENSITIVE_TOKEN',json.dumps(result))
        self.assertLess(len(json.dumps(result).encode()),2300)

    def test_unrelated_old_synthetic_report_does_not_gain_size_overhead(self):
        self.assertIsNone(diag.new_studies_brief({'accounts':[{'cash':100}]}))

    def test_invalid_or_missing_study_reports_not_healthy(self):
        result=diag.new_studies_brief({'qualityCampaign':{'status':'unavailable'}})
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['quality']['status'],'unavailable')
        self.assertIsNone(result['intraday']['variantsObserved'])


if __name__ == '__main__':
    unittest.main()
