import copy
import unittest
from fibonacci_monitor import validate_monitor, advance_monitor, LEVELS

NOW = 1790848800000
STEP = 300000

class MonitorTests(unittest.TestCase):
    def monitor(self, direction='LONG', instrument='XAU/USD'):
        return validate_monitor(dict(tradeId='example', direction=direction,timeframe='5m',instrument=instrument,
            levels={k:4050 for k in LEVELS},startedAt=NOW-STEP,previousClose=4040), NOW)
    def bar(self, close=4060, **extra):
        return dict(openTime=NOW-STEP,close=close,instrument='XAU/USD',isOpen=False,**extra)
    def test_cross_and_repeated_poll(self):
        original=self.monitor(); before=copy.deepcopy(original)
        state,events,status=advance_monitor(original,[self.bar()],NOW)
        self.assertEqual(original,before)
        self.assertEqual(len(events),6)
        self.assertTrue(all(e['favorable'] for e in events))
        self.assertEqual(advance_monitor(state,[self.bar()],NOW)[1],[])
    def test_short_and_down(self):
        m=self.monitor('SHORT');m['previousClose']=4060
        self.assertTrue(advance_monitor(m,[self.bar(4040)],NOW)[1][0]['favorable'])
        self.assertFalse(advance_monitor(self.monitor('SHORT'),[self.bar()],NOW)[1][0]['favorable'])
    def test_open_future_stale_and_instrument_rejected(self):
        for update in ({'isOpen':True},{'openTime':NOW},{'instrument':'GC=F'},{'openTime':NOW-STEP*5},{'close':float('nan')}):
            b=self.bar();b.update(update)
            self.assertEqual(advance_monitor(self.monitor(),[b],NOW)[1],[])
    def test_no_pretrade_or_gap_alerts(self):
        m=self.monitor();m['processedAt']=NOW
        self.assertEqual(advance_monitor(m,[self.bar()],NOW)[1],[])
        m=self.monitor();m['processedAt']=NOW-STEP*10
        self.assertEqual(advance_monitor(m,[self.bar()],NOW)[1],[])
    def test_frozen_levels_and_reentry(self):
        m=self.monitor();state,events,_=advance_monitor(m,[self.bar()],NOW)
        later=self.bar(4040);later['openTime']=NOW
        state,events,_=advance_monitor(state,[later],NOW+STEP)
        self.assertTrue(all(not e['favorable'] for e in events))
        self.assertEqual(state['levels'],m['levels'])
    def test_invalid_snapshots(self):
        m=self.monitor()
        for k,v in [('levels',{}),('direction','NEUTRAL'),('timeframe','4h'),('instrument','unknown'),('previousClose',float('inf')),('startedAt',NOW+60000)]:
            with self.assertRaises(ValueError):validate_monitor({**m,k:v},NOW)
    def test_aggregate_preserves_instrument(self):
        import server
        b=self.bar();b.update(open=4040,high=4065,low=4035)
        start=b['openTime']//900000*900000
        rows=[dict(b,openTime=start+i*300000) for i in range(3)]
        self.assertEqual(server.aggregate_bars(rows,15)[0]['instrument'],'XAU/USD')
        self.assertEqual(server.aggregate_bars([rows[0],rows[2]],15),[])
        self.assertEqual(server.aggregate_bars(rows+[rows[0]],15),[])
        self.assertEqual(server.aggregate_bars([rows[0],dict(rows[1],instrument='GC=F'),rows[2]],15),[])
        self.assertEqual(server.aggregate_bars([dict(rows[0],high=float('inf')),*rows[1:]],15),[])
        self.assertTrue(server.aggregate_bars([dict(rows[0],isOpen=True),*rows[1:]],15)[0]['isOpen'])

if __name__=='__main__':unittest.main()
