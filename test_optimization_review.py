import copy
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
import decision_audit as audit
import optimization_review as review
import paper_costs
import stop_target_audit


class ForwardTests(unittest.TestCase):
    def row(self, direction='NEUTRAL', move=1., at=None, regime='CONTINUATION'):
        at = at or datetime(2026,10,16,10,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000
        payload=dict(ruleVersion=audit.RULE_VERSION, origin='background', direction=direction,
            shadowDirection='NEUTRAL', barAt=at-300000, price=100,priceAt=at,
            trendContext=dict(available=True,phase=regime,intact=True,direction='LONG'),
            earlyImpulse=dict(version='early-impulse-v1',available=True,barAt=at-300000,
                direction='LONG',comparisonOnly=True,affectsApproval=False),
            reason='Bestätigung fehlt',gateReasons=[])
        r=audit.normalize(payload,at)[1]
        return r,({'price':100+move,'at':at+900000},None,None)

    def test_frozen_forward_comparison_does_not_change_decision(self):
        row=self.row(); before=copy.deepcopy(row)
        result=review.report([row],audit.outcome,now=row[0]['recordedAt']+1000000)
        self.assertEqual(row,before)
        self.assertEqual(result['paired'],1)
        self.assertEqual(result['missedCount'],1)
        m=result['phases']['collection']
        self.assertEqual(m['baseline']['signals'],0)
        self.assertAlmostEqual(m['early']['meanModelPct'],.96)
        self.assertEqual(m['regime']['signals'],1)
        self.assertFalse(result['automaticRuleChange'])
        self.assertIsNone(m['baseline']['losingSignalRate'])
        self.assertEqual(m['early']['losingSignalRate'],0)
        self.assertAlmostEqual(m['early']['netModelDeltaVsBaselinePct'],.96)

    def test_legacy_browser_unavailable_and_future_not_success(self):
        row=self.row(); old=copy.deepcopy(row);old[0].pop('optimization')
        browser=copy.deepcopy(row);browser[0]['origin']='browser'
        self.assertEqual(review.report([old,browser],audit.outcome)['sampled'],0)
        for bad in (None,{'price':101,'at':row[0]['recordedAt']+899999},
                    {'price':101,'at':row[0]['recordedAt']+960001}):
            r=review.report([(row[0],(bad,None,None))],audit.outcome,now=row[0]['recordedAt']+1000000)
            self.assertEqual(r['paired'],0);self.assertEqual(r['missing'],1)
        row[0]['optimization']['variants']['regime']=None
        self.assertEqual(review.report([row],audit.outcome)['paired'],0)

    def test_sample_before_outcome_and_validation_separate(self):
        a=self.row();b=self.row(at=a[0]['recordedAt']+300000)
        validation=self.row(at=datetime(2026,10,26,8,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        r=review.report([(a[0],(None,None,None)),b,validation],audit.outcome,now=validation[0]['recordedAt']+1000000)
        self.assertEqual(r['sampled'],2);self.assertEqual(r['paired'],1)
        self.assertEqual(r['phases']['collection']['early']['cases'],0)
        self.assertEqual(r['phases']['validation']['early']['cases'],1)

    def test_range_waits_and_signal_delay_means_logged_evidence_only(self):
        a=self.row(regime='RANGE');b=self.row(direction='LONG',at=a[0]['recordedAt']+300000)
        r=review.report([a,b],audit.outcome,now=a[0]['recordedAt']+1000000)
        self.assertEqual(r['phases']['collection']['regime']['wait'],1)
        self.assertEqual(r['missed'][0]['laterSignalMinutes'],5)
        self.assertEqual(r['missed'][0]['reason'],'Bestätigung fehlt')

    def test_short_and_product_blocker_not_mislabeled_late_signal(self):
        a=self.row(direction='SHORT',move=-1)
        a[0]['optimization']['blockers']=['Produktnachweis fehlt']
        r=review.report([a],audit.outcome,now=a[0]['recordedAt']+1000000)
        self.assertAlmostEqual(r['phases']['collection']['baseline']['meanModelPct'],.96)
        self.assertTrue(r['missed'][0]['signalAlreadyPresent'])
        self.assertEqual(r['missed'][0]['direction'],'SHORT')


class CostTests(unittest.TestCase):
    def case(self):
        return dict(status='closed',productReturnKnown=True,pendingUnits=0,remainingUnits=0,
            allocated=100.,cashReleased=110.,quantity=10,startedAt=0,closedAt=86400000,
            events=[dict(kind='partial-profit',units=4,quote=dict(bid=10.)),
                    dict(kind='stop',units=6,quote=dict(bid=70/6))])

    def test_spread_not_deducted_twice_partial_orders_counted(self):
        c=self.case();c['entrySpreadEur']=5;before=copy.deepcopy(c)
        a=dict(feeEurPerOrder=1.,slippageBpsPerSide=10.,extraHoldingBpsPerDay=5.)
        r=paper_costs.evaluate(c,a)
        self.assertEqual(c,before);self.assertEqual(r['orders'],3)
        self.assertAlmostEqual(r['modelNetEur'],10-3-.21-.05)

    def test_open_unknown_deferred_and_demo_excluded(self):
        for patch in (dict(status='open'),dict(pendingUnits=1),dict(productReturnKnown=False),
                      dict(demonstration=True),dict(events=[]),dict(closedAt=-1)):
            r=paper_costs.report([{**self.case(),**patch}])
            self.assertIsNone(r['scenarios'][0]['modelNetEur'])
            self.assertEqual(r['scenarios'][0]['excluded'],1)
        with self.assertRaises(ValueError):
            paper_costs.evaluate(self.case(),dict(feeEurPerOrder=-1,slippageBpsPerSide=0,extraHoldingBpsPerDay=0))

    def test_costs_can_turn_gross_profit_into_loss(self):
        c=self.case();c['cashReleased']=102.
        report=paper_costs.report([c])
        for scenario in report['scenarios']:
            self.assertEqual(scenario['grossEur'],2.)
            self.assertLess(scenario['modelNetEur'],0)
        self.assertLess(report['scenarios'][1]['modelNetEur'],report['scenarios'][0]['modelNetEur'])
        self.assertFalse(report['netReturnKnown'])

    def test_no_cases_not_zero_profit(self):
        self.assertIsNone(paper_costs.report([])['scenarios'][0]['modelNetEur'])

    def test_exit_comparison_same_valid_pairs_only(self):
        v=dict(complete=True,status='observed-stop',firstObserved='stop',directionalR=.5,maxFavorableR=2.)
        pair=dict(lifecycle=dict(fixed={**v,'directionalR':-1},trailing=v))
        missing=dict(lifecycle=dict(fixed=v,trailing={**v,'status':'inconclusive'}))
        r=stop_target_audit.exit_comparison([pair,missing])
        self.assertEqual(r['paired'],1);self.assertEqual(r['excluded'],1)
        self.assertEqual(r['variants']['trailing']['meanGivebackR'],1.5)


if __name__=='__main__':unittest.main()
