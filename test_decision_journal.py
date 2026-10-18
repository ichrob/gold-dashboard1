import unittest
from decision_journal import entry,valid_followup

class JournalTests(unittest.TestCase):
    def setUp(self):
        self.base=dict(at=1800000000000,priceAt=1800000000000,price=4000,valid=True,ready=True,direction='LONG',keep=False,reason='Originalgrund',evidence={'context':{'adx':20}})
    def result(self,net):
        return dict(at=self.base['at']+3600000,directionalPct=net+.04,scenarios=[dict(costPct=.04,baseline=net)])
    def test_filter_loss_and_missed_gain_are_not_real_pnl(self):
        for net,word in [(-1,'negatives'),(1,'positives')]:
            r=entry('validation',self.base,self.result(net),None,self.base['at']+3700000)
            self.assertIn(word,r['lesson']);self.assertEqual(r['netSpotPct'],net)
            self.assertEqual(r['reason'],'Originalgrund');self.assertEqual(r['phase'],'validation')
    def test_waiting_and_invalid_never_become_success(self):
        self.assertEqual(entry('development',self.base,None,None,self.base['at'])['status'],'pending')
        self.assertEqual(entry('development',self.base,None,None,self.base['at']+3800000)['status'],'missing')
        self.assertEqual(entry('development',dict(self.base,valid=False),self.result(1),None,self.base['at'])['status'],'invalid')
    def test_neutral_only_describes_movement(self):
        base=dict(self.base,ready=False,direction='NEUTRAL')
        follow=dict(valid=True,price=4040,priceAt=base['at']+3600000,at=base['at']+3600000)
        r=entry('development',base,None,follow,follow['at'])
        self.assertEqual(r['decision'],'ABWARTEN');self.assertAlmostEqual(r['marketMovePct'],1)
        self.assertIsNone(r['netSpotPct']);self.assertIn('kein Beleg',r['lesson'])
        for bad in [dict(follow,priceAt=follow['priceAt']-1),dict(follow,priceAt=follow['priceAt']+90001),dict(follow,price=0),dict(follow,valid=False)]:
            self.assertFalse(valid_followup(base,bad))
    def test_read_does_not_change_original_evidence(self):
        import copy
        old=copy.deepcopy(self.base)
        entry('validation',self.base,self.result(1),None,self.base['at']+3700000)
        self.assertEqual(old,self.base)
