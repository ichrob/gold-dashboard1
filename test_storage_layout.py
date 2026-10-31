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


class DecisionFootprintLogTests(unittest.TestCase):
    def test_sanitized_bounded_one_shot_log(self):
        from unittest.mock import patch
        import json
        sample={'status':'sampled','sampledRecords':8,
                'fields':[{'fieldGroup':'decisionContext','observedFieldValues':8,
                           'summedNestedBytes':1024,'maximumNestedBytes':256}]}
        before=storage_layout._DECISION_LOGGED
        try:
            storage_layout._DECISION_LOGGED=False
            with patch('builtins.print') as output:
                storage_layout._log_decision_sample_once({
                    **sample,'fields':[{'fieldGroup':'private-account-key',
                                        'observedFieldValues':8,'summedNestedBytes':900,
                                        'maximumNestedBytes':200}]})
                output.assert_not_called()
                storage_layout._log_decision_sample_once(sample)
                storage_layout._log_decision_sample_once(sample)
                self.assertEqual(output.call_count,1)
                logged=output.call_args.args[0]
                self.assertTrue(logged.startswith('BOB_DECISION_FOOTPRINT '))
                values=json.loads(logged.split(' ',1)[1])
                self.assertEqual(values['sampledRecords'],8)
                self.assertEqual(values['fields'][0]['field'],'decisionContext')
                self.assertIsNone(values['diskBytesFreed'])
                self.assertNotIn('private-account-key',logged)
                self.assertNotIn('payload',logged)
        finally:
            storage_layout._DECISION_LOGGED=before


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DecisionProductsCohortTests(unittest.TestCase):
    def test_age_windows_are_bounded_read_only_and_never_expose_products(self):
        import json
        import psycopg
        from psycopg.types.json import Jsonb
        schema='audit_cohort_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                conn.execute('''CREATE TABLE bob_decision_audit (
                    id text primary key, recorded_at timestamptz not null,
                    payload jsonb not null)''')
                conn.execute('CREATE INDEX cohort_time ON bob_decision_audit(recorded_at,id)')
                for i in range(48):
                    products=[] if i%5==0 else [{'isin':'SECRET_ISIN_'+str(i%3),
                         'price':9007199254740993,'note':'private-evidence'}]
                    conn.execute("""INSERT INTO bob_decision_audit
                        VALUES(%s,now()-(%s*interval '1 day'),%s)""",
                        (str(i),48-i,Jsonb({'products':products,
                                            'marketEvaluable':True,
                                            'privateValue':'do-not-export'})))
                original=conn.execute('SELECT id,payload FROM bob_decision_audit ORDER BY id').fetchall()
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    sample=storage_layout.decision_products_cohorts(conn)
                self.assertEqual(sample['status'],'sampled')
                self.assertEqual(sample['maxSelectedRows'],32)
                self.assertEqual(sample['method'],'indexed-four-age-windows-max-eight-rows-each')
                groups={x['ageWindow']:x for x in sample['cohorts']}
                self.assertEqual(set(groups),{'oldest','newest','before-24h','before-7d'})
                self.assertTrue(all(group['selectedRows']==8 for group in groups.values()))
                self.assertLessEqual(sample['uniqueSampledRecords'],32)
                self.assertGreaterEqual(sample['uniqueSampledRecords'],16)
                for group in groups.values():
                    self.assertLessEqual(group['nonEmptyProductRows'],group['selectedRows'])
                    self.assertLessEqual(group['distinctNonEmptyArrays'],group['nonEmptyProductRows'])
                    self.assertLessEqual(group['productsJsonTextBytes'],group['totalJsonTextBytes'])
                    self.assertGreater(group['totalJsonTextBytes'],0)
                self.assertIsNone(sample['reclaimableBytes'])
                summary=json.dumps(sample)
                for sensitive in ('SECRET_ISIN','9007199254740993','private-evidence','do-not-export'):
                    self.assertNotIn(sensitive,summary)
                self.assertEqual(conn.execute('SELECT id,payload FROM bob_decision_audit ORDER BY id').fetchall(),original)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_no_rows_and_missing_audit_are_distinguished(self):
        import psycopg
        schema='audit_cohort_empty_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                conn.execute('CREATE TABLE bob_decision_audit (id text primary key,recorded_at timestamptz,payload jsonb)')
                result=storage_layout.decision_products_cohorts(conn)
                self.assertEqual(result['status'],'empty')
                self.assertEqual(result['uniqueSampledRecords'],0)
                self.assertEqual(result['cohorts'],[])
                conn.execute('DROP TABLE bob_decision_audit')
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    result=storage_layout.decision_products_cohorts(conn)
                self.assertEqual(result['status'],'not-observed')
                self.assertEqual(conn.execute('SELECT 1').fetchone()[0],1)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')
