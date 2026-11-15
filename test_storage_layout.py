import os
import unittest
import uuid
import storage_layout


class BoundedCatalogReadTests(unittest.TestCase):
    def test_global_physical_size_sort_is_replaced_with_finite_catalog_candidates(self):
        from contextlib import nullcontext
        from unittest.mock import patch

        class Cursor:
            def __init__(self, rows): self.rows = rows
            def fetchall(self): return self.rows

        class Conn:
            def __init__(self): self.queries = []
            def transaction(self): return nullcontext()
            def execute(self, sql):
                self.queries.append(sql)
                if 'WITH relation_candidates AS MATERIALIZED' in sql:
                    return Cursor([('bob_fixture', 100, 40, 20, 30)])
                if 'WITH index_candidates AS MATERIALIZED' in sql:
                    return Cursor([('bob_fixture', 'bob_fixture_idx', 20, True)])
                raise AssertionError('Unexpected optional SQL')

        conn = Conn()
        readers = ('diagnostic_sample', 'recent_diagnostic_stages',
                   'diagnostic_payload_equality_sample',
                   'diagnostic_payload_byte_sample',
                   'decision_payload_sample', 'decision_products_cohorts')
        with patch.multiple(storage_layout, **{name: unittest.mock.DEFAULT for name in readers}) as mocked:
            for reader in mocked.values():
                reader.return_value = {'status': 'not-observed'}
            data = storage_layout.report(conn)

        self.assertEqual(len(conn.queries), 2)
        self.assertEqual(data['status'], 'observed')
        self.assertEqual(data['tables'][0]['totalBytes'], 100)
        self.assertEqual(data['tables'][0]['otherBytes'], 10)
        self.assertEqual(data['relationCandidateCap'], 24)
        self.assertEqual(data['indexCandidateCap'], 30)
        self.assertFalse(data['globalTopNVerified'])
        self.assertEqual(data['selectionScope'],
                         'catalog-ranked-candidates-not-global-top-n')
        rel, idx = conn.queries
        self.assertIn('WITH relation_candidates AS MATERIALIZED', rel)
        self.assertIn('LEFT JOIN pg_class t ON t.oid=c.reltoastrelid', rel)
        self.assertIn('ORDER BY estimated_pages DESC,c.relname LIMIT 24', rel)
        self.assertIn('WITH index_candidates AS MATERIALIZED', idx)
        self.assertIn('ORDER BY c.relpages DESC,c.relname LIMIT 30', idx)
        self.assertNotIn('ORDER BY pg_total_relation_size(c.oid)', rel)
        self.assertNotIn('ORDER BY pg_relation_size(c.oid)', idx)

    def test_decision_queries_have_distinct_log_markers_without_raw_payloads(self):
        import inspect
        a = inspect.getsource(storage_layout.decision_payload_sample)
        b = inspect.getsource(storage_layout.decision_products_cohorts)
        self.assertIn('bob_storage_layout:decision_payload_sample', a)
        self.assertIn('bob_storage_layout:decision_products_cohorts', b)
        self.assertNotIn('bob_storage_layout:decision_products_cohorts', a)
        self.assertNotIn('bob_storage_layout:decision_payload_sample', b)


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


