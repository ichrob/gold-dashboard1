"""Paired prospective campaign: warning isolation, expiry, durable seed and stop."""
import copy
import json
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import paper_portfolios as profiles
import paper_simulation as sim
from test_bob_stop_reentry import MemoryLedger
from test_trend_follow import market, quote, ISIN

END=profiles.CAMPAIGN_END

class CampaignTests(unittest.TestCase):
    def test_end_and_identical_risk(self):
        self.assertEqual(END,datetime(2026,10,30,15,tzinfo=timezone.utc).timestamp()*1000)
        a,b=(profiles.POLICIES[n] for n in ('early1000oct','normal1000oct'))
        for field in ('initial_capital_eur','exposure_fraction','daily_loss_fraction','campaign_end','require_trend'):
            self.assertEqual(a[field],b[field])
        self.assertEqual(a['initial_capital_eur'],1000.)
        self.assertNotEqual(profiles.names(a['id']),profiles.names(b['id']))

    def test_warning_both_sides_expiry_and_main_unchanged(self):
        now=END-600000
        for side in ('LONG','SHORT'):
            m=market(at=now)
            m.update(direction='NEUTRAL',earlyWarning=dict(version='early-warning-v2',available=True,
                state='watch',direction=side,signalBarAt=now-300000,expiresAt=now+600000,
                comparisonOnly=True,affectsApproval=False,extensionRisk=False),
                warningPaperPlan=dict(kind='candidate',direction=side,entry=4000.,
                    stop=3980. if side=='LONG' else 4020.,target=4040. if side=='LONG' else 3960.,unit='USD/oz'))
            original=copy.deepcopy(m)
            out=profiles.warning_paper_market(m,now)
            self.assertEqual(out['direction'],side)
            self.assertEqual(out['analysisBarAt'],now-300000)
            self.assertEqual(m,original)
            self.assertIsNone(profiles.entry_block_reason(profiles.POLICIES['early1000oct'],out))
            for update in ({'state':'withdrawn'},{'expiresAt':now},{'extensionRisk':True},{'affectsApproval':True}):
                bad={**m,'earlyWarning':{**m['earlyWarning'],**update}}
                self.assertIsNone(profiles.warning_paper_market(bad,now)['plan'])
            self.assertIsNone(profiles.warning_paper_market({**m,'warningPaperPlan':None},now)['plan'])

    def ledger(self):
        ledger=MemoryLedger()
        ledger.control.update(startAt=END-3600000,initialCapital=1000.,cash=1000.,equity=1000.)
        return ledger

    def test_warning_plan_rejection_reaches_ledger_without_main_signal_requirement(self):
        now=END-600000
        m=market(at=now)
        m.update(direction='NEUTRAL', warningPaperPlan=None,
            warningPaperPlanReason='Unterstützung vor dem Ziel: Mindest-CRV nicht erfüllt',
            earlyWarning=dict(version='early-warning-v2',available=True,state='active',
                direction='SHORT',signalBarAt=now-300000,expiresAt=now+300000,
                comparisonOnly=True,affectsApproval=False,extensionRisk=False))
        original=copy.deepcopy(m)
        for expired in (False,True):
            source=copy.deepcopy(m)
            if expired:source['earlyWarning']['expiresAt']=now
            out=profiles.warning_paper_market(source,now)
            ledger=self.ledger()
            with patch('paper_simulation.new_case') as enter:
                sim.run_once(ledger,{},out,{'choices':[]},{},now,profiles.POLICIES['early1000oct'])
                enter.assert_not_called()
            self.assertIn('Frühwarn-Test:',ledger.control['reason'])
            if expired:
                self.assertIn('Keine aktuelle gültige Frühwarnung',ledger.control['reason'])
                self.assertNotIn('Mindest-CRV',ledger.control['reason'])
            else:self.assertIn(m['warningPaperPlanReason'],ledger.control['reason'])
            self.assertEqual(ledger.control['cash'],1000.)
        self.assertEqual(m,original)

    def test_no_entry_at_or_after_deadline(self):
        for profile in ('early1000oct','normal1000oct'):
            ledger=self.ledger()
            for now in (END,END+30000):
                with patch('paper_simulation.new_case') as enter:
                    sim.run_once(ledger,{},market(at=now),{'choices':[{'isin':ISIN}]},{ISIN:quote(now)},now,profiles.POLICIES[profile])
                    enter.assert_not_called()
                self.assertEqual(ledger.control['status'],'completed')
                self.assertEqual(ledger.control['cash'],1000.)

    def test_existing_position_time_exit_and_missing_bid_remains_pending(self):
        for missing in (False,True):
            now=END-30000
            m=market(at=now)
            c=sim.new_case(m,{'isin':ISIN},quote(now),now,cash=650.)
            ledger=self.ledger();ledger.active=c;ledger.control['cash']-=c['allocated']
            q=None if missing else quote(END)
            sim.run_once(ledger,{},market(at=END),{'choices':[]},{ISIN:q},END,profiles.POLICIES['normal1000oct'])
            self.assertEqual(ledger.control['status'],'ending-pending-quotes' if missing else 'completed')
            if missing:
                self.assertGreater(ledger.active['pendingUnits'],0)
                self.assertFalse(ledger.active['productReturnKnown'])
            else:
                self.assertIsNone(ledger.active)
                self.assertEqual(ledger.completed[0]['exitReason'],'time-exit')
                self.assertEqual(ledger.completed[0]['endsAt'],END)

class ComparisonTests(unittest.TestCase):
    def accounts(self):
        return [dict(profile=p,control=dict(status='completed',totalProfit=n,initialCapital=1000.),
            performance=dict(closedTrades=2,pricedTrades=2,inconclusiveTrades=0))
            for p,n in [('early1000oct',20.),('normal1000oct',10.)]]

    def test_completed_difference_and_gap_suppression(self):
        accounts=self.accounts()
        result=profiles.campaign_comparison(accounts)
        self.assertEqual(result['differenceEarlyMinusMainEur'],10.)
        self.assertFalse(result['strategyWinnerConfirmed'])
        for field,value in [('inconclusiveTrades',1),('pricedTrades',0),('pricedTrades',None)]:
            bad=copy.deepcopy(accounts);bad[0]['performance'][field]=value
            self.assertIsNone(profiles.campaign_comparison(bad)['differenceEarlyMinusMainEur'])
        for status in ['running','ending-pending-quotes']:
            bad=copy.deepcopy(accounts);bad[0]['control']['status']=status
            self.assertIsNone(profiles.campaign_comparison(bad)['differenceEarlyMinusMainEur'])
        self.assertIsNone(profiles.campaign_comparison([])['differenceEarlyMinusMainEur'])

    def test_terminal_status_survives_night_report(self):
        from unittest.mock import MagicMock
        for status in ('completed','ending-pending-quotes'):
            db=MagicMock()
            # Control query returns a one-column row.
            db.execute.return_value.fetchone.side_effect=[({'status':status,'enabled':True,'startAt':1},),None,None]
            db.execute.return_value.fetchall.return_value=[]
            with patch('paper_simulation.background_push.degiro_session',return_value='night'), patch('paper_simulation.paper_case_review.legacy_exclusions',return_value={}):
                self.assertEqual(sim.report(db)['control']['status'],status)

if __name__=='__main__':unittest.main()
