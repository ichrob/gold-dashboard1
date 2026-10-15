"""Early warning latency is an observation, never permission to trade."""
import datetime as dt
import unittest
import decision_audit as d

BASE=dt.datetime(2026,10,15,12,tzinfo=dt.timezone.utc).timestamp()*1000


def row(minutes, direction='NEUTRAL', impulse=None):
    r={'recordedAt':int(BASE+minutes*60000),
       'ruleVersion':d.RULE_VERSION,'origin':'background',
       'direction':direction,'marketEvaluable':False}
    if impulse:
        r['earlyImpulse']={'version':'early-impulse-v1','available':True,
                           'direction':impulse}
    return (r,[None,None,None])


class LeadTimeTests(unittest.TestCase):
    def test_measures_forward_only_lag_and_ignores_browsers(self):
        rows=[row(15,'LONG'),row(0,impulse='LONG'),row(60,impulse='SHORT'),
              row(125,'SHORT'),row(130,'NEUTRAL')]
        result=d.early_impulse_review(rows)['leadTime']
        self.assertEqual(result['laterConfirmed'],1)
        self.assertEqual(result['meanLeadMinutes'],15)
        self.assertEqual(result['medianLeadMinutes'],15)
        self.assertEqual(result['noConfirmationWithinHour'],1)
        self.assertEqual(result['pending'],0)
        self.assertEqual(result['alreadyConfirmed'],0)

    def test_same_time_confirmation_not_counted_as_early_and_unfinished_pending(self):
        rows=[row(0,'LONG','LONG'),row(65,impulse='SHORT'),
              row(75,'NEUTRAL')]
        lead=d.early_impulse_review(rows)['leadTime']
        self.assertEqual(lead['alreadyConfirmed'],1)
        self.assertEqual(lead['pending'],1)
        self.assertEqual(lead['meanLeadMinutes'],None)
        self.assertFalse(d.early_impulse_review(rows)['automaticRuleChange'])


if __name__=='__main__':unittest.main()
