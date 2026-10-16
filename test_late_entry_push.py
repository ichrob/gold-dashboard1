import unittest
import background_push as b


class LateEntryAlertTests(unittest.TestCase):
    def setUp(self):
        self.settings=b.config({'timeframe':'15m'})
        self.market={'ready':True,'priceFresh':True,'price':4200,
            'direction':'LONG','baseDirection':'LONG','mtf':'LONG','score':85,
            'atr':4,'dataAt':1800000000000,'session':{'entryAllowed':True}}
    def kinds(self,events):
        return [x['data']['eventKind'] for x in events]
    def test_late_entry_blocked_without_disabling_real_trade_monitoring(self):
        late={**self.market,'entryTimingGate':{'available':True,'allowed':False,
             'late':True,'reason':'15-Minuten-Fenster vorbei'}}
        state,ev=b.advance({},self.settings,late,True,False,now=1000)
        self.assertNotIn('signal-change',self.kinds(ev))
        self.assertNotIn('signalPending',state)
        state,ev=b.advance(state,self.settings,{**late,'dataAt':1800000030000},True,False,now=33000)
        self.assertNotIn('signal-change',self.kinds(ev))
        timely={**self.market,'entryTimingGate':{'available':True,'allowed':True}}
        state,ev=b.advance(state,self.settings,timely,True,False,now=63000)
        self.assertNotIn('signal-change',self.kinds(ev))
        state,ev=b.advance(state,self.settings,{**timely,'dataAt':1800000030000},True,False,now=95000)
        self.assertIn('signal-change',self.kinds(ev))
    def test_closed_minute_followthrough_skips_only_redundant_push_delay(self):
        timely={**self.market,'entryTimingGate':{'available':True,'allowed':True},
                'entryTiming':'two-minute-follow-through-v1'}
        state,ev=b.advance({},self.settings,timely,True,False,now=1000)
        self.assertIn('signal-change',self.kinds(ev))
        self.assertNotIn('signalPending',state)
        # A mere early impulse or claimed timing without the shared verified
        # market gate may NOT bypass the 30-second confirmation.
        unverified={**self.market,'entryTiming':'two-minute-follow-through-v1',
                'entryTimingGate':{'available':False,'allowed':False}}
        state,ev=b.advance({},self.settings,unverified,True,False,now=1000)
        self.assertNotIn('signal-change',self.kinds(ev))
        normal={**self.market,'entryTimingGate':{'available':True,'allowed':True},
                'entryTiming':'five-minute-confirmation'}
        state,ev=b.advance({},self.settings,normal,True,False,now=1000)
        self.assertNotIn('signal-change',self.kinds(ev))

    def test_existing_trade_alerts_unchanged_by_late_gate(self):
        settings=b.config({'trade':{'active':True,'tradeId':'real-42','instrument':'XAU/USD',
            'dir':'LONG','entry':100,'stop':90,'initialRisk':10,'target':150}})
        market={**self.market,'price':88,'direction':'SHORT','baseDirection':'SHORT',
            'entryTimingGate':{'available':True,'allowed':False,'reason':'zu spät'}}
        state,ev=b.advance({},settings,market,True,True,now=1800000000100)
        self.assertNotIn('signal-change',self.kinds(ev))
        self.assertTrue(any(k in self.kinds(ev) for k in ('reversal','stop-hit','stop-near')),
            self.kinds(ev))


if __name__=='__main__':
    unittest.main()
