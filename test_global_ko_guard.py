"""Global KO guard integration: selection already blocks narrow KO buffers;
these tests cover live-trade advice; issuer-verified paper exits have separate tests."""
import unittest
import background_push
from test_paper_simulation import market, NOW, ISIN


def issuer_quote(at, ko=99.3, direction='LONG'):
    return {**quote(at), 'productVerified': True, 'direction': direction,
            'ko': ko, 'metadata': {'underlyingType': 'SPOT', 'ko': ko}}


class KoGuardIntegrationTests(unittest.TestCase):
    def test_live_position_has_pre_ko_warning_not_broker_order(self):
        product=dict(isin=ISIN,simpleSpotTurbo=True,referenceConfirmed=True,
                     currency='EUR',direction='LONG',bid=10.,goldReference=100.,
                     fxReference=1.,fxScenario=1.,ratio=.1,strike=90.,ko=98.2,
                     entry=10.,quantity=10,source='issuer',referenceAt='2026-10-08T07:00:00Z')
        settings=background_push.config(dict(trade=dict(active=True,tradeId='ko1',
                     instrument='XAU/USD',dir='LONG',entry=100,stop=90,
                     initialRisk=10,target=120,product=product)))
        m={**market(),'atr':.5,'session':{'entryAllowed':True}}
        state,events=background_push.advance({},settings,m,False,True,now=NOW)
        self.assertIn('ko-risk-warning',[e['data']['eventKind'] for e in events])
        self.assertEqual(state['trade']['koProtection']['level'],'warning')
        self.assertIn('Kein automatischer Verkauf', ' '.join(e['body'] for e in events))
        state,second=background_push.advance(state,settings,m,False,True,now=NOW+30000)
        self.assertNotIn('ko-risk-warning',[e['data']['eventKind'] for e in second])
        stale={**m,'priceFresh':False,'price':99.0}
        _,third=background_push.advance({},settings,stale,False,True,now=NOW)
        self.assertFalse(any(e['data']['eventKind'].startswith('ko-risk') for e in third))


if __name__=='__main__':
    unittest.main()
