import unittest
from datetime import date,timedelta
import improvement_assessment as a
import improvement_tracker as m


def trial_rows(sign=1):
    rows=[]
    for day in range(20):
        for case in range(5):
            keep=case<3
            change=.5 if keep else -sign
            out=dict(keep=keep,directionalPct=change,scenarios=[dict(baseline=change-c,candidate=change-c if keep else 0) for c in [.04,.12]])
            rows.append(((date(2026,11,1)+timedelta(days=day)).isoformat(),'validation',dict(cohort='one',evidence={'context':{'adx':25,'trend':'LONG'}}),out))
    return rows


def review(rows,complete=True):
    return a.assess(rows,dict(cohort='one',development=dict(count=60,days=10),validation=m.pairs(rows)),
        m.real_results([]),[100,0,100 if complete else 50,50],True,dict(expected=100,coveragePct=100))


class AssessmentTests(unittest.TestCase):
    def test_no_data_and_incomplete_never_advantage(self):
        self.assertEqual(review([])['code'],'collecting')
        self.assertEqual(review(trial_rows()[:5],False)['code'],'unclear')
        self.assertEqual(review(trial_rows(),False)['code'],'unclear')

    def test_benefit_loss_and_no_automatic_change(self):
        good=review(trial_rows())
        self.assertEqual(good['code'],'benefit')
        self.assertFalse(good['automaticRuleChange'])
        bad=review(trial_rows(-1))
        self.assertEqual(bad['code'],'worse')
        self.assertEqual(bad['missedWinners'],40)
        self.assertEqual(good['independentCases'],100)
        self.assertEqual(good['intervals'][0]['blocks'],10)

    def test_regime_uses_entry_evidence_not_outcome(self):
        self.assertEqual(a.regime({'evidence':{'context':{'adx':12,'trend':'LONG'}}}),'sideways')
        self.assertEqual(a.regime({'evidence':{'context':{'adx':25,'trend':'SHORT'}}}),'falling')
        self.assertEqual(a.regime({}),'unknown')
        self.assertEqual(a.regime({'evidence':{'context':{'adx':float('nan'),'trend':'LONG'}}}),'unknown')

    def test_other_versions_excluded_and_day_uncertainty(self):
        rows=trial_rows();rows[0][2]['cohort']='older'
        self.assertEqual(review(rows)['independentCases'],99)
        same_day=[('2026-11-01',phase,p,o) for d,phase,p,o in trial_rows()]
        self.assertIsNone(a.interval(same_day))

if __name__=='__main__':unittest.main()
