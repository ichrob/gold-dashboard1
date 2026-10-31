import os
import unittest
import uuid
import storage_layout

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class LayoutTests(unittest.TestCase):
    def test_readonly_layout_adds_up_without_touching_originals(self):
        import psycopg
        schema='layout_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                c.execute('CREATE TABLE bob_diagnostic_history(id int primary key,stage text,payload jsonb)')
                c.execute("INSERT INTO bob_diagnostic_history SELECT i,'analysis',jsonb_build_object('value',i) FROM generate_series(1,1000)i")
                before=c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall()
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    r=storage_layout.report(c)
                    self.assertEqual(r['status'],'observed')
                    t=r['tables'][0]
                    self.assertEqual(t['totalBytes'],sum(t[k] for k in ('heapBytes','indexBytes','toastBytes','otherBytes')))
                    self.assertTrue(r['indexes'][0]['valid'])
                    self.assertIsNone(r['reclaimableBytes'])
                    self.assertEqual(r['diagnosticPayloadSample']['status'],'sampled')
                self.assertEqual(c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall(),before)
                c.execute('DROP TABLE bob_diagnostic_history')
                with c.transaction():
                    r=storage_layout.report(c)
                    self.assertEqual(r['status'],'observed')
                    self.assertEqual(r['diagnosticPayloadSample']['status'],'not-observed')
                    self.assertEqual(c.execute('SELECT 1').fetchone()[0],1)
            finally:
                c.execute('DROP SCHEMA '+schema+' CASCADE')


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DecisionAuditFootprintTests(unittest.TestCase):
    def test_bounded_read_only_aggregation_and_missing_table(self):
        import json
        import psycopg
        from psycopg.types.json import Jsonb
        schema='audit_layout_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                c.execute('''CREATE TABLE bob_decision_audit (
                    id text PRIMARY KEY, recorded_at timestamptz NOT NULL,
                    payload jsonb NOT NULL)''')
                c.execute('CREATE INDEX audit_sample_time ON bob_decision_audit(recorded_at,id)')
                for i in range(12):
                    payload={'decisionContext':{'evidence':'a'*3000,'number':9007199254740993},
                             'products':[{'quote':i}], 'privateExample':'do-not-echo'}
                    c.execute("INSERT INTO bob_decision_audit VALUES(%s,now()+%s*interval '1 second',%s)",
                              (str(i),i,Jsonb(payload)))
                originals=c.execute('SELECT id,payload FROM bob_decision_audit ORDER BY id').fetchall()
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    result=storage_layout.decision_payload_sample(c)
                self.assertEqual(result['status'],'sampled')
                self.assertEqual(result['sampledRecords'],8)
                self.assertEqual(result['method'],'indexed-oldest-four-and-newest-four-max-eight-unique-rows')
                names={field['fieldGroup'] for field in result['fields']}
                self.assertEqual(names,{'decisionContext','products','other-fields'})
                self.assertEqual(next(field for field in result['fields']
                                      if field['fieldGroup']=='decisionContext')['observedFieldValues'],8)
                self.assertNotIn('do-not-echo',json.dumps(result))
                self.assertNotIn('9007199254740993',json.dumps(result))
                self.assertIsNone(result['reclaimableBytes'])
                self.assertEqual(c.execute('SELECT id,payload FROM bob_decision_audit ORDER BY id').fetchall(),originals)
                c.execute('DROP TABLE bob_decision_audit')
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    missing=storage_layout.decision_payload_sample(c)
                self.assertEqual(missing['status'],'not-observed')
                self.assertEqual(c.execute('SELECT 1').fetchone()[0],1)
            finally:
                c.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_empty_audit_does_not_claim_savings(self):
        import psycopg
        schema='empty_layout_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                c.execute('CREATE TABLE bob_decision_audit(id text PRIMARY KEY, recorded_at timestamptz, payload jsonb)')
                result=storage_layout.decision_payload_sample(c)
                self.assertEqual(result['status'],'empty')
                self.assertEqual(result['sampledRecords'],0)
                self.assertEqual(result['fields'],[])
            finally:
                c.execute('DROP SCHEMA '+schema+' CASCADE')
