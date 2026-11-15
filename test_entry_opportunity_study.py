import copy
import json
import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock
import entry_opportunity_study as s

NOW = int(datetime(2026,11,12,12,tzinfo=timezone.utc).timestamp()*1000)


def fixture(now=NOW, price=100., side='LONG', baseline=False):
    sign = 1 if side == 'LONG' else -1
    bundle = {'spots':dict(xaus=price,is_genuine_xauusd_spot=True,
        spot_price_as_of=datetime.fromtimestamp(now/1000,timezone.utc).isoformat())}
    plan = dict(direction=side,entry=price,stop=price-sign*2,target=price+sign*4)
    arms = {k:dict(allowed=k!='reference' or baseline,reason='eligible',plan=plan,
        gate={'barAt':now//300000*300000-300000}) for k in s.ARMS}
    trial = dict(version=s.VERSION,comparisonOnly=True,status='observed',direction=side,
        checkedAt=now,sourceAt=now,barAt=now//300000*300000-300000,arms=arms)
    market = dict(direction=side,ready=True,priceFresh=True,dataAt=now,price=price,
        session={'entryAllowed':True},entryOpportunityStudy=trial,plan=None)
    return bundle, market


class OpportunityTests(unittest.TestCase):
    def test_javascript_gates_and_math(self):
        subprocess.run(['node','test_entry_opportunity_study.js'],check=True,capture_output=True)

    def test_rejected_main_plan_does_not_suppress_alternative(self):
        b,m=fixture(); before=copy.deepcopy((b,m)); old=s.seed(NOW)
        state=s.advance(old,b,m,NOW)
        self.assertEqual(old['episodes'],0)
        self.assertEqual((b,m),before)
        self.assertEqual(state['episodes'],1)
        self.assertEqual(state['active']['arms']['reference']['status'],'skipped')
        self.assertEqual(state['active']['arms']['combined']['status'],'open')
        self.assertEqual(s.advance(state,b,m,NOW),state)

    def test_symmetric_actual_observed_stop_slippage_and_cost(self):
        for side,exit_price in [('LONG',97.),('SHORT',103.)]:
            b,m=fixture(side=side); state=s.advance(s.seed(NOW),b,m,NOW)
            b,m=fixture(NOW+30000,exit_price,side)
            state=s.advance(state,b,m,NOW+30000)
            a=state['arms']['combined']
            self.assertEqual(state['completedPairs'],1)
            self.assertAlmostEqual(a['pairedNetR'],-1.58)
            self.assertEqual(a['additionalEntries'],1)
            self.assertEqual(a['pairedLosses'],1)
            self.assertEqual(a['maxObservedAdverseR'],1.5)
            self.assertIsNone(state['active'])
            self.assertEqual(state['recent'][0]['arms']['combined']['exitPrice'],exit_price)

    def test_missing_path_excludes_whole_pair_and_never_becomes_zero(self):
        b,m=fixture(baseline=True); state=s.advance(s.seed(NOW),b,m,NOW)
        # One arm closed, the rest cannot be assigned a result across an outage.
        state['active']['arms']['reference'].update(status='closed',netR=1.,modelReturnPct=1.,
            maxAdverseR=0.,maxFavorableR=1.)
        b,m=fixture(NOW+91000,105.)
        state=s.advance(state,b,m,NOW+91000)
        self.assertEqual(state['inconclusivePairs'],1)
        self.assertEqual(state['completedPairs'],0)
        self.assertEqual(state['arms']['reference']['pairedNetR'],0)
        self.assertIsNone(state['recent'][0]['arms']['combined']['netR'])

    def test_malformed_naive_or_future_source_time_fails_closed(self):
        for label in (None, 1794500000000, [], {}, '2026-11-12 12:00:00',
                      'bad-clock', '2026-11-12T13:00:00+00:00'):
            with self.subTest(clock=label):
                bundle, market = fixture()
                bundle['spots']['spot_price_as_of'] = label
                self.assertIsNone(s.source(bundle, NOW))
                self.assertEqual(s.advance(s.seed(NOW),bundle,market,NOW)['episodes'],0)
        self.assertIsNone(s.source(None,NOW))
        self.assertIsNone(s.source({'spots':[]},NOW))
        self.assertIsNone(s.source({'spots':{}},float('nan')))
        bundle, _ = fixture()
        self.assertEqual(s.source(bundle,NOW),(100.,float(NOW)))

    def test_invalid_clocks_and_plans_cannot_enter(self):
        for edit in ('future','stale','mismatched','bad-stop','partial','session','no-direction'):
            b,m=fixture()
            t=m['entryOpportunityStudy']
            if edit=='future':t['checkedAt']=NOW+1
            if edit=='stale':t['checkedAt']=NOW-60001
            if edit=='mismatched':m['dataAt']=NOW-1
            if edit=='bad-stop':t['arms']['combined']['plan']['stop']=101.
            if edit=='partial':del t['arms']['minute']
            if edit=='session':m['session']['entryAllowed']=False
            if edit=='no-direction':t['direction']='NEUTRAL'
            self.assertEqual(s.advance(s.seed(NOW),b,m,NOW)['episodes'],0,edit)

    def test_same_five_minute_opportunity_cannot_reenter(self):
        b,m=fixture();state=s.advance(s.seed(NOW),b,m,NOW)
        b,m=fixture(NOW+30000,105);state=s.advance(state,b,m,NOW+30000)
        b,m=fixture(NOW+60000,105);state=s.advance(state,b,m,NOW+60000)
        self.assertEqual(state['episodes'],1)

    def test_stale_quote_cannot_extend_observation_clock(self):
        b,m=fixture();state=s.advance(s.seed(NOW),b,m,NOW)
        state=s.advance(state,b,m,NOW+60000)
        self.assertEqual(state['active']['arms']['combined']['lastObservedAt'],NOW)
        state=s.advance(state,b,m,NOW+91000)
        self.assertEqual(state['inconclusivePairs'],1)

    def test_fixed_risk_exposure_cap(self):
        b,m=fixture();state=s.advance(s.seed(NOW),b,m,NOW)
        b,m=fixture(NOW+30000,104);state=s.advance(state,b,m,NOW+30000)
        self.assertAlmostEqual(state['arms']['combined']['pairedModelReturnPct'],1.92)

    def test_persistence_and_read_only_report(self):
        c=MagicMock();c.execute.return_value.fetchone.return_value=None
        b,m=fixture();s.tick(c,b,m,NOW)
        writes=[x for x in c.execute.call_args_list if x.args[0].startswith('INSERT')]
        self.assertEqual(len(writes),1)
        saved=json.loads(writes[0].args[1][1])
        self.assertEqual(saved['episodes'],1)
        c.reset_mock();c.execute.return_value.fetchone.return_value=(saved,)
        report=s.report(c)
        self.assertFalse(report['strategyWinnerConfirmed'])
        self.assertFalse(report['productReturnVerified'])
        self.assertTrue(all(x.args[0].startswith('SELECT') for x in c.execute.call_args_list))

    def test_engine_and_worker_wiring(self):
        from pathlib import Path
        self.assertIn('Opportunity.evaluate',Path('background_analysis.js').read_text())
        self.assertIn("__import__('entry_opportunity_study').tick",Path('paper_simulation.py').read_text())
        self.assertIn("__import__('entry_opportunity_study').report",Path('bob_diagnostics.py').read_text())


if __name__ == '__main__':
    unittest.main()
