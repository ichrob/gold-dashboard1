import copy
import json
import os
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import diagnostic_history as history
import evidence_repair as repair


def source(at,price=4000):
    return dict(primary='Gold-API.com · XAU/USD Spot',xaus=price,
                spot_price_as_of=datetime.fromtimestamp(at/1000,timezone.utc).isoformat())


class OriginalInputTests(unittest.TestCase):
    def test_recovery_requires_original_identity_clock_and_capture_freshness(self):
        target=1800000000000
        good=source(target)
        self.assertEqual(history.original_spot(good,(target+10000)/1000)[1],4000)
        for payload,observed in [
            (dict(good,primary='Investing.com · Gold-CFD'),(target+10000)/1000),
            (dict(good,xaus=True),(target+10000)/1000),
            (dict(good,spot_price_as_of=None),(target+10000)/1000),
            (good,(target-1)/1000),(good,(target+60001)/1000)]:
            self.assertIsNone(history.original_spot(payload,observed))

    def test_journal_never_uses_receipt_time_or_conflicting_source_values(self):
        target=1800000000000
        conn=MagicMock()
        conn.execute.return_value.fetchall.return_value=[
            (source(target-1),(target+10000)/1000),
            (source(target+1000,4001),(target+2000)/1000),
            (source(target+60001,4002),(target+61000)/1000)]
        value=repair.journal_truth(conn,target)
        self.assertEqual(value['at'],target+1000)
        self.assertEqual(value['price'],4001)
        self.assertEqual(value['evidenceOrigin'],'diagnostic-input-journal')
        conn.execute.return_value.fetchall.return_value.append((source(target+1000,9999),(target+3000)/1000))
        self.assertIsNone(repair.journal_truth(conn,target))
        conn.execute.side_effect=RuntimeError('private connection string')
        self.assertIsNone(repair.journal_truth(conn,target))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class JournalRecoveryDatabaseTests(unittest.TestCase):
    def test_saved_input_repairs_exact_outcome_and_future_input_is_redundantly_archived(self):
        import psycopg
        from psycopg import sql
        import uuid
        import bob_market_store
        schema='input_recovery_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                history.init(conn);bob_market_store.init(conn)
                conn.execute('CREATE TABLE bob_decision_audit(id TEXT PRIMARY KEY,payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_outcomes(decision_id TEXT,horizon INTEGER,truth JSONB,PRIMARY KEY(decision_id,horizon))')
                now=int(time.time()*1000);start=now-1800000;target=start+900000
                record=dict(recordedAt=start,marketEvaluable=True,price=4000,direction='LONG')
                conn.execute("INSERT INTO bob_decision_audit VALUES('test',%s::jsonb)",(json.dumps(record),))
                # An old input event exists, but the separate spot archive missed it.
                conn.execute('''INSERT INTO bob_diagnostic_history(id,trace_id,stage,observed_at,payload)
                    VALUES(%s,%s,'input',%s,%s::jsonb)''',('a'*32,'b'*32,(target+10000)/1000,json.dumps(source(target,4010))))
                ok,_,reason=repair.retry_signal(conn,dict(decision='test',horizon=15))
                self.assertTrue(ok);self.assertIn('Diagnosejournal',reason)
                truth=conn.execute('SELECT truth FROM bob_decision_outcomes').fetchone()[0]
                self.assertEqual(truth['at'],target)
                self.assertEqual(truth['price'],4010)
                self.assertEqual(truth['evidenceOrigin'],'diagnostic-input-journal')
                conn.execute("UPDATE bob_decision_audit SET payload=%s::jsonb WHERE id='test'",(json.dumps(dict(record,marketEvaluable=False)),))
                self.assertFalse(repair.retry_signal(conn,dict(decision='test',horizon=15))[0])
                # New input delivery also saves its original source tick. A later
                # conflicting value must neither overwrite it nor lose the journal.
                e=dict(id='c'*32,traceId='d'*32,stage='input',at=now/1000,payload=source(now-1000,4020))
                history.write(conn,e)
                conflicting=copy.deepcopy(e);conflicting['id']='e'*32;conflicting['payload']['xaus']=9999
                history.write(conn,conflicting)
                rows=conn.execute('SELECT price FROM bob_spot_observations').fetchall()
                self.assertEqual(rows,[(4020.,)])
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_diagnostic_history').fetchone()[0],3)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
