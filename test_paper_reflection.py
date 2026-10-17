import copy
import unittest
import paper_reflection as reflection


def settled():
    return dict(id='test',status='closed',productReturnKnown=True,pendingUnits=0,
                remainingUnits=0,allocated=100.,cashReleased=101.,quantity=10,
                startedAt=1000,closedAt=61000,plan={'direction':'LONG'},exitReason='stop',
                events=[dict(kind='stop',units=10,quote={'bid':10.1})])


class ReflectionTests(unittest.TestCase):
    def test_cost_erodes_gross_win_and_replay_is_idempotent(self):
        c=settled();control={'cash':101.}
        reflection.record(control,c,70000)
        self.assertEqual(control['reflection']['reviewed'],1)
        self.assertEqual(control['reflection']['modelLosses'],1)
        self.assertIn('aufgezehrt',c['reflection']['observations'][0])
        self.assertEqual(control['cash'],101.)
        original=copy.deepcopy(control)
        reflection.record(control,c,80000)
        self.assertEqual(control,original)

    def test_missing_evidence_is_not_a_loss(self):
        c=settled();c.update(productReturnKnown=False,status='inconclusive')
        control={};reflection.record(control,c,70000)
        self.assertEqual(control['reflection']['unpriced'],1)
        self.assertEqual(control['reflection']['modelLosses'],0)
        self.assertIsNone(c['reflection']['costModel'])

    def test_unsettled_open_and_demo_cases_are_not_learned(self):
        for update in ({'status':'open'},{'pendingUnits':1},{'demonstration':True}):
            c=settled();c.update(update);control={}
            reflection.record(control,c,70000)
            self.assertNotIn('reflection',control)

    def test_recent_details_bounded_lifetime_counts_retained(self):
        control={}
        for n in range(25):
            c=settled();c['id']=str(n);reflection.record(control,c,70000+n)
        self.assertEqual(control['reflection']['reviewed'],25)
        self.assertEqual(len(control['reflection']['recent']),20)


if __name__=='__main__':unittest.main()
