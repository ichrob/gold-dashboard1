import copy
import unittest
import background_push as b

NOW=1793181600000  # 2026-10-28 10:00 UTC
class RiskBackgroundTests(unittest.TestCase):
    def event(self,kind='risk-warning',channel='general'):
        return {'title':'RISIKO','body':'Test','tag':'bob-risk-'+channel,'data':{
            'kind':channel,'eventKind':kind,'riskOnly':True,'expiresAt':NOW+60000,
            'dataAt':NOW,'generatedAt':NOW,'tradeId':'a' if channel=='trade' else None}}
    def market(self,event=None):
        return {'ready':False,'priceFresh':False,'risk':{'state':{'checkedAt':NOW,'enabled':True},'events':[event or self.event()]}}
    def test_opt_in_is_strict_and_default_unchanged(self):
        self.assertNotIn('riskEnabled',b.config({}))
        self.assertTrue(b.config({'riskEnabled':True})['riskEnabled'])
        for v in ['true',1,None]:
            with self.assertRaises(ValueError):b.config({'riskEnabled':v})
    def test_fast_signal_independent_of_slow_history_but_not_optout(self):
        state,events=b.advance({},b.config({'riskEnabled':True}),self.market(),True,False,NOW,log=False)
        self.assertEqual(events[0]['data']['eventKind'],'risk-warning')
        self.assertTrue(state['risk']['enabled'])
        state,events=b.advance({},b.config({}),self.market(),True,False,NOW,log=False)
        self.assertFalse(events)
        self.assertNotIn('risk',state)
    def test_expired_result_not_delivered(self):
        for market in [self.market({**self.event(),'data':{**self.event()['data'],'expiresAt':NOW}}),
                       {**self.market(),'risk':{'state':{'checkedAt':NOW-60001},'events':[self.event()]}}]:
            _,events=b.advance({},b.config({'riskEnabled':True}),market,True,False,NOW,log=False)
            self.assertFalse(events)
    def test_trade_identity_and_channel_gate(self):
        cfg=b.config({'riskEnabled':True,'trade':{'active':True,'tradeId':'a','instrument':'XAU/USD','dir':'LONG','entry':4000,'stop':3900,'initialRisk':100}})
        event=self.event('risk-exit','trade')
        _,events=b.advance({},cfg,self.market(event),False,True,NOW,log=False)
        self.assertEqual(len(events),1)
        event['data']['tradeId']='other'
        _,events=b.advance({},cfg,self.market(event),False,True,NOW,log=False)
        self.assertFalse(events)
    def test_optional_and_existing_alerts_are_separate(self):
        optional=self.event('risk-exit','trade')
        ordinary=self.event('stop-hit','trade');ordinary['data']['riskOnly']=False
        groups=b.notification_batches([optional,ordinary])
        self.assertEqual(groups,[[ordinary],[optional]])
        self.assertFalse(b.compose_events(groups[0])['data']['riskOnly'])
        self.assertTrue(b.compose_events(groups[1])['data']['riskOnly'])
    def test_exit_priority_and_short_expiry(self):
        exit=self.event('risk-exit','trade')
        advisory={**self.event('signal-change'),'data':{**self.event('signal-change')['data'],'riskOnly':False,'expiresAt':NOW+180000}}
        msg=b.compose_events([advisory,exit])
        self.assertEqual(msg['data']['eventKind'],'risk-exit')
        self.assertEqual(msg['data']['expiresAt'],NOW+60000)
        self.assertEqual(msg['body'],'Test')
if __name__=='__main__':unittest.main()
