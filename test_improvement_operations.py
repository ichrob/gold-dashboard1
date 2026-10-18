import unittest,os,json
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,patch
import improvement_operations as o
import improvement_tracker as m
from test_improvement_tracker import at

class OperationsTests(unittest.TestCase):
    def trade(self):
        return dict(tradeId='private-test',active=False,product=dict(currency='CHF',entry=10,quantity=2),
            purchase=dict(at='2026-10-19T08:00:00+02:00'),exitReceipt=dict(executedAt='2026-10-19T09:00:00+02:00'),
            actualExecution=dict(entryCHF=10,exitCHF=12,quantity=2,feesCHF=1,netCHF=3))
    def test_real_native_chf_and_missing_fees_remain_distinct(self):
        row=self.trade();r=o.cost_review([row],m.START)
        self.assertEqual(r['complete'],1);self.assertEqual(r['items'][0]['netCHF'],3)
        del row['actualExecution']['feesCHF']
        r=o.cost_review([row],m.START)
        self.assertEqual(r['complete'],0);self.assertIsNone(r['items'][0]['feesNative'])
        self.assertIn('Tatsächliche Kauf- und Verkaufsgebühren',r['items'][0]['missing'])
    def test_unknown_timezone_and_nan_never_complete(self):
        row=self.trade();row['purchase']={'executedLocal':'19.10.2026 08:00:00'}
        row['actualExecution']['entryCHF']=float('nan')
        r=o.cost_review([row],m.START)
        self.assertEqual(r['complete'],0);self.assertIsNone(r['items'][0]['entry'])
    def test_duplicate_reports_and_recurrence(self):
        t=datetime.now(timezone.utc)
        events=[(t,'detected','a'),(t,'detected','a'),(t+timedelta(seconds=10),'repair-verified','a'),
                (t+timedelta(seconds=10),'recovered','a'),(t+timedelta(seconds=20),'detected','a')]
        r=o.repair_episodes(events)
        self.assertEqual((r['episodes'],r['verified'],r['open'],r['recurrences']),(2,1,1,1))
        self.assertEqual(r['repeatedDetections'],1);self.assertEqual(r['meanRepairSeconds'],10)
        self.assertEqual(r['verifiedPct'],50)
        self.assertIsNone(o.repair_episodes([])['verifiedPct'])
    def test_ordinary_recovery_not_verified_repair(self):
        t=datetime.now(timezone.utc)
        r=o.repair_episodes([(t,'recovered','a'),(t,'detected','a')])
        self.assertEqual(r['verified'],0);self.assertEqual(r['recoveredWithoutVerifiedRepair'],1)
    def test_daily_outages_use_scheduled_denominator(self):
        conn=Mock();conn.execute.return_value.fetchall.return_value=[('2026-10-19',7,5,at(19,8,4),at(19,8,4))]
        r=o.daily(conn,m.VERSION,at(19,8,5),m.START,[])[0]
        self.assertEqual((r['expected'],r['missingSlots'],r['invalidSlots']),(10,3,2))
        self.assertEqual(r['coveragePct'],50)
    def test_gate_never_approves_and_missing_phase_blocks(self):
        report=dict(assessment=dict(code='benefit',netDifferenceCHF=10,regimes=[dict(key=k,cases=30,days=5,difference=.1,stressDifference=.1) for k in ('rising','falling','sideways')]),
            real=dict(pairedCount=20,pairedDays=10),reliability=dict(coveragePct=100),progress=[100]*4,
            comparison=dict(cohort='baseline'),protocol=dict(candidate='test'))
        costs=dict(complete=20,missing=0)
        r=o.release_dossier(report,costs)
        self.assertTrue(r['evidenceReady']);self.assertFalse(r['approved']);self.assertFalse(r['automaticRuleChange'])
        report['assessment']['regimes'][0]['stressDifference']=-.1
        self.assertFalse(o.release_dossier(report,costs)['evidenceReady'])
        report['assessment']['regimes'][0]['stressDifference']=.1
        self.assertFalse(o.release_dossier(report,dict(complete=20,missing=1))['evidenceReady'])
    def test_telemetry_contains_no_private_trade_results(self):
        conn=Mock();row=dict(day='2026-10-19',observed=1,valid=1,expected=1,lastSlot=at(),lastValidSourceAt=at(),coveragePct=100)
        result=o.archive(conn,dict(protocol=dict(version='test'),dailyReview=[row],releaseDossier={'status':'blocked'}),at())
        self.assertEqual(set(result),{'version','at','persisted','day','observed','valid','expected','lastSlot','lastValidSourceAt','coveragePct'})

@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class OperationsDatabaseTests(unittest.TestCase):
    def test_real_error_groups_and_episodes(self):
        import psycopg,uuid,bob_repair_store,evidence_repair
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            schema='operations_'+uuid.uuid4().hex
            conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
            try:
                o.init(conn);bob_repair_store.init(conn);evidence_repair.init(conn)
                now=at();t=datetime.fromtimestamp(now/1000,timezone.utc)
                for i in range(10):
                    conn.execute('INSERT INTO bob_self_heal_events(event_id,event_at,kind,code) VALUES(%s,%s,%s,%s)',(str(i),t,'detected','market-worker-stopped'))
                conn.execute('INSERT INTO bob_self_heal_events(event_id,event_at,kind,code) VALUES(%s,%s,%s,%s)',('verified',t+timedelta(seconds=10),'repair-verified','market-worker-stopped'))
                for i in range(15):
                    conn.execute("INSERT INTO bob_test_repairs VALUES(%s,'signal','{}','escalated',3,%s,%s::jsonb)",(str(i),now,json.dumps(dict(reasons=['invalidStart'],history=[{'at':now}]))))
                r=o.repairs(conn,now+20000)
                self.assertEqual((r['episodes'],r['verified'],r['repeatedDetections']),(1,1,9))
                self.assertEqual((r['testProblemTypes'],r['testCases']),(1,15))
            finally:
                conn.rollback();conn.execute('DROP SCHEMA IF EXISTS '+schema+' CASCADE');conn.commit()

class CommitTelemetryTests(unittest.TestCase):
    def test_failed_commit_never_reports_persisted_success(self):
        import push_server
        from contextlib import contextmanager
        conn=Mock();conn.commit.side_effect=RuntimeError('commit failed')
        @contextmanager
        def database():yield conn
        with patch.object(push_server.improvement_tracker,'archive_review',return_value={'persisted':True}),patch('builtins.print') as emit:
            with self.assertRaises(RuntimeError):push_server.run_improvement_review_once(database)
            emit.assert_not_called()