class DiagnosticStageSampleTests(unittest.TestCase):
    def test_index_bounded_sample_is_not_day_writes_or_payloads(self):
        from contextlib import nullcontext
        import json

        class Conn:
            def __init__(self):
                self.sql = None
                self.params = None

            def transaction(self):
                return nullcontext()

            def execute(self, sql, params):
                self.sql, self.params = sql, params
                return self

            def fetchall(self):
                return [('analysis', 310), ('health', 120), ('input', 82)]

        conn = Conn()
        result = storage_layout.recent_diagnostic_stages(conn)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['sampledRows'], 512)
        self.assertTrue(result['moreOlderEventsMayExist'])
        self.assertEqual(result['stages'][0]['persistedSampleRows'], 310)
        self.assertEqual(conn.params, (512,))
        self.assertIn('ORDER BY recorded_at DESC LIMIT %s', conn.sql)
        self.assertNotIn('payload', conn.sql)
        self.assertNotIn('trace_id', conn.sql)
        self.assertIn('neither 24h INSERT counters', result['note'])
        self.assertNotIn('secret-private-payload', json.dumps(result))

    def test_untrusted_stage_or_failure_is_not_published(self):
        from contextlib import nullcontext
        class Conn:
            def __init__(self, rows=None, fail=False):
                self.rows, self.fail = rows, fail
            def transaction(self):
                return nullcontext()
            def execute(self, *_):
                if self.fail:
                    raise RuntimeError('secret-private-payload')
                return self
            def fetchall(self):
                return self.rows

        for rows in ([('secret-private-payload', 1)], [('analysis', -1)],
                     [('analysis', 513)], [('analysis', True)]):
            with self.subTest(rows=rows):
                self.assertEqual(storage_layout.recent_diagnostic_stages(Conn(rows))['status'],
                                 'not-observed')
        self.assertEqual(storage_layout.recent_diagnostic_stages(Conn(fail=True)),
                         {'status': 'not-observed', 'readOnly': True})
        empty = storage_layout.recent_diagnostic_stages(Conn([]))
        self.assertEqual(empty['status'], 'observed-empty')
        self.assertEqual(empty['sampledRows'], 0)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DiagnosticStagePostgresTests(unittest.TestCase):
    def test_original_events_unchanged_and_missing_table_fail_closed(self):
        import psycopg
        schema = 'diagstage_' + uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'], autocommit=True) as c:
            c.execute('CREATE SCHEMA ' + schema)
            try:
                c.execute('SET search_path TO ' + schema)
                c.execute('''CREATE TABLE bob_diagnostic_history (
                    id INT PRIMARY KEY, stage TEXT NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    observed_at DOUBLE PRECISION, payload JSONB NOT NULL)''')
                c.execute('''CREATE INDEX diagstage_recent_time
                    ON bob_diagnostic_history(recorded_at DESC)''')
                c.execute('''INSERT INTO bob_diagnostic_history(id,stage,observed_at,payload)
                    SELECT i,CASE WHEN i<=12 THEN 'input' ELSE 'analysis' END,
                           1793620800 + i,jsonb_build_object('private','never-export')
                    FROM generate_series(1,30) AS i''')
                original = c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall()
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    result = storage_layout.recent_diagnostic_stages(c)
                self.assertEqual(result['status'], 'observed')
                self.assertEqual(result['sampledRows'], 30)
                self.assertFalse(result['moreOlderEventsMayExist'])
                self.assertEqual({x['stage']: x['persistedSampleRows']
                                  for x in result['stages']}, {'analysis': 18, 'input': 12})
                self.assertNotIn('never-export', str(result))
                self.assertEqual(c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall(),
                                 original)
                c.execute('DROP TABLE bob_diagnostic_history')
                self.assertEqual(storage_layout.recent_diagnostic_stages(c)['status'],
                                 'not-observed')
            finally:
                c.execute('DROP SCHEMA ' + schema + ' CASCADE')


