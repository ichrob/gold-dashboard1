"""Separate active candle data-source selection from stale backups and paper uncertainty."""
import unittest
import bob_diagnostics as d

class GoldDataSourceTriageTests(unittest.TestCase):
    def test_alternate_source_is_identified_not_silently_marked_healthy(self):
        areas={
            'sourceReliability':{'sources':{'xaus/1m':{'state':'stale'},'biquote/5m':{'state':'stale'}}},
            'market':{'candles':{
                '1m':{'integrity':{'state':'ok','source':'biquote · XAU/USD Broker/MT5'}},
                '5m':{'integrity':{'state':'ok','source':'biquote · XAU/USD Broker/MT5'}}}},
            'simulationAndPush':{'accounts':[{'recentCases':{'items':[{'status':'inconclusive'}]}}]},
        }
        output=d.summary(areas)
        rows={x['area']:x for x in output['attention']}
        self.assertEqual(rows['sourceReliability.sources.xaus/1m']['sourceRole'],'alternate')
        self.assertEqual(rows['sourceReliability.sources.biquote/5m']['sourceRole'],'selected')
        paper=[x for x in output['attention'] if x['state']=='inconclusive']
        self.assertEqual(len(paper),1)
        self.assertEqual(paper[0]['meaning'],'paper-result-unconfirmed-not-a-realised-loss')
        self.assertEqual(output['assessment'],'needs-attention')
        self.assertIn('not realised losses',output['note'])
    def test_unknown_source_never_asserts_current(self):
        areas={'sourceReliability':{'sources':{'xaus/1m':{'state':'stale'}}}}
        rows=d.summary(areas)['attention']
        self.assertEqual(rows[0]['sourceRole'],'undetermined')

if __name__=='__main__':
    unittest.main()
