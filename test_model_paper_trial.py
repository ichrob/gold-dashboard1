"""Model-only 800/1000 forward PAPER execution is separate from original ledgers."""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import model_paper_trial as trial

NOW = int(datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc).timestamp()*1000)
def stamp(at):
    return datetime.fromtimestamp(at/1000,timezone.utc).isoformat()


def fixture(side='LONG', profile='trend800nov', now=NOW):
    sign=1 if side=='LONG' else -1
    entry,stop,target=4200.,4200.-30*sign,4200.+60*sign
    ko=3900. if side=='LONG' else 4500.
    original=stamp(now-10000)
    model_at=stamp(now-180000)
    plan=dict(kind='candidate',direction=side,entry=entry,stop=stop,target=target,
              unit='USD/oz',entrySuitable=True)
    market=dict(ready=True,priceFresh=True,price=entry,direction=side,
        session=dict(entryAllowed=True),entryPlanState=dict(state='ready',code='PAPER_PLAN_READY'),
        ruleVersion='intraday-trend-follow-v7',analysisBarAt=now-300000,
        paperCampaignEntries={profile:dict(
            paperOnly=True,plan=plan,gate=dict(allowed=True))})
    row=dict(isin='DE000FG14AV8',direction=side,available=False,
        modelMode='anchored-estimate',planState='model-only-reference',
        simulationPlanningUsable=True,simulationFillAllowed=False,
        modelCurrency='EUR',modelEntry=20.1,modelStop=17.3,modelTarget=25.4,
        modelGoldEntry=entry,modelGoldStop=stop,modelGoldTarget=target,
        modelKo=ko,modelStrike=ko,modelRatio=.1,modelFxRate=.9,
        modelInputAgeSeconds=10,modelAnchorAgeSeconds=180,
        modelOriginalGoldAt=original,modelFxAt=original,modelReferenceAt=model_at)
    bundle=dict(spots=dict(xaus=entry,is_genuine_xauusd_spot=True,
        spot_price_as_of=original,usd_eur_meta=dict(rate=.9,fetchedAt=original)))
    audit=dict(current=True,items=[row])
    return market,bundle,audit


