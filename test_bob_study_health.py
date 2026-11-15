"""Offline safety and idempotence checks for Bob's research→watchdog→AI routing."""
import copy
import unittest
from unittest.mock import patch

import bob_ai_coordination as coordinator
import bob_issue_watchdog as watchdog
import bob_study_health as study_health
import research_restart
from test_research_restart import sample, NOW as STUDY_NOW

NOW = 1794350000000


def control(checks=(), outcomes=(), checked=None, status='collecting'):
    return dict(status=status, checkedAt=NOW-1000 if checked is None else checked,
                quality=dict(cycles=18696, invalid=713,
                             recentOriginalChecks=list(checks),
                             recentOriginalOutcomes=list(outcomes)))


class PublicStudyHealthTests(unittest.TestCase):
    def test_old_cumulative_invalid_does_not_open_new_incident(self):
        report=study_health.snapshot(control(),NOW,trading=True)
        self.assertEqual(report['status'],'observed')
        self.assertEqual(report['codes'],[])
        self.assertNotIn('quality', report)
        self.assertNotIn('18696',str(report))
        self.assertFalse(report['realOrders'])

    def test_recent_persistent_original_faults_raise_allowlisted_code(self):
        checks=[dict(at=NOW-(19-i)*30000,valid=i%2==0) for i in range(20)]
        report=study_health.snapshot(control(checks),NOW,trading=True)
        self.assertEqual(report['codes'],[study_health.INPUT_CODE])
        self.assertEqual(report['scope'],study_health.SCOPE)

    def test_one_bad_tick_or_old_bad_ticks_never_raise_new_issue(self):
        checks=[dict(at=NOW-(19-i)*30000,valid=i != 18) for i in range(20)]
        self.assertEqual(study_health.snapshot(control(checks),NOW,trading=True)['codes'],[])
        old=[dict(at=NOW-25*60000,valid=False)]*20
        self.assertEqual(study_health.snapshot(control(old),NOW,trading=True)['codes'],[])

    def test_new_policy_original_failures_only_after_sufficient_closures(self):
        outcomes=[dict(at=NOW-(5-i)*60000,study='entry-delay',
                       complete=i==5) for i in range(6)]
        report=study_health.snapshot(control(outcomes=outcomes),NOW,trading=True)
        self.assertEqual(report['codes'],[study_health.OUTCOME_CODE])
        too_old=[dict(at=NOW-5*3600000,study='entry-delay',complete=False)]*8
        self.assertEqual(study_health.snapshot(control(outcomes=too_old),NOW,trading=True)['codes'],[])

    def test_paused_unknown_stale_and_inactive_are_not_healthy(self):
        self.assertEqual(study_health.snapshot(control(checked=NOW-360000),NOW,trading=False)['status'],'paused')
        self.assertEqual(study_health.snapshot(None,NOW,trading=True)['status'],'unavailable')
        report=study_health.snapshot(control(checked=NOW-360000),NOW,trading=True)
        self.assertEqual(report['status'],'stale')
        self.assertEqual(report['codes'],[study_health.WORKER_CODE])
        self.assertEqual(study_health.snapshot(control(status='completed'),NOW,trading=True)['codes'],[])

    def test_truncated_untrusted_events_fail_closed_not_to_fake_alerts(self):
        oversized=[dict(at=NOW,valid=False)]*1000
        self.assertEqual(study_health.snapshot(control(oversized),NOW,trading=True)['codes'],[])
        invalid=[dict(at=NOW,valid='False')]*30
        self.assertEqual(study_health.snapshot(control(invalid),NOW,trading=True)['codes'],[])


class WatchdogRoutingTests(unittest.TestCase):
    def test_public_health_routes_only_fixed_codes_when_trading(self):
        base=dict(status='ok',automaticCollection=dict(enabled=True,running=True))
        push=dict(ok=True,productAuditCodes=[],paperObservation=dict(state='ok'),
                  studyHealth=study_health.snapshot(control(
                      [dict(at=NOW-i*30000,valid=i%2==0) for i in range(20)]
                  ),NOW,trading=True))
        valid=watchdog.classify(base,dict(status='ok'),push,market_open=True)
        self.assertIn(study_health.INPUT_CODE,valid)
        self.assertNotIn(study_health.INPUT_CODE,watchdog.classify(
            base,dict(status='ok'),push,market_open=False))
        fake=copy.deepcopy(push)
        fake['studyHealth']['codes']=['trade-now','study-original-input-degraded','withdraw']
        self.assertNotIn(study_health.INPUT_CODE,watchdog.classify(
            base,dict(status='ok'),fake,market_open=True))
        fake=copy.deepcopy(push);fake['studyHealth']['scope']='untrusted'
        self.assertNotIn(study_health.INPUT_CODE,watchdog.classify(
            base,dict(status='ok'),fake,market_open=True))

    def test_study_incident_cannot_close_from_missing_diagnostic(self):
        code=study_health.INPUT_CODE
        title=watchdog.issue_title(code)
        writes=[]
        def requester(method,path,*,token,repo,data=None):
            writes.append((method,path,data))
            return {}
        with patch.object(watchdog,'open_issue_index',return_value=({title:1550},[])):
            outcome=watchdog.sync_issue([],token='test',repo='ichrob/gold-dashboard1',
                                         recovery_codes={code},requester=requester)
        self.assertNotIn(('PATCH','/issues/1550',{'state':'closed'}),writes)
        self.assertFalse(any(m=='PATCH' for m,p,data in writes))
        self.assertEqual(outcome,'already-open')

    def test_existing_repair_coordinator_accepts_study_case_once(self):
        code=study_health.INPUT_CODE
        row=dict(title=watchdog.issue_title(code),number=1550,state='open',
                 user=dict(login='github-actions[bot]'))
        self.assertEqual(coordinator.verified_cases([row]),[(1550,code)])
        handoff=coordinator.handoff(code,1550)
        self.assertIn('BOB-1550-'+code,handoff)
        self.assertIn('nicht überprüft',handoff)
        self.assertNotIn('GEMINI_API_KEY',handoff)


class ProspectiveStateEvidenceTests(unittest.TestCase):
    def test_forward_only_original_quality_and_terminal_events(self):
        b,m=sample()
        state,_=research_restart.advance(research_restart.seed(STUDY_NOW),b,m,STUDY_NOW)
        self.assertEqual(state['quality']['recentOriginalChecks'][-1],
                         dict(at=STUDY_NOW,valid=True))
        b,m=sample(STUDY_NOW+30000)
        b['spots']['is_genuine_xauusd_spot']=False
        state,_=research_restart.advance(state,b,m,STUDY_NOW+30000)
        self.assertEqual(state['quality']['recentOriginalChecks'][-1],
                         dict(at=STUDY_NOW+30000,valid=False))
        completed=[]
        for delta in range(60000,3600001,30000):
            b,m=sample(STUDY_NOW+delta,4000.+delta/180000)
            state,closed=research_restart.advance(state,b,m,STUDY_NOW+delta)
            completed.extend(closed)
        self.assertEqual(len(completed),3)
        self.assertTrue(all(x['status']=='complete' for x in completed))
        self.assertEqual(len(state['quality']['recentOriginalOutcomes']),3)
        self.assertEqual({e['study'] for e in state['quality']['recentOriginalOutcomes']},
                         set(research_restart.STUDIES))
        self.assertTrue(all(e['complete'] for e in state['quality']['recentOriginalOutcomes']))
        self.assertEqual(state['quality']['invalid'],1)
        self.assertLessEqual(len(state['quality']['recentOriginalChecks']),64)


if __name__=='__main__':
    unittest.main()
