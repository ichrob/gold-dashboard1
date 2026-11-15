import copy
import unittest
import background_push as b

NOW = 1794470400000


def market(direction='LONG', now=NOW, allowed=False):
    return dict(ready=True,priceFresh=True,direction=direction,baseDirection=direction,
        price=4000.,dataAt=now,analysisBarAt=now//300000*300000-300000,mtf=direction,
        session={'entryAllowed':True},entryTimingGate={'allowed':allowed,'reason':'EMA-Abstand'},
        entryPlanState={'state':'ready' if allowed else 'waiting','reason':'EMA-Abstand'})


class ScenarioTests(unittest.TestCase):
    def run_tick(self,state,m,now=NOW):
        return b.advance(state,b.config({}),m,True,False,now=now,log=False)

    def kinds(self,events):
        return [e['data']['eventKind'] for e in events]

    def test_blocked_entry_still_reports_confirmed_scenario_both_sides(self):
        for side in ('LONG','SHORT'):
            m=market(side);before=copy.deepcopy(m)
            state,events=self.run_tick({},m)
            self.assertEqual(events,[])
            state,events=self.run_tick(state,market(side,NOW+30000),NOW+30000)
            self.assertEqual(self.kinds(events),['market-scenario'])
            self.assertEqual(events[0]['data']['direction'],side)
            self.assertIn('Einstieg noch gesperrt',events[0]['body'])
            self.assertFalse(events[0]['data']['affectsApproval'])
            self.assertEqual(m,before)
            for i in range(2,7):
                state,events=self.run_tick(state,market(side,NOW+i*30000),NOW+i*30000)
                self.assertEqual(events,[])

    def test_scenario_can_progress_to_entry_without_repeated_scenario(self):
        state,_=self.run_tick({},market())
        state,_=self.run_tick(state,market(now=NOW+30000),NOW+30000)
        state,e=self.run_tick(state,market(now=NOW+60000,allowed=True),NOW+60000)
        self.assertEqual(e,[])
        state,e=self.run_tick(state,market(now=NOW+90000,allowed=True),NOW+90000)
        self.assertEqual(self.kinds(e),['signal-change'])
        state,e=self.run_tick(state,market(now=NOW+120000),NOW+120000)
        self.assertEqual(e,[])

    def test_new_same_direction_after_stable_neutral_phase_is_not_suppressed(self):
        state={}
        for side,t in [('LONG',0),('LONG',30000),('NEUTRAL',60000),('NEUTRAL',90000),('LONG',120000),('LONG',150000)]:
            state,e=self.run_tick(state,market(side,NOW+t,True),NOW+t)
        self.assertEqual(self.kinds(e),['signal-change'])

    def test_no_rearm_for_outage_night_or_learning_veto(self):
        for reason in ('outage','night','learning'):
            state={'notifiedDirection':'LONG','scenarioNotified':'LONG'}
            for t in (0,30000):
                m=market('NEUTRAL',NOW+t,True)
                if reason=='outage':m['priceFresh']=False
                if reason=='night':m['session']['entryAllowed']=False
                if reason=='learning':m['baseDirection']='LONG'
                state,_=self.run_tick(state,m,NOW+t)
            self.assertEqual(state['notifiedDirection'],'LONG',reason)

    def test_no_scenario_for_warning_only_stale_source_or_night(self):
        for reason in ('neutral','stale','night','unchanged-source'):
            state={}
            for t in (0,30000):
                m=market(now=NOW+t)
                if reason=='neutral':m['direction']='NEUTRAL'
                if reason=='stale':m['dataAt']=NOW-90000
                if reason=='night':m['session']['entryAllowed']=False
                if reason=='unchanged-source':m['dataAt']=NOW
                state,e=self.run_tick(state,m,NOW+t)
                self.assertNotIn('market-scenario',self.kinds(e),reason)

    def test_invalid_target_plan_is_not_called_an_entry(self):
        state={}
        for t in (0,30000):
            m=market(now=NOW+t,allowed=True)
            m['entryPlanState']={'state':'blocked','reason':'Widerstand vor dem Ziel'}
            state,e=self.run_tick(state,m,NOW+t)
        self.assertEqual(self.kinds(e),['market-scenario'])
        self.assertIn('Widerstand vor dem Ziel',e[0]['body'])

    def test_main_title_not_hidden_by_earlier_warning(self):
        for kind in ('signal-change','market-scenario'):
            events=[{'title':'FRÜHWARNUNG','body':'warning','data':{'kind':'general','eventKind':'early-warning'}},
                    {'title':'HAUPTSIGNAL','body':'confirmed','data':{'kind':'general','eventKind':kind,'direction':'LONG'}}]
            msg=b.compose_events(events)
            self.assertEqual(msg['title'],'HAUPTSIGNAL')
            self.assertEqual(msg['data']['direction'],'LONG')
            self.assertEqual(set(msg['data']['events']),{'early-warning',kind})
            urgent={'title':'STOP','body':'exit','data':{'kind':'trade','eventKind':'stop-hit'}}
            msg=b.compose_events(events+[urgent])
            self.assertEqual(msg['title'],'STOP')
            self.assertNotIn('confirmed',msg['body'])


if __name__=='__main__':unittest.main()