class ModelPaperTrials(unittest.TestCase):
    def test_two_separate_prospective_accounts(self):
        for profile, initial in trial.PROFILES.items():
            s=trial.new_control(profile,NOW)
            self.assertEqual(s['initialCapitalEur'],initial)
            self.assertEqual(s['cashEur'],initial)
            self.assertFalse(s['originalTradesAltered'])
            self.assertEqual(s['brokerFills'],0)
            self.assertFalse(s['realOrders'])

    def test_first_model_entry_is_risk_capped_and_not_observed(self):
        for profile in trial.PROFILES:
            market,bundle,audit=fixture(profile=profile)
            c=trial.new_control(profile,NOW-60000)
            original=copy.deepcopy(c)
            out=trial.evolve(c,market,bundle,audit,NOW)
            self.assertEqual(c,original,'pure function must not mutate original ledger')
            self.assertEqual(out['status'],'model-position-open')
            pos=out['active']
            self.assertTrue(pos['modelOnly'])
            self.assertFalse(pos['brokerFillVerified'])
            self.assertFalse(pos['productNetVerified'])
            self.assertLessEqual(pos['costEur'],trial.PROFILES[profile]*trial.ENTRY_EXPOSURE)
            self.assertGreaterEqual(out['cashEur'],trial.PROFILES[profile]*(1-trial.ENTRY_EXPOSURE))
            self.assertLessEqual(pos['quantity']*(pos['entryModelEur']-17.3)+
                2*trial.FEE_EUR,trial.PROFILES[profile]*.01+.2)
            self.assertEqual(out['realizedModelProfitEur'],0)

    def test_close_uses_original_new_spot_but_remains_model_only(self):
        m,b,a=fixture()
        c=trial.evolve(trial.new_control('trend800nov',NOW),m,b,a,NOW)
        self.assertTrue(c['active'])
        newer=NOW+120000
        m['price']=4265
        b['spots']['xaus']=4265
        b['spots']['spot_price_as_of']=stamp(newer-10000)
        b['spots']['usd_eur_meta']['fetchedAt']=stamp(newer-10000)
        done=trial.evolve(c,m,b,a,newer)
        self.assertIsNone(done['active'])
        self.assertEqual(done['completed'],1)
        self.assertEqual(done['recent'][0]['status'],'model-target')
        self.assertFalse(done['recent'][0]['brokerFillVerified'])
        self.assertFalse(done['recent'][0]['productNetVerified'])
        self.assertGreater(done['realizedModelProfitEur'],0)
        self.assertEqual(done['brokerFills'],0)
        self.assertFalse(done['realOrders'])
        later=trial.evolve(done,m,b,a,newer)
        self.assertIsNone(later['active'],'cannot re-enter from same confirmed signal')

    def test_unobserved_market_does_not_invent_exit(self):
        m,b,a=fixture()
        c=trial.evolve(trial.new_control('trend800nov',NOW),m,b,a,NOW)
        m['priceFresh']=False
        lost=trial.evolve(c,m,b,a,NOW+120000)
        self.assertEqual(lost['status'],'valuation-pending')
        self.assertEqual(lost['active'],c['active'])
        self.assertEqual(lost['completed'],0)
        self.assertIsNone(lost['modelEquityEur'])

    def test_ko_crossed_worst_case_still_only_model_loss(self):
        m,b,a=fixture()
        c=trial.evolve(trial.new_control('trend800nov',NOW),m,b,a,NOW)
        now=NOW+120000;m['price']=3890;b['spots']['xaus']=3890
        b['spots']['spot_price_as_of']=stamp(now-10000)
        b['spots']['usd_eur_meta']['fetchedAt']=stamp(now-10000)
        end=trial.evolve(c,m,b,a,now)
        self.assertEqual(end['recent'][0]['status'],'model-ko')
        self.assertLess(end['realizedModelProfitEur'],0)
        self.assertEqual(end['recent'][0]['modelExitEur'],0)

    def test_no_model_trades_when_any_required_proof_fails(self):
        for which in ('intrinsic','expired','no-audit','stale-spot','future-fx',
                      'weak-gate','poor-target','wrong-direction','session-closed',
                      'bad-ko','no-plan','bad-origin','unconfirmed-source'):
            m,b,a=fixture()
            if which=='intrinsic':a['items'][0]['modelMode']='intrinsic-only'
            if which=='expired':a['items'][0]['modelAnchorAgeSeconds']=301
            if which=='no-audit':a['current']=False
            if which=='stale-spot':b['spots']['spot_price_as_of']=stamp(NOW-61000)
            if which=='future-fx':b['spots']['usd_eur_meta']['fetchedAt']=stamp(NOW+1000)
            if which=='weak-gate':m['paperCampaignEntries']['trend800nov']['gate']['allowed']=False
            if which=='poor-target':
                a['items'][0]['modelGoldTarget']=4220.
            if which=='wrong-direction':a['items'][0]['direction']='SHORT'
            if which=='session-closed':m['session']['entryAllowed']=False
            if which=='bad-ko':a['items'][0]['modelKo']=4180.
            if which=='no-plan':m['paperCampaignEntries']['trend800nov']['plan']=None
            if which=='bad-origin':a['items'][0]['modelOriginalGoldAt']=stamp(NOW-61000)
            if which=='unconfirmed-source':m['ready']=False
            out=trial.evolve(trial.new_control('trend800nov',NOW),m,b,a,NOW)
            self.assertIsNone(out['active'],which)
            self.assertEqual(out['cashEur'],800.0,which)
            self.assertEqual(out['completed'],0,which)

    def test_stop_target_independence_and_long_short(self):
        for side in ('LONG','SHORT'):
            m,b,a=fixture(side=side)
            c=trial.evolve(trial.new_control('trend800nov',NOW),m,b,a,NOW)
            self.assertTrue(c['active'],side)
            s=c['active']
            self.assertTrue((s['goldStop']<s['goldEntry']<s['goldTarget']) if side=='LONG'
                else (s['goldTarget']<s['goldEntry']<s['goldStop']))
            self.assertFalse(s['observedProductFill'])


if __name__=='__main__':
    unittest.main()
