import json,os,unittest
from unittest.mock import MagicMock,patch
import improvement_resilience as r

class ResilienceTests(unittest.TestCase):
    def event(self):return dict(body='Stop prüfen',data=dict(eventKind='stop-hit',tradeId='test',generatedAt=1000,dataAt=900))
    def test_latency_missing_times_and_duplicate_scope(self):
        first=r.hint_record(1,self.event(),True,2000)
        failed=r.hint_record(1,self.event(),False,3000)
        second=r.hint_record(1,self.event(),True,4000)
        other=r.hint_record(2,self.event(),True,5000)
        summary=r.hint_summary([first,failed,second,other])
        self.assertEqual(summary['repeats'],1);self.assertEqual(summary['failed'],1)
        self.assertEqual(summary['prompt'],3)
        event=self.event();event['data'].pop('generatedAt')
        self.assertEqual(r.hint_record(1,event,True,5000)['timing'],'unknown')
        self.assertEqual(r.hint_record(1,self.event(),True,40000)['timing'],'delayed')
        self.assertNotIn('Stop prüfen',json.dumps(first))
    def test_priorities_group_and_do_not_activate(self):
        report=dict(dailyReview=[dict(missingSlots=10,invalidSlots=3)],costEvidence=dict(missing=2),assessment=dict(missedWinners=7))
        result=r.prioritize(report,dict(items=[dict(status='failed')]),dict(failed=2,delayed=3,repeats=10))
        self.assertEqual([i['key'] for i in result['items']],['resilience','data','delivery','duplicates','costs','missed'])
        self.assertEqual(result['items'][1]['cases'],13)
    def test_drill_failure_recorded_and_secrets_not_inherited(self):
        database=MagicMock();conn=database.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value=None
        with patch.dict(os.environ,{'DATABASE_URL':'secret','VAPID_PRIVATE_KEY':'secret'}),patch.object(r.subprocess,'run',return_value=type('R',(),{'returncode':1})()) as run:
            r.run_drills(database,1792396800000)
        self.assertEqual(run.call_count,3)
        self.assertNotIn('DATABASE_URL',run.call_args.kwargs['env'])
        insert=[c for c in conn.execute.call_args_list if c.args[0].startswith('INSERT')][0]
        self.assertTrue(all(i['status']=='failed' for i in json.loads(insert.args[1][2])['items']))
        conn.commit.assert_called_once()
    def test_already_run_does_not_repeat(self):
        database=MagicMock()
        with patch.object(r.subprocess,'run') as run:r.run_drills(database,1792396800000)
        run.assert_not_called()

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class Persistence(unittest.TestCase):
    def test_capture_and_read_keep_unknown_evidence(self):
        import psycopg,uuid
        schema='resilience_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
            r.init(conn)
            e=dict(body='test',data=dict(eventKind='stop-hit',generatedAt=1000))
            r.capture(conn,1,[e],True,2000);r.capture(conn,1,[e],True,3000)
            report=r.read(conn,{},4000)
            self.assertEqual(report['hints']['repeats'],1)
            self.assertEqual(report['hints']['attempts'],2)
            self.assertEqual(report['drills']['items'],[])
            conn.execute('DROP SCHEMA '+schema+' CASCADE')
