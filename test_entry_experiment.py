import copy
import unittest
import decision_audit as audit
import entry_experiment as trial
import test_market_optimization as fixtures


class Tests(unittest.TestCase):
    def row(self, direction='LONG'):
        r, truths = fixtures.Tests().row(direction)
        r['entryQuality'].update(baselineDirection=direction, deviationAtr=1.3,
                                 roomR=2, signalAgeMinutes=12)
        r['marketOptimization'] = trial.market.capture(r)
        r['entryExperiment'] = trial.capture(r)
        return r, truths

    def test_one_parameter_changes_and_symmetric_directions(self):
        for direction in ('LONG','SHORT'):
            variants=self.row(direction)[0]['entryExperiment']['variants']
            for key in ('reference','atr2','atr25','age20'):
                self.assertEqual(variants[key],direction)
            for key in ('atr1','age10','cautious'):
                self.assertEqual(variants[key],'NEUTRAL')

    def test_new_distance_variant_and_no_old_cohort_backfill(self):
        for direction in ('LONG','SHORT'):
            r,t=self.row(direction)
            r['marketOptimization']['entry']['deviationAtr']=2.25
            r['entryExperiment']=trial.capture(r)
            self.assertEqual(r['entryExperiment']['variants']['atr25'],direction)
            self.assertEqual(r['entryExperiment']['variants']['atr2'],'NEUTRAL')
            for g in trial.report([(r,t)],audit.outcome)['groups']:
                self.assertEqual(g['variants']['atr25']['signals'],1)
                self.assertIsNotNone(g['variants']['atr25']['worstNetEndpointPct'])
                self.assertIsNone(g['variants']['atr2']['worstNetEndpointPct'])
            r['entryExperiment']['version']='entry-experiment-v1'
            self.assertEqual(trial.report([(r,t)],audit.outcome)['sampled'],0)

    def test_unknown_input_is_not_a_wait_or_win(self):
        for value in (None, float('nan'), -1, True):
            r,t=self.row()
            r['marketOptimization']['entry']['roomR']=value
            r['entryExperiment']=trial.capture(r)
            self.assertIsNone(r['entryExperiment']['variants']['reference'])
            self.assertFalse(trial.report([(r,t)],audit.outcome)['groups'])

    def test_same_cohort_and_no_mutation_or_backfill(self):
        row=self.row(); before=copy.deepcopy(row)
        result=trial.report([row],audit.outcome)
        self.assertEqual(row,before)
        for g in result['groups']:
            self.assertEqual(g['cases'],1)
            self.assertEqual(len(g['variants']),8)
            self.assertEqual(g['variants']['cautious']['missedWins'],1)
            self.assertEqual(g['variants']['cautious']['avoidedLosses'],0)
            self.assertAlmostEqual(g['variants']['cautious']['meanDifferencePct'],-.01)
        self.assertIsNone(result['winner'])
        self.assertFalse(result['automaticRuleChange'])
        row[0].pop('entryExperiment')
        self.assertEqual(trial.report([row],audit.outcome)['sampled'],0)

    def test_reference_boundary_and_hard_room_requirement(self):
        r,t=self.row()
        r['marketOptimization']['entry'].update(deviationAtr=1.5,signalAgeMinutes=15)
        self.assertEqual(trial.capture(r)['variants']['reference'],'LONG')
        r['marketOptimization']['entry']['roomR']=1.99
        self.assertTrue(all(trial.capture(r)['variants'][k]=='NEUTRAL' for k in trial.THRESHOLDS))

    def test_stale_inputs_excluded_and_validation_separate(self):
        r,t=self.row()
        r['marketOptimization']['inputFresh']=False
        self.assertFalse(trial.report([(r,t)],audit.outcome)['groups'])
        r['marketOptimization']['inputFresh']=True
        delta=11*86400000
        r['recordedAt']+=delta
        for truth in r['_marketReviewTruths'].values(): truth['at']+=delta
        self.assertTrue(all(g['phase']=='validation' for g in trial.report([(r,t)],audit.outcome)['groups']))


if __name__=='__main__': unittest.main()
