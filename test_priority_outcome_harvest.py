"""Fresh 60m evidence must not wait for historical horizon rotation."""
import json
import os
import time
import unittest
import uuid
from unittest.mock import MagicMock, patch
import decision_audit as audit
import psycopg


class PriorityTests(unittest.TestCase):
    def test_same_recent_budget_and_archive_rotation(self):
        for horizon in audit.HARVEST_HORIZONS:
            conn=MagicMock()
            with patch.object(audit,'_harvest_at',0), patch.object(audit.time,'time',return_value=100), \
                 patch.object(audit,'_next_harvest_horizon',return_value=horizon), \
                 patch.object(audit,'_harvest_recent') as recent, patch.object(audit,'_harvest_horizon') as old:
                audit.harvest(conn)
                self.assertEqual(sum(c.kwargs['batch_size'] for c in recent.call_args_list),128)
                self.assertEqual(recent.call_args_list[0].args,(conn,60))
                old.assert_called_once_with(conn,horizon)
                audit.harvest(conn)
                self.assertEqual(old.call_count,1,'Repeated calls retain the existing throttle')

    def test_priority_timeout_cannot_cancel_other_horizons(self):
        conn=MagicMock()
        with patch.object(audit,'_harvest_at',0), patch.object(audit.time,'time',return_value=100), \
             patch.object(audit,'_next_harvest_horizon',return_value=15), \
             patch.object(audit,'_harvest_recent',side_effect=[psycopg.errors.QueryCanceled(),0]) as recent, \
             patch.object(audit,'_harvest_horizon') as old, patch('builtins.print'):
            audit.harvest(conn)
        self.assertEqual([c.args[1] for c in recent.call_args_list],[60,15])
        old.assert_called_once_with(conn,15)
        self.assertEqual(conn.transaction.call_count,3)

    def test_invalid_batch_cannot_create_unbounded_query(self):
        for value in (0,129,-1,True,1.5,'16'):
            conn=MagicMock()
            with self.assertRaises(ValueError):audit._harvest_recent(conn,60,batch_size=value)
            conn.execute.assert_not_called()


@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PriorityDatabaseTests(unittest.TestCase):
    def test_first_pass_uses_original_clock_and_excludes_absent_or_foreign_quotes(self):
        from psycopg import sql
        schema='priority_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                conn.execute('CREATE TABLE bob_decision_audit(id TEXT PRIMARY KEY,recorded_at TIMESTAMPTZ,payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_outcomes(decision_id TEXT,horizon INTEGER,truth JSONB,PRIMARY KEY(decision_id,horizon))')
                conn.execute('CREATE TABLE bob_decision_harvest_cursor(horizon INTEGER PRIMARY KEY,recorded_at TIMESTAMPTZ,decision_id TEXT,attempted_at TIMESTAMPTZ)')
                conn.execute('INSERT INTO bob_decision_harvest_cursor(horizon) VALUES(1)')
                conn.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
                now=int(time.time()*1000)
                records={}
                for i,key in enumerate(('available','missing','foreign','out-of-window')):
                    start=now-(61+i*3)*60000
                    record=dict(recordedAt=start,marketEvaluable=True,price=100,direction='LONG')
                    records[key]=record
                    # DB insertion time differs from the frozen source decision.
                    conn.execute('INSERT INTO bob_decision_audit VALUES(%s,to_timestamp(%s/1000.0),%s::jsonb)',
                                 (key,start+20000,json.dumps(record)))
                    if key=='missing':continue
                    source='other-source' if key=='foreign' else 'gold-api-xau-usd-v1'
                    at=start+3600000+(61000 if key=='out-of-window' else 1000)
                    conn.execute('INSERT INTO bob_spot_observations VALUES(%s,to_timestamp(%s/1000.0),101)',(source,at))
                with patch.object(audit,'_harvest_at',0):audit.harvest(conn)
                rows=conn.execute('SELECT decision_id,horizon,truth FROM bob_decision_outcomes').fetchall()
                self.assertEqual([(key,h) for key,h,_ in rows],[('available',60)])
                truth=rows[0][2]
                self.assertEqual(audit.milliseconds(truth['at']),records['available']['recordedAt']+3601000)
                self.assertAlmostEqual(audit.outcome(records['available'],truth,60)['directionalPct'],1)
                with patch.object(audit,'_harvest_at',0):audit.harvest(conn)
                self.assertEqual(conn.execute('SELECT decision_id,horizon,truth FROM bob_decision_outcomes').fetchall(),rows)
                self.assertEqual(dict(conn.execute('SELECT id,payload FROM bob_decision_audit').fetchall()),records)
            finally:
                conn.rollback()
