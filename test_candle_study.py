import unittest
from test_candle_shadow import bars
from candle_shadow import analyze,STEPS
from candle_study import compare


class StudyTests(unittest.TestCase):
    def test_early_hint_outcome_and_missing_data(self):
        from candle_study import early_hints
        now=1800000000000
        histories={};records=[]
        for tf in ('1m','5m'):
            step=STEPS[tf]
            b=[dict(openTime=now-(21-i)*step,open=100,high=102,low=98,close=100,isOpen=False,instrument='XAU/USD') for i in range(21)]
            if tf=='1m':b[-1].update(open=101,close=101.8)
            records.append(dict(analyze(b,tf,now),observedAt=now))
            histories[tf]=b
        for i in range(15):
            histories['1m'].append(dict(openTime=now+i*60000,open=100,high=105,low=98,close=104,isOpen=False,instrument='XAU/USD'))
        data={'observations':records,'bars_by_tf':histories}
        r=early_hints(data,now,5)['pairs']['1m_5m']
        self.assertEqual(r['evaluated'],1)
        self.assertEqual(r['positive'],1)
        self.assertAlmostEqual(r['meanNetBps'],395)
        self.assertIsNone(r['meanObservedLeadMinutes'])
        histories['1m'][-1]['isOpen']=True
        r=early_hints(data,now,5)['pairs']['1m_5m']
        self.assertEqual(r['evaluated'],0)
        self.assertEqual(r['missingOutcome'],1)

    def data(self,tf='15m'):
        b=bars(tf);b[-1].update(open=101,high=102,low=98,close=101.8)
        now=b[-1]['openTime']+STEPS[tf]
        row=dict(analyze(b,tf,now),observedAt=now,baselineDirection='SHORT')
        for i in range(3):
            b.append(dict(openTime=now+i*STEPS[tf],open=100,high=105,low=98,
                          close=104,isOpen=False,instrument='XAU/USD'))
        return {'observations':[row],'bars_by_tf':{tf:b}},now

    def test_thirty_minute_comparison(self):
        data,now=self.data('30m')
        result=compare(data,now,5)['byTimeframe']['30m']
        self.assertEqual(result['baseline']['count'],1)
        self.assertEqual(result['removedNonpositive'],1)
        self.assertAlmostEqual(result['baseline']['meanNetBps'],-405)

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
