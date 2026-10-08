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

class FxTarget(unittest.TestCase):
    def test_fx_changes_estimate_without_triggering_gold_target(self):
        import copy
        now=1791453600000
        p=dict(isin='DE000FG4JXV7',direction='LONG',simpleSpotTurbo=True,referenceConfirmed=True,currency='EUR',bid=20,goldReference=100,fxReference=.9,fxScenario=.9,ratio=.1,strike=50,ko=50,entry=20,quantity=10,source='fixture',referenceAt='2026-10-08T10:00:00Z')
        settings=b.config({'trade':{'active':True,'tradeId':'fx','instrument':'XAU/USD','dir':'LONG','entry':100,'stop':90,'initialRisk':10,'target':120,'product':p}})
        original=copy.deepcopy(settings)
        market={'ready':True,'priceFresh':True,'price':101,'direction':'LONG','dataAt':now,'fx':{'rate':1.2,'fetchedAt':'2026-10-08T10:00:00Z'}}
        state,events=b.advance({},settings,market,False,True,now=now,log=False)
        self.assertEqual(settings,original)
        self.assertEqual(state['trade']['target'],120)
        self.assertFalse(any(e['data']['eventKind'] in ('target','target-extension') for e in events))
        market.update(price=120)
        _,events=b.advance(state,settings,market,False,True,now=now,log=False)
        event=next(e for e in events if e['data']['eventKind']=='target')
        self.assertIn('Gold 120.00 USD/oz',event['body'])
        self.assertIn('23.9000 EUR',event['body'])
        self.assertIn('geschätzt',event['body'])

class ContinuedCalculation(unittest.TestCase):
    def test_outage_keeps_original_clock_and_recalculates(self):
        settings=b.config({'trade':{'active':True,'tradeId':'cached','instrument':'XAU/USD','dir':'LONG','entry':100,'stop':90,'initialRisk':10,'target':120}})
        state,_=b.advance({},settings,{'ready':True,'priceFresh':True,'price':105,'dataAt':100000},False,True,now=100000,log=False)
        for now in (130000,160000,200000):
            state,events=b.advance(state,settings,{'ready':False,'priceFresh':False,'analysisError':True},False,True,now=now,log=False)
            calc=state['continuedCalculation']
            self.assertEqual(calc['dataAt'],100000)
            self.assertEqual(calc['computedAt'],now)
            self.assertEqual(calc['stopDistance'],15)
            self.assertTrue(calc['stale'])
            self.assertFalse(any(e['data']['eventKind'] in ('target','stop','target-extension') for e in events))
        self.assertTrue(any(e['data']['eventKind']=='data-unavailable' for e in events))
        state,_=b.advance(state,settings,{'ready':True,'priceFresh':True,'price':106,'dataAt':230000},False,True,now=230000,log=False)
        self.assertFalse(state['continuedCalculation']['stale'])
        self.assertEqual(state['continuedCalculation']['dataAt'],230000)

if __name__=='__main__':unittest.main()
