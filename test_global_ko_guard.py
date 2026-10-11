"""Global KO guard integration: selection already blocks narrow KO buffers;
these tests cover live trade alerts and all automatic paper portfolios."""
import unittest
import background_push
import paper_simulation as sim
from test_paper_simulation import market, tick, quote, NOW, ISIN


def issuer_quote(at, ko=98.6, direction='LONG'):
    return {**quote(at), 'productVerified': True, 'direction': direction,
            'ko': ko, 'metadata': {'underlyingType': 'SPOT', 'ko': ko}}


class KoGuardIntegrationTests(unittest.TestCase):
    def test_paper_exits_before_long_ko_with_synchronized_eur_bid(self):
        m=market()
        choice={'isin':ISIN,'scope':'XAU/USD'}
        c=sim.new_case(m,choice,issuer_quote(NOW),NOW,cash=101.)
        self.assertTrue(c['koReference']['verified'])
        fresh=issuer_quote(NOW+30000)
        advanced=sim.advance_case(c,tick(100,atr=.5),fresh,NOW+30000)
        self.assertEqual(advanced['status'],'closed')
        self.assertEqual(advanced['exitReason'],'ko-protective-exit')
        self.assertEqual(advanced['bookedUnits'],10)
        self.assertTrue(advanced['productReturnKnown'])

    def test_paper_no_quote_never_invents_ko_exit(self):
        c=sim.new_case(market(),{'isin':ISIN,'scope':'XAU/USD'},issuer_quote(NOW),NOW,cash=101.)
        advanced=sim.advance_case(c,tick(100,atr=.5),None,NOW+30000)
        self.assertEqual(advanced['status'],'open')
        self.assertEqual(advanced['cashReleased'],0)
        self.assertEqual(advanced['pendingUnits'],0)
        self.assertIn('ko-risk-no-sale',[e['kind'] for e in advanced['events']])
        self.assertEqual(advanced['koProtection']['level'],'critical')

    def test_paper_rejects_old_sale_bid_at_ko_event(self):
        c=sim.new_case(market(),{'isin':ISIN,'scope':'XAU/USD'},issuer_quote(NOW),NOW,cash=101.)
        advanced=sim.advance_case(c,tick(100,atr=.5),issuer_quote(NOW+23000),NOW+30000)
        self.assertEqual(advanced['status'],'open')
        self.assertEqual(advanced['cashReleased'],0)

    def test_future_ko_not_compared_to_spot(self):
        choice={'isin':ISIN,'scope':'FUTURE'}
        c=sim.new_case(market(),choice,issuer_quote(NOW),NOW,cash=101.)
        self.assertIsNone(c['koReference'])
        advanced=sim.advance_case(c,tick(100,atr=.5),issuer_quote(NOW+30000),NOW+30000)
        self.assertNotEqual(advanced.get('exitReason'),'ko-protective-exit')

    def test_short_ko_guard_exits_on_confirmed_bid(self):
        m=market('SHORT')
        c=sim.new_case(m,{'isin':ISIN,'scope':'XAU/USD'},
                       issuer_quote(NOW,ko=101.4,direction='SHORT'),NOW,cash=101.)
        advanced=sim.advance_case(c,tick(100,atr=.5,direction='SHORT'),
                                  issuer_quote(NOW+30000,ko=101.4,direction='SHORT'),NOW+30000)
        self.assertEqual(advanced['exitReason'],'ko-protective-exit')

    def test_live_position_has_pre_ko_warning_not_broker_order(self):
        product=dict(isin=ISIN,simpleSpotTurbo=True,referenceConfirmed=True,
                     currency='EUR',direction='LONG',bid=10.,goldReference=100.,
                     fxReference=1.,fxScenario=1.,ratio=.1,strike=90.,ko=98.6,
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
