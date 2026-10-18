import os
import unittest
from unittest.mock import Mock
from datetime import datetime, timedelta
import improvement_tracker as m


def at(day=19,hour=8,minute=0,second=0):
    return int(datetime(2026,10,day,hour,minute,second,tzinfo=m.ZONE).timestamp()*1000)


def market(now,price=4000,adx=20):
    return dict(price=price,dataAt=now,priceFresh=True,analysisBarAt=now-300000,
        ready=True,direction='LONG',context={'adx':adx},entryTimingGate={'allowed':True},
        session={'entryAllowed':True},ruleVersion='test')


class TrackerTests(unittest.TestCase):
    def test_start_and_windows(self):
        conn=Mock()
        self.assertFalse(m.capture(conn,{},at(18)))
        conn.execute.assert_not_called()
        self.assertFalse(m.eligible(at(19,7)))
        self.assertFalse(m.eligible(at(24,10)))
        self.assertTrue(m.eligible(at(19)))
        self.assertEqual(m.expected_slots(at(19,9)),120)
        self.assertEqual(m.expected_slots(at(20,8)),1680)
        self.assertEqual(m.expected_slots(at(18)),0)

    def test_stale_and_blocked_not_signals(self):
        now=at();x=market(now)
        self.assertTrue(m.observation(x,now)['ready'])
        self.assertFalse(m.observation(x,now)['keep'])
        self.assertTrue(m.observation(market(now,adx=30),now)['keep'])
        self.assertFalse(m.observation(x,now+90001)['valid'])
        x['entryTimingGate']['allowed']=False
        self.assertFalse(m.observation(x,now)['ready'])

    def test_pairs_count_missed_winners_and_costs(self):
        def row(change):
            return ('2026-10-19','validation',{'cohort':'test'},dict(directionalPct=change,keep=False,
                scenarios=[dict(baseline=change-c,candidate=0) for c in m.PROTOCOL['costPct']]))
        r=m.pairs([row(-1),row(1)])
        self.assertEqual(r['avoidedLosses'],1);self.assertEqual(r['missedGains'],1)
        self.assertEqual(r['falseSignalPct'],50)
        self.assertAlmostEqual(r['scenarios'][0]['baselineMean'],-.04)

    def test_no_data_never_success_and_outages_reduce_coverage(self):
        real=m.real_results([])
        q=m.summarize(0,0,0,None,[],real,at(18))
        self.assertEqual(q['progress'],[0]*4)
        q=m.summarize(120,60,1,at(19,9),[],real,at(19,9))
        self.assertEqual(q['reliability']['coveragePct'],50)
        self.assertEqual(q['progress'][1:], [0,0,0])
        self.assertFalse(q['adoption']['automaticRuleChange'])

    def test_progress_does_not_round_incomplete_goals_to_100(self):
        real=m.real_results([])
        real.update(count=20,days=10,pairedCount=19,pairedDays=10)
        q=m.summarize(100,100,20,at(),[],real,at(20,8))
        self.assertLess(q['progress'][0],100)
        self.assertEqual(q['progress'][1],100)
        self.assertLess(q['progress'][3],50)

    def test_real_costs_and_no_future_entry_evidence(self):
        start=at(20,10);end=start+3600000
        snap=dict(tradeId='x',dir='LONG',active=False,product={'currency':'EUR'},
            purchase={'at':datetime.fromtimestamp(start/1000,m.ZONE).isoformat(),'totalCHF':101},
            exitReceipt={'executedAt':datetime.fromtimestamp(end/1000,m.ZONE).isoformat(),'saleNetCHF':99})
        before=m.observation(market(start-30000),start-30000)
        r=m.real_results([snap],{'x':before},at(20,8))
        self.assertEqual(r['netCHF'],-2);self.assertEqual(r['pairedCandidateCHF'],0)
        self.assertEqual(r['drawdownCHF'],2)
        before['at']=start+1
        self.assertEqual(m.real_results([snap],{'x':before},at(20,8))['pairedCount'],0)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class TrackerDatabaseTests(unittest.TestCase):
    def test_persistent_dedup_future_pair_and_phase_boundary(self):
        import psycopg,uuid,json
        schema='improvement_test_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            try:
                m.init(conn)
                conn.execute('CREATE TABLE bob_real_trades (active BOOLEAN,updated_at TIMESTAMPTZ,snapshot JSONB)')
                t=at()
                m.capture(conn,market(t),t)
                m.capture(conn,market(t,price=9999),t)
                stored=conn.execute('SELECT payload FROM bob_improvement_observations').fetchone()[0]
                self.assertEqual(stored['price'],4000)
                self.assertIsNone(conn.execute('SELECT outcome FROM bob_improvement_trials').fetchone()[0])
                m.capture(conn,market(t+3600000,price=3960),t+3600000)
                outcome=conn.execute('SELECT outcome FROM bob_improvement_trials').fetchone()[0]
                self.assertAlmostEqual(outcome['directionalPct'],-1)
                self.assertEqual(outcome['scenarios'][0]['candidate'],0)
                self.assertIsNone(conn.execute('SELECT validation_at FROM bob_improvement_state').fetchone()[0])
                report=m.report(conn,t+3630000)
                self.assertEqual(report['comparison']['development']['count'],1)
                journal=report['decisionJournal']['items'][0]
                self.assertEqual(journal['decision'],'LONG')
                self.assertEqual(journal['status'],'evaluated')
                self.assertAlmostEqual(journal['netSpotPct'],-1.04)
                # Neutral trials use original followups without changing the strategy outcomes.
                # Keep this journal-only fixture isolated from the existing phase-boundary scenario.
                conn.execute('SAVEPOINT journal_case')
                neutral=dict(market(t+43200000),ready=False,direction='NEUTRAL')
                m.capture(conn,neutral,t+43200000)
                m.capture(conn,market(t+46800000,price=4040),t+46800000)
                neutral_review=m.report(conn,t+46830000)['decisionJournal']['items'][0]
                self.assertEqual(neutral_review['decision'],'ABWARTEN')
                self.assertEqual(neutral_review['status'],'observed')
                self.assertIsNone(conn.execute('SELECT outcome FROM bob_improvement_trials WHERE slot=%s',(t+43200000,)).fetchone()[0])
                conn.execute('ROLLBACK TO SAVEPOINT journal_case')
                self.assertEqual(report['progress'][3],0)
                # Sufficient completed development evidence freezes a future boundary.
                day=datetime(2026,10,19,8,tzinfo=m.ZONE); completed_days=0
                while completed_days<10:
                    if day.weekday()<5:
                        for hour in range(8,20,2):
                            stamp=int(day.replace(hour=hour).timestamp()*1000)
                            payload=m.observation(market(stamp),stamp)
                            conn.execute('INSERT INTO bob_improvement_trials VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING',
                                (m.VERSION,stamp,day.date().isoformat(),'development',json.dumps(payload),json.dumps(outcome)))
                        completed_days+=1
                    day+=timedelta(days=1)
                later=int(datetime(2026,11,3,8,tzinfo=m.ZONE).timestamp()*1000)
                m.capture(conn,market(later),later)
                boundary=conn.execute('SELECT validation_at FROM bob_improvement_state').fetchone()[0]
                self.assertEqual(boundary,later+1)
                m.capture(conn,market(later+7200000),later+7200000)
                self.assertEqual(conn.execute("SELECT count(*) FROM bob_improvement_trials WHERE phase='validation'").fetchone()[0],1)
                count=conn.execute('SELECT count(*) FROM bob_improvement_trials').fetchone()[0]
                m.archive_review(conn,later+7230000)
                m.archive_review(conn,later+7230000)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_improvement_reviews').fetchone()[0],1)
                recorded=m.report(conn,later+7230000)['history'][0]
                self.assertFalse(recorded['actualRuleChange'])
                self.assertIn('decision',recorded)
                conn.commit()
                # Reinitialization preserves evidence and does not rewrite the protocol.
                m.init(conn)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_improvement_trials').fetchone()[0],count)
            finally:
                conn.rollback()
                conn.execute('DROP SCHEMA IF EXISTS '+schema+' CASCADE');conn.commit()

if __name__=='__main__':unittest.main()
