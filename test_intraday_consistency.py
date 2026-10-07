"""Cross-runtime numerical boundaries and audit isolation for intraday v2."""
import unittest
import server
import backtest
import future_analysis
import decision_audit

class IntradayConsistency(unittest.TestCase):
    def test_minute_comparison_separate_and_first_observation(self):
        row={'direction':'LONG','barAt':1000,'recordedAt':1000,'price':100,'marketEvaluable':True,'minuteEntry':{'version':'minute-entry-v1','available':True,'direction':'NEUTRAL'}}
        truth={'price':101,'at':3601000}
        import copy
        late=copy.deepcopy(row);late['recordedAt']=2000;late['minuteEntry']['direction']='LONG'
        # An unavailable minute history is never counted as a filtered entry.
        missing=copy.deepcopy(row);missing['barAt']=2000;missing['minuteEntry']['available']=False
        r=decision_audit.entry_quality_review([(late,[None,{'price':101,'at':3602000}]),(row,[None,truth]),(missing,[None,truth])],field='minuteEntry',version='minute-entry-v1')
        self.assertEqual(r['evaluated'],1)
        self.assertEqual(r['filtered'],1)
        self.assertEqual(r['missedFavorable'],1)
        self.assertEqual(r['candidateMeanPct'],0)
        self.assertAlmostEqual(r['baselineMeanPct'],1)
        self.assertEqual(r['version'],'minute-entry-v1')

    def test_rsi_boundaries_across_engines(self):
        for engine in (server._rsi, backtest.rsi, future_analysis.rsi):
            self.assertEqual(engine([4200.0]*240), 50)
            self.assertEqual(engine([4200.0+i for i in range(240)]), 100)
            self.assertEqual(engine([4200.0-i for i in range(240)]), 0)

    def test_previous_rule_keeps_identity_and_does_not_enter_new_statistics(self):
        payload={'ruleVersion':'intraday-1h-15m-5m-v1','direction':'LONG','barAt':1000}
        _, old=decision_audit.normalize(payload, now=2000)
        self.assertEqual(old['ruleVersion'],payload['ruleVersion'])
        summary=decision_audit.summarize([(old,[None,None,None])])
        self.assertEqual(summary['legacyCount'],1)
        self.assertEqual(summary['metrics']['15']['missing'],0)

    def test_entry_quality_comparison_and_observed_adverse_excursion(self):
        row={'direction':'LONG','barAt':1000,'recordedAt':1000,'price':100,'marketEvaluable':True,'entryQuality':{'version':'entry-quality-v1','available':True,'direction':'NEUTRAL'}}
        truth={'at':3601000,'price':102,'minPrice':98,'maxPrice':103}
        result=decision_audit.entry_quality_review([(row,[None,truth,None]),(row,[None,truth,None])])
        self.assertEqual(result['evaluated'],1)
        self.assertEqual(result['missedFavorable'],1)
        self.assertAlmostEqual(result['baselineMeanPct'],2)
        self.assertEqual(result['candidateMeanPct'],0)
        self.assertEqual(result['meanObservedAdversePct'],2)
        self.assertEqual(result['candidateMeanObservedAdversePct'],0)
        row['direction']='SHORT';row['entryQuality']['direction']='SHORT'
        result=decision_audit.entry_quality_review([(row,[None,truth,None])])
        self.assertEqual(result['kept'],1)
        self.assertEqual(result['meanObservedAdversePct'],3)

    def test_entry_snapshot_refresh_is_idempotent(self):
        row={'direction':'LONG','barAt':1000,'ruleVersion':decision_audit.RULE_VERSION,'entryQuality':{'version':'entry-quality-v1','available':True,'direction':'LONG','signalAgeMinutes':5}}
        first,_=decision_audit.normalize(row,now=2000)
        row['entryQuality']['signalAgeMinutes']=6
        second,_=decision_audit.normalize(row,now=3000)
        self.assertEqual(first,second)
