import unittest
import background_push as b

class TargetCheckpoint(unittest.TestCase):
    def run_case(self,side='LONG',blocked=False,phase='CONTINUATION'):
        long=side=='LONG'
        settings=b.config({'trade':{'active':True,'tradeId':'checkpoint','instrument':'XAU/USD','dir':side,'entry':100,'stop':90 if long else 110,'initialRisk':10,'target':120 if long else 80}})
        market={'ready':True,'priceFresh':True,'price':120 if long else 80,'dataAt':1800000000000,'direction':side,'mtf':side,'score':80 if long else 20,'atr':4,'macd':2 if long else -2,'signal':0,'analysisBarAt':1799999900000,'suggestedTarget':145 if long else 55,'suggestedStop':80 if long else 120,'suggestedTargetPlan':{'entrySuitable':not blocked,'warning':'Hindernis geprüft'},'trendContext':{'available':True,'intact':True,'direction':side,'phase':phase}}
        return settings,market,b.advance({},settings,market,False,True,now=1800000000000)
    def test_continuation_and_stop_never_loosened(self):
        for side in ['LONG','SHORT']:
            settings,market,(state,events)=self.run_case(side)
            self.assertTrue(any(e['data']['eventKind']=='target-extension' for e in events))
            self.assertTrue(state['trade']['stop']>=90 if side=='LONG' else state['trade']['stop']<=110)
            self.assertFalse(any(e['data']['eventKind']=='target-extension' for e in b.advance(state,settings,market,False,True,now=1800000030000)[1]))
    def test_obstacle_blocks_extension_not_monitoring(self):
        for side in ['LONG','SHORT']:
            _,_,(state,events)=self.run_case(side,True)
            self.assertEqual(state['trade']['target'],120 if side=='LONG' else 80)
            self.assertFalse(any(e['data']['eventKind']=='target-extension' for e in events))
            self.assertTrue(any('Fortsetzung' in e['body'] for e in events))
    def test_pullback_is_checkpoint_not_forced_exit(self):
        _,_,(_,events)=self.run_case(phase='PULLBACK')
        self.assertFalse(any(e['data']['eventKind']=='target-extension' for e in events))
        self.assertTrue(any('Haupttrend intakt' in e['body'] for e in events))

if __name__=='__main__':unittest.main()
