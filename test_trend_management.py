import unittest
import background_push
import paper_simulation as sim
from test_paper_simulation import case,tick,quote,NOW
class TrendManagement(unittest.TestCase):
    def test_pullback_does_not_force_paper_exit_but_stop_does(self):
        for side,price,stop_price in [('LONG',111,89),('SHORT',89,111)]:
            other='SHORT' if side=='LONG' else 'LONG'
            trend=dict(available=True,intact=True,direction=side,phase='PULLBACK')
            c=sim.advance_case(case(side),tick(price,direction=other,trendContext=trend),quote(NOW+30000),NOW+30000)
            self.assertEqual(c['status'],'open')
            self.assertNotIn('profit-taking',[e['kind'] for e in c['events']])
            c=sim.advance_case(c,tick(stop_price,60,direction=other,trendContext=trend),quote(NOW+60000),NOW+60000)
            self.assertEqual(c['exitReason'],'stop')
    def test_stop_never_loosened(self):
        for side,price,candidate in [('LONG',111,80),('SHORT',89,120)]:
            c=case(side);old=c['engine']['trade']['stop']
            c=sim.advance_case(c,tick(price,direction=side,suggestedStop=candidate,trendContext=dict(available=True,intact=True,direction=side,phase='PULLBACK')),quote(NOW+30000),NOW+30000)
            new=c['engine']['trade']['stop']
            self.assertTrue(new>=old if side=='LONG' else new<=old)
    def test_target_keeps_runner_with_intact_trend(self):
        c=sim.advance_case(case(),tick(120,direction='NEUTRAL',trendContext=dict(available=True,intact=True,direction='LONG',phase='PULLBACK')),quote(NOW+30000),NOW+30000)
        self.assertEqual(c['status'],'open');self.assertTrue(c['partialTaken'])
    def test_comparison_uses_frozen_baseline(self):
        import intraday_comparison as cmp
        now=cmp.START+60000
        m=dict(ready=True,priceFresh=True,price=4200,dataAt=now,analysisBarAt=now-360000,ruleVersion='intraday-trend-follow-v7',direction='NEUTRAL',shadowDirection='NEUTRAL',comparisonBaseline=dict(ruleVersion=cmp.POLICY,direction='LONG',shadowDirection='SHORT',decisionReason='frozen'))
        r=cmp.observation(m,now);self.assertTrue(r['valid']);self.assertEqual(r['fast'],'LONG');self.assertEqual(r['cautious'],'SHORT')

    def test_audit_retains_legacy_identity_and_new_context(self):
        import decision_audit as audit
        for version in ('intraday-responsive-v6','intraday-trend-follow-v7'):
            _,row=audit.normalize(dict(ruleVersion=version,direction='NEUTRAL',barAt=NOW,trendContext=dict(version='sustained-trend-v1',intact=True,direction='LONG')),now=NOW)
            self.assertEqual(row['ruleVersion'],version)
            self.assertEqual(row['trendContext']['direction'],'LONG')
