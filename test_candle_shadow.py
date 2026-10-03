import copy
import io
import unittest
from contextlib import redirect_stdout
import candle_shadow as cs


def bars(tf='15m'):
    step = cs.STEPS[tf]
    start = (1700000000000//step)*step
    return [dict(openTime=start+i*step, open=100, high=102, low=98,
                 close=100, isOpen=False, instrument='XAU/USD') for i in range(21)]


class CandleTests(unittest.TestCase):
    def assess(self, b, tf='15m', age=0):
        return cs.analyze(b, tf, b[-1]['openTime']+cs.STEPS[tf]+age)

    def test_support_rejection_and_mirror(self):
        b=bars();b[-1].update(open=101, high=102, low=98, close=101.8)
        r=self.assess(b)
        self.assertEqual(r['direction'], 'LONG')
        self.assertAlmostEqual(r['metrics']['priorAtr'],4)
        for x in b:
            x.update(open=200-x['open'], close=200-x['close'],
                     high=200-x['low'], low=200-x['high'])
        self.assertEqual(self.assess(b)['direction'], 'SHORT')

    def test_context_required(self):
        b=bars();b[-1].update(open=101,high=102,low=98,close=101.8)
        for x in b[:-1]:x['low']=90
        self.assertEqual(self.assess(b)['direction'],'NEUTRAL')

    def test_two_wicks_not_directional(self):
        self.assertEqual(self.assess(bars())['direction'],'NEUTRAL')

    def test_open_candle_cannot_change_signal(self):
        b=bars();now=b[-1]['openTime']+cs.STEPS['15m']
        expected=cs.analyze(b,'15m',now)
        b.append(dict(b[-1],openTime=now,low=1,high=1000,isOpen=False))
        self.assertEqual(cs.analyze(b,'15m',now),expected)

    def test_invalid_and_incomplete_inputs(self):
        cases=[('close',float('nan')),('high',float('inf')),('open',True),
               ('low',103),('instrument','GCZ26-estimate'),('estimated',True),
               ('isOpen',None),('openTime',True)]
        for key,value in cases:
            with self.subTest(key=key):
                b=bars();b[-1][key]=value
                now=bars()[-1]['openTime']+cs.STEPS['15m']
                self.assertEqual(cs.analyze(b,'15m',now)['status'],'unavailable')

    def test_stale_gaps_mixed_and_duplicate(self):
        b=bars()
        self.assertEqual(self.assess(b,age=900001)['status'],'unavailable')
        for modify in ('gap','mixed','duplicate','reversed'):
            z=copy.deepcopy(b)
            if modify=='gap':z[0]['openTime']-=900000
            if modify=='mixed':z[0]['instrument']='GC=F'
            if modify=='duplicate':z[0]['openTime']=z[1]['openTime']
            if modify=='reversed':z[0],z[1]=z[1],z[0]
            self.assertEqual(self.assess(z)['status'],'unavailable')

    def test_no_mutation_and_log_deduplication(self):
        history={tf:bars(tf) for tf in cs.STEPS};original=copy.deepcopy(history)
        baseline={tf:{'dir':'LONG','available':True} for tf in cs.STEPS}
        baseline_before=copy.deepcopy(baseline)
        now=max(b[-1]['openTime']+cs.STEPS[tf] for tf,b in history.items())
        cs._seen.clear()
        output=io.StringIO()
        with redirect_stdout(output):
            first=cs.snapshot(history,baseline,now)
            second=cs.snapshot(history,baseline,now)
        self.assertEqual(first,second)
        self.assertEqual(history,original)
        self.assertEqual(baseline,baseline_before)
        self.assertFalse(first['affectsSelection'])
        self.assertEqual(len(output.getvalue().splitlines()),sum(
            r['status']=='observed' for r in first['byTimeframe'].values()))

    def test_each_timeframe_and_source(self):
        for tf in cs.STEPS:
            b=bars(tf)
            for x in b:x['instrument']='GC=F'
            self.assertEqual(self.assess(b,tf)['instrument'],'GC=F')

    def test_integration_is_additive_and_failure_isolated(self):
        # Execute the actual server hook without importing network/service startup.
        from pathlib import Path
        source=Path(__file__).with_name('server.py').read_text()
        hook=source[source.index('        # Research output only.'):source.index('        _live_cache = bundle')]
        import textwrap
        bundle={'history':{'bars_by_tf':{tf:bars(tf) for tf in cs.STEPS}},'spots':{'xaus':100}}
        original=copy.deepcopy(bundle)
        scope={'bundle':bundle,'candle_shadow':cs,'now':1701000000,
               '_mtf_score':lambda b,tf:{'dir':'LONG','available':True}}
        exec(textwrap.dedent(hook),scope)
        self.assertEqual({k:v for k,v in bundle.items() if k!='candleShadow'},original)
        from unittest.mock import patch
        with patch.object(cs,'snapshot',side_effect=RuntimeError),redirect_stdout(io.StringIO()):
            exec(textwrap.dedent(hook),scope)
        self.assertEqual(bundle['candleShadow']['status'],'unavailable')
        self.assertEqual(bundle['spots'],original['spots'])


if __name__=='__main__':unittest.main()