class DiagnosticJsonbEqualityTests(unittest.TestCase):
    def test_aggregate_only_bounded_metadata_with_no_original_values(self):
        from contextlib import nullcontext
        import json

        class Conn:
            def __init__(self):
                self.queries = []
            def transaction(self):
                return nullcontext()
            def execute(self, sql, params=None):
                self.queries.append((sql, params))
                return self
            def fetchall(self):
                return [('analysis', 85, 65, 20, 2),
                        ('input', 105, 20, 85, 7)]

        c = Conn()
        x = storage_layout.diagnostic_payload_equality_sample(c)
        self.assertEqual(x['status'], 'sampled')
        self.assertEqual(x['eligibleSampledRows'], 190)
        self.assertEqual(x['sampleCapAllStages'], 256)
        self.assertIsNone(x['diskBytesFreed'])
        self.assertFalse(x['migrationAuthorized'])
        self.assertEqual(x['stages'][1]['repeatedStoredJsonbRows'], 85)
        self.assertEqual(x['stages'][1]['sameTraceTimeAndJsonbExtraRows'], 7)
        self.assertEqual(c.queries[1][1], (256, ['input', 'analysis']))
        self.assertIn('ORDER BY recorded_at DESC LIMIT %s', c.queries[1][0])
        self.assertIn('GROUP BY stage,payload,trace_id,observed_at', c.queries[1][0])
        self.assertTrue(c.queries[0][0].startswith('SET LOCAL statement_timeout'))
        result_text = json.dumps(x)
        for private in ('trace_id', 'observed_at', 'raw-payload', 'secret-token'):
            self.assertNotIn(private, result_text)

    def test_empty_bad_values_and_query_failure_are_fail_closed(self):
        from contextlib import nullcontext
        class Conn:
            def __init__(self, rows, fail=False):
                self.rows, self.fail = rows, fail
            def transaction(self):
                return nullcontext()
            def execute(self, *_):
                if self.fail:
                    raise RuntimeError('private-source-value')
                return self
            def fetchall(self):
                return self.rows

        self.assertEqual(storage_layout.diagnostic_payload_equality_sample(
            Conn([]))['status'], 'observed-empty')
        for bad in ([('private-stage', 2, 1, 1, 0)],
                    [('input', 4, 2, 1, 0)],
                    [('input', 4, 2, 2, 3)],
                    [('input', 257, 256, 1, 0)],
                    [('input', True, 1, 0, 0)],
                    [('input', -1, 1, 0, 0)]):
            with self.subTest(rows=bad):
                self.assertEqual(storage_layout.diagnostic_payload_equality_sample(
                    Conn(bad)), {'status': 'not-observed', 'readOnly': True})
        self.assertEqual(storage_layout.diagnostic_payload_equality_sample(
            Conn([], fail=True)), {'status': 'not-observed', 'readOnly': True})


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DiagnosticEqualityPostgresTests(unittest.TestCase):
    def test_equality_is_not_duplicate_event_and_keeps_source_byte_values(self):
        import json
        import psycopg
        from psycopg.types.json import Jsonb

        schema = 'diag_equal_' + uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'], autocommit=True) as c:
            c.execute('CREATE SCHEMA ' + schema)
            try:
                c.execute('SET search_path TO ' + schema)
                c.execute('''CREATE TABLE bob_diagnostic_history (
                    id INT PRIMARY KEY, stage TEXT NOT NULL, trace_id TEXT NOT NULL,
                    observed_at DOUBLE PRECISION NOT NULL, recorded_at
                    TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL)''')
                c.execute('CREATE INDEX diag_equal_recent ON bob_diagnostic_history(recorded_at DESC)')
                rows = [
                    (1, 'input', 'trace-a', 101, {'private': 'never-export', 'value': 1}),
                    (2, 'input', 'trace-b', 102, {'value': 1, 'private': 'never-export'}),
                    (3, 'input', 'trace-a', 101, {'private': 'never-export', 'value': 1}),
                    (4, 'analysis', 'trace-a', 101, {'direction': 'LONG'}),
                    (5, 'analysis', 'trace-b', 102, {'direction': 'LONG'}),
                    (6, 'health', 'trace-a', 101, {'private': 'never-export'}),
                ]
                for ident, stage, trace, at, payload in rows:
                    c.execute('''INSERT INTO bob_diagnostic_history
                        (id,stage,trace_id,observed_at,payload)
                        VALUES (%s,%s,%s,%s,%s)''',
                        (ident, stage, trace, at, Jsonb(payload)))
                before = c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall()
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    sample = storage_layout.diagnostic_payload_equality_sample(c)
                self.assertEqual(sample['status'], 'sampled')
                self.assertEqual(sample['eligibleSampledRows'], 5)
                parsed = {s['stage']: s for s in sample['stages']}
                self.assertEqual(parsed['input']['sampledRows'], 3)
                self.assertEqual(parsed['input']['distinctStoredJsonbPayloads'], 1)
                self.assertEqual(parsed['input']['repeatedStoredJsonbRows'], 2)
                self.assertEqual(parsed['input']['sameTraceTimeAndJsonbExtraRows'], 1)
                self.assertEqual(parsed['analysis']['repeatedStoredJsonbRows'], 1)
                self.assertEqual(parsed['analysis']['sameTraceTimeAndJsonbExtraRows'], 0)
                self.assertNotIn('never-export', json.dumps(sample))
                self.assertNotIn('trace-a', json.dumps(sample))
                self.assertEqual(c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall(), before)
                c.execute('DROP TABLE bob_diagnostic_history')
                self.assertEqual(storage_layout.diagnostic_payload_equality_sample(c)['status'],
                                 'not-observed')
            finally:
                c.execute('DROP SCHEMA ' + schema + ' CASCADE')


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
                self.assertEqual(sample['maxSelectedRows'],48)
                self.assertEqual(sample['method'],'indexed-six-age-windows-max-eight-rows-each')
                groups={x['ageWindow']:x for x in sample['cohorts']}
                self.assertEqual(set(groups),{'oldest','newest','before-24h','before-7d','before-14d','before-30d'})
                self.assertTrue(all(group['selectedRows']==8 for group in groups.values()))
                self.assertLessEqual(sample['uniqueSampledRecords'],48)
                self.assertEqual(sample['boundedRecordCount'],48)
                self.assertFalse(sample['recordCountIsLowerBound'])
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
                self.assertEqual(result['boundedRecordCount'],0)
                self.assertFalse(result['recordCountIsLowerBound'])
                self.assertEqual(result['cohorts'],[])
                conn.execute('DROP TABLE bob_decision_audit')
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    result=storage_layout.decision_products_cohorts(conn)
                self.assertEqual(result['status'],'not-observed')
                self.assertEqual(conn.execute('SELECT 1').fetchone()[0],1)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')


    def test_row_count_caps_before_unbounded_archive_scan(self):
        import psycopg
        schema='audit_count_cap_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                conn.execute('''CREATE TABLE bob_decision_audit (
                    id text primary key, recorded_at timestamptz not null, payload jsonb not null)''')
                conn.execute('CREATE INDEX audit_count_time ON bob_decision_audit(recorded_at,id)')
                conn.execute("""INSERT INTO bob_decision_audit
                    SELECT i::text,now()-i*interval '1 minute','{"products":[]}'::jsonb
                    FROM generate_series(1,10021) i""")
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    result=storage_layout.decision_products_cohorts(conn)
                self.assertEqual(result['status'],'sampled')
                self.assertEqual(result['boundedRecordCount'],10001)
                self.assertTrue(result['recordCountIsLowerBound'])
                self.assertEqual(result['boundedRecordCountCap'],10001)
                self.assertLessEqual(result['uniqueSampledRecords'],48)
                self.assertIsNone(result['reclaimableBytes'])
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_audit').fetchone()[0],10021)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')
