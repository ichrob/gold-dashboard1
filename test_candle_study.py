import unittest
from test_candle_shadow import bars
from candle_shadow import analyze,STEPS
from candle_study import compare


class StudyTests(unittest.TestCase):
    def data(self):
        b=bars();b[-1].update(open=101,high=102,low=98,close=101.8)
        now=b[-1]['openTime']+STEPS['15m']
        row=dict(analyze(b,'15m',now),observedAt=now,baselineDirection='SHORT')
        for i in range(3):
            b.append(dict(openTime=now+i*STEPS['15m'],open=100,high=105,low=98,
                          close=104,isOpen=False,instrument='XAU/USD'))
        return {'observations':[row],'bars_by_tf':{'15m':b}},now

    def test_comparison_costs_and_duplicate_records(self):
        data,now=self.data();data['observations']*=2
        r=compare(data,now,5)['byTimeframe']['15m']
        self.assertEqual(r['baseline']['count'],1)
        self.assertAlmostEqual(r['baseline']['meanNetBps'],-405)
        self.assertEqual(r['withConflictFilter']['count'],0)
        self.assertEqual(r['removedNonpositive'],1)

    def test_cutoff_and_future_completeness(self):
        data,now=self.data()
        self.assertEqual(compare(data,now+1)['byTimeframe']['15m']['baseline']['count'],0)
        data['bars_by_tf']['15m'][-1]['isOpen']=True
        self.assertEqual(compare(data,now)['byTimeframe']['15m']['baseline']['count'],0)

    def test_never_enter_before_observation(self):
        data,now=self.data();data['observations'][0]['observedAt']=now+1
        self.assertEqual(compare(data,now)['byTimeframe']['15m']['baseline']['count'],0)

    def test_incorrect_reconstructed_hint_rejected(self):
        data,now=self.data();data['observations'][0]['direction']='SHORT'
        self.assertEqual(compare(data,now)['byTimeframe']['15m']['baseline']['count'],0)


if __name__=='__main__':unittest.main()
