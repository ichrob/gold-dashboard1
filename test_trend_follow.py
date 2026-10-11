"""Trend follower must behave differently from existing partial-profit paper model."""
import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
import paper_simulation as sim
import trend_follow
import paper_portfolios

NOW=int(datetime(2026,10,12,9,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
ISIN='DE000PJ9NCK0'

def market(price=4000.,at=NOW,direction='LONG',bar=NOW,trend_direction='LONG'):
    return dict(plan=dict(kind='candidate',direction='LONG',entry=4000.,stop=3980.,target=4040.,unit='USD/oz'),
        price=price,priceFresh=True,ready=True,dataAt=at,analysisBarAt=bar,
        ruleVersion='trend-test-constant-v1',direction=direction,score=82,atr=10,
        trendContext=dict(available=True,intact=direction==trend_direction,
                          direction=trend_direction),session=dict(entryAllowed=True))

def quote(at=NOW,bid=10.):
    return dict(isin=ISIN,found=True,marketOpen=True,currency='EUR',source='issuer-test',
        bid=bid,ask=bid+.1,bidAt=at,askAt=at)

def case(hold=True):
    c=sim.new_case(market(),dict(isin=ISIN),quote(),NOW,cash=800.)
    c['endsAt']=NOW+8*3600000
    if hold:
        c.update(trendFollow=True,exitPolicy=trend_follow.VERSION,trendHighWater=4000.,
                 trendReversalBars=0,trendExtensions=0)
    return c

class TrendExitTests(unittest.TestCase):
    def test_holds_entire_position_past_first_target_without_partial_profit(self):
        tick=market(price=4045.,at=NOW+30_000)
        held=sim.advance_case(case(),tick,quote(NOW+30_000,10.5),NOW+30_000)
        normal=sim.advance_case(case(False),tick,quote(NOW+30_000,10.5),NOW+30_000)
        self.assertEqual(held['status'],'open')
        self.assertEqual(held['remainingUnits'],held['quantity'])
        self.assertFalse(held['partialTaken'])
        self.assertTrue(any(e['kind']=='trend-target-continued' for e in held['events']))
        self.assertFalse(any(e['kind']=='partial-profit' for e in held['events']))
        self.assertTrue(any(e['kind']=='partial-profit' for e in normal['events']))
        self.assertLess(normal['remainingUnits'],normal['quantity'])

    def test_trailing_never_loosens_and_stop_wins_before_new_trailing(self):
        opened=case()
        favorable=sim.advance_case(opened,market(price=4045.,at=NOW+30_000),
                                   quote(NOW+30_000,10.7),NOW+30_000)
        new_stop=favorable['engine']['trade']['stop']
        self.assertGreater(new_stop,3980.)
        setback=sim.advance_case(favorable,market(price=4038.,at=NOW+60_000),
                                 quote(NOW+60_000,10.4),NOW+60_000)
        self.assertGreaterEqual(setback['engine']['trade']['stop'],new_stop)
        stopped=sim.advance_case(setback,market(price=new_stop-1,at=NOW+90_000),
                                 quote(NOW+90_000,9.8),NOW+90_000)
        self.assertEqual(stopped['exitReason'],'stop')
        self.assertEqual(stopped['status'],'closed')
        self.assertEqual(stopped['remainingUnits'],0)

    def test_counter_signal_needs_two_distinct_completed_bars(self):
        c=case()
        opposite=lambda stamp,bar: market(price=4001.,at=stamp,direction='SHORT',
                                            bar=bar,trend_direction='SHORT')
        c=sim.advance_case(c,opposite(NOW+30_000,NOW+15*60_000),
                            quote(NOW+30_000,9.9),NOW+30_000)
        self.assertEqual(c['trendReversalBars'],1)
        self.assertEqual(c['status'],'open')
        c=sim.advance_case(c,opposite(NOW+60_000,NOW+15*60_000),
                            quote(NOW+60_000,9.9),NOW+60_000)
        self.assertEqual(c['trendReversalBars'],1)
        self.assertEqual(c['status'],'open')
        c=sim.advance_case(c,opposite(NOW+90_000,NOW+30*60_000),
                            quote(NOW+90_000,9.9),NOW+90_000)
        self.assertEqual(c['status'],'closed')
        self.assertEqual(c['exitReason'],'trend-confirmed-reversal')

    def test_counter_signal_reset_does_not_accumulate(self):
        c=case()
        c=sim.advance_case(c,market(price=4001.,at=NOW+30_000,
             direction='SHORT',bar=NOW+15*60_000,trend_direction='SHORT'),
             quote(NOW+30_000),NOW+30_000)
        c=sim.advance_case(c,market(price=4002.,at=NOW+60_000,
             direction='LONG',bar=NOW+15*60_000,trend_direction='LONG'),
             quote(NOW+60_000),NOW+60_000)
        self.assertEqual(c['trendReversalBars'],0)
        self.assertEqual(c['status'],'open')

    def test_gap_rejected_instead_of_fabricating_exit(self):
        c=case()
        invalid=market(price=4050.,at=NOW+150_000)
        out=sim.advance_case(c,invalid,quote(NOW+150_000),NOW+150_000)
        self.assertEqual(out['status'],'inconclusive')
        self.assertFalse(out['productReturnKnown'])
        self.assertTrue(any(e['kind']=='data-gap' for e in out['events']))
        self.assertFalse(any(e['kind']=='trend-target-continued' for e in out['events']))

    def test_manual_watch_and_original_three_profiles_untouched(self):
        self.assertEqual(paper_portfolios.POLICIES['trend800']['initial_capital_eur'],800)
        self.assertEqual({k:paper_portfolios.POLICIES[k].get('initial_capital_eur',100)
            for k in ('conservative','balanced','offensive')},
            {'conservative':100,'balanced':100,'offensive':100})
        import pathlib
        content=pathlib.Path('degiro_assistant.js').read_text(encoding='utf-8')
        self.assertIn("const KEY='bobManualTradeTestV1'",content)
        self.assertIn('manual-paper-test',content)

if __name__=='__main__':
    unittest.main()
