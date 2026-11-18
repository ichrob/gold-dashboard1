"""Forward-only 2x5m paper signal must never turn main NEUTRAL into live approval."""
import copy
import unittest
from datetime import datetime, timezone
import paper_portfolios as portfolio
import stop_target_audit

NOW=int(datetime(2026,11,18,11,10,30,tzinfo=timezone.utc).timestamp()*1000)
BAR=(NOW//300000-1)*300000
SOURCE='two-candle-5m-paper-v1'

def market(side='LONG'):
    sign=1 if side=='LONG' else -1
    price=4000.1
    plan={'kind':'candidate','direction':side,'entry':price,
        'stop':price-sign*7.5,'target':price+sign*15,
        'source':SOURCE,'unit':'USD/oz','paperOnly':True,
        'experimental':True}
    assert stop_target_audit.valid_plan(plan)
    return {'ready':True,'priceFresh':True,'dataAt':NOW-15000,
        'price':price,'score':50,'direction':'NEUTRAL',
        'plan':None,'ruleVersion':'intraday-trend-follow-v7',
        'trendContext':{'available':True,'intact':True,'direction':side},
        'dmi':{'frames':{'15m':{'available':True,'direction':side},
                          '1h':{'available':True,'direction':side}}},
        'paperTwoCandleEntry':{'version':'two-closed-5m-paper-v1',
            'source':SOURCE,'paperOnly':True,'comparisonOnly':True,
            'realOrders':False,'liveRulesChanged':False,
            'entryApproved':False,'productApproved':False,
            'status':'ready','direction':side,'barAt':BAR,
            'sourceAt':NOW-15000,'plan':plan}}

class TwoCandlePortfolioTests(unittest.TestCase):
    def test_profile_and_old_account_isolation(self):
        p=portfolio.POLICIES['early5m1000nov']
        self.assertEqual(p['initial_capital_eur'],1000.)
        self.assertEqual(p['exposure_fraction'],.65)
        self.assertEqual(p['daily_loss_fraction'],.03)
        self.assertEqual(p['max_holding_minutes'],300)
        self.assertTrue(p['fresh_validation'])
        self.assertTrue(p['two_candle_early'])
        self.assertTrue(p['require_trend'])
        self.assertNotIn('early5m1000nov',portfolio.FRESH_VALIDATION_PROFILES)
        self.assertEqual(p['campaign_end'],portfolio.FRESH_VALIDATION_END)
        self.assertNotEqual(portfolio.names('early5m1000nov')['bob_paper_control'],
                            portfolio.names('normal1000dec')['bob_paper_control'])

    def test_valid_both_directions_without_fabricating_70_30_score(self):
        for side in ('LONG','SHORT'):
            original=market(side)
            before=copy.deepcopy(original)
            scoped=portfolio.two_candle_paper_market(original,NOW)
            self.assertEqual(original,before,'Original market must not mutate')
            self.assertEqual(original['direction'],'NEUTRAL')
            self.assertEqual(scoped['direction'],side)
            self.assertEqual(scoped['score'],50)
            self.assertEqual(scoped['paperEntrySource'],SOURCE)
            self.assertEqual(scoped['entryPlanState']['state'],'ready')
            self.assertEqual(scoped['analysisBarAt'],BAR)
            self.assertEqual(scoped['entryTimingGate']['paperOnly'],True)
            self.assertTrue(scoped['entryTimingGate']['allowed'])
            self.assertIsNone(portfolio.entry_block_reason(
                portfolio.POLICIES['early5m1000nov'],scoped))
            self.assertIsNotNone(portfolio.entry_block_reason(
                portfolio.POLICIES['normal1000nov'],scoped))
            self.assertFalse(scoped['plan'].get('entryApproved',False))
            self.assertTrue(stop_target_audit.valid_plan(scoped['plan']))

    def test_forged_stale_and_inconsistent_trial_cannot_become_entry(self):
        original=market('SHORT')
        modifications=[
            ('missing-trial',lambda m:m.pop('paperTwoCandleEntry')),
            ('non-object',lambda m:m.update(paperTwoCandleEntry=['bogus'])),
            ('wrong-version',lambda m:m['paperTwoCandleEntry'].update(version='fake')),
            ('broker-approval',lambda m:m['paperTwoCandleEntry'].update(entryApproved=True)),
            ('not-comparison',lambda m:m['paperTwoCandleEntry'].update(comparisonOnly=False)),
            ('missing-original-clock',lambda m:m['paperTwoCandleEntry'].pop('sourceAt')),
            ('fabricated-clock',lambda m:m['paperTwoCandleEntry'].update(sourceAt=NOW)),
            ('future-bar',lambda m:m['paperTwoCandleEntry'].update(barAt=NOW+300000)),
            ('old-bar',lambda m:m['paperTwoCandleEntry'].update(barAt=BAR-600000)),
            ('bad-bar-alignment',lambda m:m['paperTwoCandleEntry'].update(barAt=BAR+1)),
            ('old-market',lambda m:m.update(dataAt=NOW-61000)),
            ('stale-source',lambda m:m.update(priceFresh=False)),
            ('wrong-trend',lambda m:m['trendContext'].update(direction='LONG')),
            ('weak-trend',lambda m:m['trendContext'].update(intact=False)),
            ('15m-opposite',lambda m:m['dmi']['frames']['15m'].update(direction='LONG')),
            ('1h-unknown',lambda m:m['dmi']['frames']['1h'].update(available=False)),
            ('bad-plan',lambda m:m['paperTwoCandleEntry']['plan'].update(target=4001)),
            ('wrong-plan-price',lambda m:m['paperTwoCandleEntry']['plan'].update(entry=4004)),
            ('bad-unit',lambda m:m['paperTwoCandleEntry']['plan'].update(unit='EUR')),
            ('forged-live',lambda m:m['paperTwoCandleEntry'].update(realOrders=True)),
        ]
        for label,change in modifications:
            with self.subTest(label=label):
                m=copy.deepcopy(original)
                change(m)
                out=portfolio.two_candle_paper_market(m,NOW)
                self.assertEqual(out['direction'],'NEUTRAL')
                self.assertIsNone(out['plan'])
                self.assertIsNone(out['paperEntrySource'])
                self.assertIsNotNone(portfolio.entry_block_reason(
                    portfolio.POLICIES['early5m1000nov'],out))

if __name__=='__main__':
    unittest.main()
