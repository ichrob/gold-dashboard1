import json
import os
import unittest
from contextlib import nullcontext
from unittest.mock import patch
import evidence_repair as repair

class RepairTests(unittest.TestCase):
    def test_compaction_defers_repair_without_touching_queue(self):
        from unittest.mock import MagicMock
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=(False,)
        with patch.object(repair,'reconcile') as reconcile, patch.object(repair,'discover') as discover:
            self.assertEqual(repair.tick(conn,1000),{'processed':0,'status':'maintenance-busy'})
            reconcile.assert_not_called()
            discover.assert_not_called()
        self.assertEqual(conn.execute.call_count,1)

    def test_late_archive_retry_reclassifies_technical_failure_without_recovery(self):
        from unittest.mock import MagicMock
        conn=MagicMock()
        payload={'technicalFailure':True,'history':[{'result':'failure'}]}
        repair.archive_attempt_state(conn,'case',payload,False,'Original fehlt weiterhin',1000)
        stored=json.loads(conn.execute.call_args.args[1][0])
        self.assertFalse(stored['technicalFailure'])
        self.assertEqual(stored['reason'],'Original fehlt weiterhin')
        self.assertNotIn('recovered',conn.execute.call_args.args[0])
        self.assertNotIn('status',stored)
        self.assertEqual(stored['history'],payload['history'])
        conn.reset_mock()
        repair.archive_attempt_state(conn,'case',payload,False,'Original fehlt weiterhin',2000)
        conn.execute.assert_not_called()

    def test_archive_budget_eventually_reaches_every_unresolved_case(self):
        class Queue:
            def __init__(self):self.times={str(i).zfill(3):0 for i in range(100)};self.batch=[]
            def transaction(self):return nullcontext()
            def execute(self,sql,args=()):
                if sql.startswith('WITH pending'):
                    keys=sorted(self.times,key=lambda k:(self.times[k],k))[:48]
                    self.batch=[(k,{'history':[]},dict(decision=k,horizon=15),{'marketEvaluable':True},None) for k in keys]
                elif 'id=ANY' in sql:
                    for k in args[1]:self.times[k]=args[0]
                else:raise AssertionError(sql)
                return self
            def fetchall(self):return self.batch
        conn=Queue()
        with patch.object(repair,'retry_signal',return_value=(False,False,'Original fehlt')) as retry:
            for now in range(1,14):repair.reconcile(conn,now)
        self.assertEqual({c.args[1]['decision'] for c in retry.call_args_list},set(conn.times))

    def test_batched_reconcile_preserves_unknown_and_wrong_time_evidence(self):
        from unittest.mock import MagicMock
        start=1800000000000
        record=dict(recordedAt=start,marketEvaluable=True,price=4000.,direction='LONG')
        target=start+15*60000
        pending=[
            ('valid',{},dict(decision='a',horizon=15),record,dict(at=target,price=4010.)),
            ('wrong-time',{'history':[]},dict(decision='b',horizon=15),record,dict(at=target-1,price=4010.)),
            ('invalid',{'history':[]},dict(decision='c',horizon=15),dict(record,marketEvaluable=False),dict(at=target,price=4010.)),
            ('deleted',{'history':[]},dict(decision='d',horizon=15),None,None),
        ]
        pending += [('missing-'+str(i),{'history':[]},dict(decision=str(i),horizon=15),record,None) for i in range(44)]
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=pending
        with patch.object(repair,'retry_signal',return_value=(False,False,'Original fehlt')) as retry:
            repair.reconcile(conn,target+60000)
        self.assertEqual(retry.call_count,8,'Archive work remains bounded')
        updates=[c.args for c in conn.execute.call_args_list if "status='recovered'" in c.args[0]]
        self.assertEqual(len(updates),1)
        self.assertEqual(updates[0][1][-1],'valid')
        self.assertEqual(json.loads(updates[0][1][1])['lastAttemptAt'],target+60000)
        rotations=[c.args[1] for c in conn.execute.call_args_list if 'id=ANY' in c.args[0]]
        self.assertEqual(set(rotations[0][1]),{r[0] for r in pending[:12]},
                         'Unexamined cases retain their old queue time for the next pass')
        self.assertEqual(len(conn.execute.call_args_list),3,'One bounded read, one rotation, one verified recovery')

    def test_retries_are_bounded_and_only_verified_success_closes(self):
        class Conn:
            def __init__(self):self.attempts=0;self.status='trying';self.payload={'history':[]};self.next=0
            def transaction(self):return nullcontext()
            def execute(self,sql,args=()):
                if sql.startswith('UPDATE bob_test_repairs'):
                    self.status,self.attempts,self.next,raw,_=args;self.payload=json.loads(raw)
                return self
            def fetchone(self):return (True,)
            def fetchall(self):return [('x','signal',{},self.attempts,self.payload)] if self.status=='trying' else []
        conn=Conn()
        with patch.object(repair,'reconcile'),patch.object(repair,'discover'),patch.object(repair,'retry_signal',return_value=(False,False,'Originalkurs fehlt')):
            for i in range(3):repair.tick(conn,1000+i*repair.INTERVAL)
        self.assertEqual(conn.status,'escalated');self.assertEqual(conn.attempts,3)
        self.assertEqual(len(conn.payload['history']),3)
        self.assertFalse(conn.payload['technicalFailure'])
        conn=Conn()
        with patch.object(repair,'reconcile'),patch.object(repair,'discover'),patch.object(repair,'retry_signal',return_value=(True,False,'Original bestätigt')):
            repair.tick(conn,1000)
        self.assertEqual(conn.status,'recovered')

    def test_bulk_timeout_does_not_prevent_targeted_worker(self):
        import push_server
        with patch('improvement_resilience.run_drills'), \
             patch.object(push_server,'run_audit_harvest_once',side_effect=RuntimeError('bulk timeout')), \
             patch.object(push_server,'run_test_repair_once') as targeted, \
             patch.object(push_server.time,'sleep',side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):push_server.audit_outcome_loop()
        targeted.assert_called_once_with(push_server.db)

    def test_archive_failure_is_not_recovery(self):
        from unittest.mock import MagicMock
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[('x','signal',{},0,{'history':[]})]
        with patch.object(repair,'reconcile'),patch.object(repair,'discover'),patch.object(repair,'retry_signal',side_effect=RuntimeError('sensitive')):
            repair.tick(conn,1000)
        updates=[c.args[1] for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE bob_test_repairs')]
        self.assertEqual(updates[0][0],'trying');self.assertNotIn('sensitive',updates[0][3])
        self.assertTrue(json.loads(updates[0][3])['technicalFailure'])

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class RepairPersistenceTests(unittest.TestCase):
    def test_repair_transaction_and_compaction_exclude_each_other(self):
        import psycopg
        key=('bob_storage_maintenance_v1',)
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as reader, psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as writer:
            self.assertTrue(reader.execute('SELECT pg_try_advisory_xact_lock_shared(hashtext(%s))',key).fetchone()[0])
            self.assertFalse(writer.execute('SELECT pg_try_advisory_lock(hashtext(%s))',key).fetchone()[0])
            reader.rollback()
            self.assertTrue(writer.execute('SELECT pg_try_advisory_lock(hashtext(%s))',key).fetchone()[0])
            try:
                self.assertEqual(repair.tick(reader,1000),{'processed':0,'status':'maintenance-busy'})
                reader.rollback()
            finally:
                writer.execute('SELECT pg_advisory_unlock(hashtext(%s))',key)
            self.assertTrue(reader.execute('SELECT pg_try_advisory_xact_lock_shared(hashtext(%s))',key).fetchone()[0])
            reader.rollback()

    def test_technical_archive_failure_keeps_technical_group(self):
        import psycopg,uuid
        from psycopg import sql
        import training_handoff
        schema='repair_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                repair.init(conn)
                for key,extra in [('gap',{'technicalFailure':False}),
                                  ('error',{'technicalFailure':True}),
                                  ('legacy',{'reason':'Automatische Archivprüfung technisch fehlgeschlagen; keine Reparatur bestätigt.'})]:
                    repair.enqueue(conn,key,'signal',{},dict(reasons=['missingFollowup']),1000)
                    payload=dict(reasons=['missingFollowup'],history=[{'action':'Archiv prüfen'}],**extra)
                    conn.execute("UPDATE bob_test_repairs SET status='escalated',attempts=3,payload=%s::jsonb WHERE id=%s",(json.dumps(payload),key))
                groups={g['id']:g for g in training_handoff.problem_groups(conn)}
                self.assertEqual(groups['test:signal:unknown']['cases'],2)
                self.assertEqual(groups['test:signal:missingFollowup']['cases'],1)
                self.assertTrue(all(g['status']=='escalated' for g in groups.values()))
            finally:
                conn.rollback()
    def test_recovery_exact_time_persistence_and_no_frozen_rewrite(self):
        import psycopg,uuid,time
        from psycopg import sql
        schema='repair_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                repair.init(conn)
                conn.execute('CREATE TABLE bob_ranking_samples(currency TEXT,slot BIGINT,payload JSONB,outcome JSONB)')
                conn.execute('CREATE TABLE bob_ranking_lifecycles(currency TEXT,slot BIGINT,result JSONB,state JSONB,complete BOOLEAN)')
                conn.execute('CREATE TABLE bob_precision_quotes(isin TEXT,source TEXT,currency TEXT,at BIGINT,payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_audit(id TEXT PRIMARY KEY,recorded_at TIMESTAMPTZ,payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_outcomes(decision_id TEXT,horizon INTEGER,truth JSONB,PRIMARY KEY(decision_id,horizon))')
                conn.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
                now=int(time.time()*1000);start=now-30*60000
                payload=dict(recordedAt=start,marketEvaluable=True,price=4000.,direction='LONG')
                conn.execute("INSERT INTO bob_decision_audit VALUES('signal',to_timestamp(%s/1000.0),%s::jsonb)",(start,json.dumps(payload)))
                frozen=dict(at=start,marketReady=True,candidates=[],missing=['DETEST'])
                outcome=dict(complete=False,status='incomplete',missing=['DETEST'])
                conn.execute("INSERT INTO bob_ranking_samples VALUES('EUR',%s,%s::jsonb,%s::jsonb)",(start,json.dumps(frozen),json.dumps(outcome)))
                repair.tick(conn,now);conn.commit()
                states=dict(conn.execute('SELECT kind,status FROM bob_test_repairs').fetchall())
                self.assertEqual(states,{'title':'escalated','signal':'trying'})
                # A present-day price is NOT accepted for a missing historical outcome.
                conn.execute("INSERT INTO bob_spot_observations VALUES('gold-api-xau-usd-v1',to_timestamp(%s/1000.0),4100)",(now,))
                repair.tick(conn,now+repair.INTERVAL)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_outcomes').fetchone()[0],0)
                target=start+15*60000
                conn.execute("INSERT INTO bob_spot_observations VALUES('gold-api-xau-usd-v1',to_timestamp(%s/1000.0),4010)",(target,))
                repair.tick(conn,now+2*repair.INTERVAL);conn.commit();repair.init(conn)
                report=repair.report(conn)
                self.assertEqual(report['counts']['recovered'],1);self.assertEqual(report['counts']['escalated'],1)
                self.assertEqual(report['items'][0]['attempts'],1)
                truth=conn.execute('SELECT truth FROM bob_decision_outcomes').fetchone()[0]
                self.assertEqual(truth['at'],target);self.assertEqual(truth['price'],4010)
                self.assertEqual(conn.execute('SELECT outcome FROM bob_ranking_samples').fetchone()[0],outcome)
                self.assertEqual(report['workerCheckedAt'],now+2*repair.INTERVAL)
                import training_handoff
                handoff=training_handoff.summary(conn)
                self.assertNotIn('DETEST',json.dumps(handoff))
                self.assertIn(dict(kind='title',reason='missing-original-evidence',cases=1),handoff['reasons'])
                self.assertEqual(handoff['workerCheckedAt'],report['workerCheckedAt'])
                training_handoff.sync_groups(conn,handoff);conn.commit()
                self.assertEqual(len(handoff['events']),1)
                first_key=handoff['problemGroups'][0]['dispatchKey']
                # Restart/migration and repeated scans do not create another request.
                repair.init(conn)
                repeated=training_handoff.summary(conn);training_handoff.sync_groups(conn,repeated)
                self.assertEqual(repeated['events'],[])
                self.assertEqual(repeated['problemGroups'][0]['dispatchKey'],first_key)
                # Only a verified disappearance followed by recurrence opens an episode.
                conn.execute("UPDATE bob_test_repairs SET status='recovered' WHERE kind='title'")
                resolved=training_handoff.summary(conn);training_handoff.sync_groups(conn,resolved)
                self.assertEqual(resolved['events'][0]['event'],'resolved')
                conn.execute("UPDATE bob_test_repairs SET status='escalated' WHERE kind='title'")
                again=training_handoff.summary(conn);training_handoff.sync_groups(conn,again)
                self.assertEqual(again['events'][0]['episode'],2)
                self.assertNotEqual(again['problemGroups'][0]['dispatchKey'],first_key)
                # A separately recovered/backfilled signal must leave the help queue.
                conn.execute("UPDATE bob_test_repairs SET status='escalated' WHERE kind='signal'")
                repair.tick(conn,now+3*repair.INTERVAL)
                self.assertEqual(repair.report(conn)['counts']['recovered'],1)
                # A late original observation also repairs an escalated case
                # without waiting for the seven-day bulk cursor to circle back.
                conn.execute("UPDATE bob_test_repairs SET status='escalated' WHERE kind='signal'")
                conn.execute("DELETE FROM bob_decision_outcomes WHERE decision_id='signal'")
                repair.tick(conn,now+4*repair.INTERVAL)
                self.assertEqual(repair.report(conn)['counts']['recovered'],1)
                # A present but wrongly timed outcome must not hide an unresolved test.
                conn.execute("DELETE FROM bob_test_repairs WHERE kind='signal'")
                conn.execute("UPDATE bob_decision_outcomes SET truth=%s::jsonb WHERE decision_id='signal'",(json.dumps(dict(at=target-1,price=4010)),))
                repair.discover(conn,now+3*repair.INTERVAL)
                self.assertEqual(conn.execute("SELECT count(*) FROM bob_test_repairs WHERE kind='signal'").fetchone()[0],1)
                # Bounded pages must eventually discover the entire older archive.
                conn.execute('DELETE FROM bob_test_repairs')
                conn.execute('DELETE FROM bob_decision_outcomes')
                conn.execute('DELETE FROM bob_decision_audit')
                old=now-300*60000
                for i in range(300):
                    conn.execute('INSERT INTO bob_decision_audit VALUES(%s,to_timestamp(%s/1000.0),%s::jsonb)',
                                 ('page-%04d'%i,old,json.dumps(dict(recordedAt=old,marketEvaluable=True))))
                for _ in range(3):repair.discover(conn,now)
                self.assertEqual(conn.execute("SELECT count(*) FROM bob_test_repairs WHERE kind='signal'").fetchone()[0],900)
                self.assertIsNone(conn.execute('SELECT signal_cursor FROM bob_test_repair_control WHERE id=1').fetchone()[0])
                repair.init(conn)  # Migration remains idempotent after adding cursor.
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
