import unittest
import snaptrade_quality as quality


class QualityTests(unittest.TestCase):
    def test_evidence_classifies_missing_original_proof(self):
        acc={'journal':{
          'orders':{'rows':[{'key':'x','quantity':'2','executedAt':None,
                             'price':'9','symbol':'GOLD','currency':'EUR'},
                            {'key':'y','quantity':'0','price':'9'}]},
          'activities':{'rows':[{'type':'BUY','fee':None},
                                {'type':'SELL','fee':'0'}], 'code':'READ_OK',
                        'complete':False}},
          'tradeInsights':{'executions':[]},
          'tradeJournal':{'events':[{},{}], 'realized':[], 'unresolved':[{}]}}
        stats=quality.evidence_gaps(acc)
        self.assertEqual(stats['positiveFills'],1)
        self.assertEqual(stats['noPositiveFill'],1)
        self.assertEqual(stats['missingExecutionTime'],1)
        self.assertEqual(stats['missingVerifiedIsin'],1)
        self.assertEqual(stats['activityMissingFees'],1)
        p=quality.profit_review(acc)
        self.assertFalse(p['netProfitVerified'])
        self.assertFalse(p['accountHistoryComplete'])

    def test_monitor_is_deduplicated_and_not_a_push(self):
        data={'configured':True,'running':True,'code':'READ_OK',
              'fresh':False,'snapshot':{'accounts':[{
              'journal':{'orders':{'code':'READ_OK'},
                         'activities':{'code':'READ_OK','complete':False}}}]}}
        result=quality.connection_watch(data)
        self.assertEqual(result['codes'],
            ['SOURCE_CLOCK_NOT_FRESH','ACTIVITY_HISTORY_PARTIAL'])
        self.assertEqual(result['pushesSent'],0)
        self.assertEqual(result['emailsSent'],0)
        self.assertEqual(len(result['codes']),len(set(result['codes'])))


if __name__=='__main__':
    unittest.main()
