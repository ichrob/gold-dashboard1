import io
import json
import os
import unittest
import uuid
from unittest.mock import patch
import storage_budget as budget


class BudgetTests(unittest.TestCase):
    def test_headroom_thresholds_do_not_claim_full_disk_measurement(self):
        self.assertEqual(budget.state(435_000_000),'below-budget-threshold')
        self.assertEqual(budget.state(2_500_000_000),'caution')
        self.assertEqual(budget.state(3_500_000_000),'action-required')
        self.assertLess(budget.ACTION_BYTES,budget.ALLOCATION_BYTES)

    def test_archive_status_uses_sanitized_persisted_result(self):
        class Conn:
            def execute(self, sql):
                return self
            def fetchone(self):
                return ('verified','2026-10-30 17:20:00+00:00',{
                    'status':'verified','evidenceDeleted':False,
                    'receipt':{'restoreVerified':True,'remoteDownloadVerified':True,
                               'deletionPermitted':False,'driveFileId':'private-file-id'}})
        with patch('archive_worker.status',return_value={'status':'already-attempted-today'}):
            result=budget.archive_status(Conn())
        self.assertEqual(result['status'],'already-attempted-today')
        self.assertEqual(result['latestPersistedAttempt']['status'],'verified')
        self.assertTrue(result['latestPersistedAttempt']['restoreVerified'])
        self.assertTrue(result['latestPersistedAttempt']['remoteDownloadVerified'])
        self.assertFalse(result['latestPersistedAttempt']['deletionPermitted'])
        self.assertNotIn('private-file-id',str(result))

    def test_interrupted_claim_does_not_hide_last_verified_restore(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        last = now - timedelta(minutes=20)
        prior = now - timedelta(hours=19)
        class Conn:
            def __init__(self):
                self.calls = []
            def execute(self, sql):
                self.calls.append(sql)
                return self
            def fetchone(self):
                if "WHERE status='verified'" in self.calls[-1]:
                    return ('verified',prior.isoformat(),{
                        'receipt':{'restoreVerified':True,
                                   'remoteDownloadVerified':True,
                                   'driveFileId':'sensitive-drive-id'},
                        'evidenceDeleted':False})
                return ('running',last.isoformat(),{
                    'status':'running','phase':None,
                    'stagedFileId':'private-unverified-file'})
        with patch('archive_worker.status',return_value={'status':'already-attempted-today'}):
            result=budget.archive_status(Conn())
        self.assertEqual(result['latestPersistedAttempt']['status'],'running')
        self.assertEqual(result['latestVerifiedAttempt']['status'],'verified')
        self.assertEqual(result['incompleteClaimReview'],'nonterminal-overdue')
        self.assertTrue(result['latestVerifiedAttempt']['restoreVerified'])
        self.assertTrue(result['latestVerifiedAttempt']['remoteDownloadVerified'])
        self.assertNotIn('sensitive-drive-id',str(result))
        self.assertNotIn('private-unverified-file',str(result))

    def test_archive_status_falls_back_when_ledger_is_unavailable(self):
        class Conn:
            def execute(self, sql):
                raise RuntimeError('old schema')
        with patch('archive_worker.status',return_value={'status':'disabled'}) as status:
            self.assertEqual(budget.archive_status(Conn()),{'status':'disabled'})
            status.assert_called_once_with()

    def test_storage_endpoint_requires_existing_service_auth(self):
        import push_server as p
        h=object.__new__(p.Handler);h.path='/storage-health';h.headers={};h.wfile=io.BytesIO()
        statuses=[];h.send_response=lambda status:statuses.append(status)
        h.send_header=lambda *_:None;h.end_headers=lambda:None
        with patch.object(p,'PUSH_SERVICE_TOKEN','test-only'),patch.object(p,'db',side_effect=AssertionError('unauthenticated read')):
            h.do_GET()
        self.assertEqual(statuses,[401])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class StorageInitLockTests(unittest.TestCase):
    @staticmethod
    def isolated_init(conn):
        # The other independent storage modules own different startup tables.
        # Only the bob_storage_samples startup lock is under test.
        import importlib
        from contextlib import ExitStack
        modules = ('storage_knowledge', 'storage_case_results',
                   'storage_history_evaluations', 'storage_paper_evaluation',
                   'storage_quality_evaluation', 'storage_improvement_evaluation')
        with ExitStack() as stack:
            for name in modules:
                stack.enter_context(patch.object(importlib.import_module(name), 'init'))
            budget.init(conn)

    def test_preexisting_columns_do_not_request_access_exclusive_lock(self):
        import psycopg
        from psycopg import sql
        schema = 'storage_init_lock_' + uuid.uuid4().hex
        url = os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(url) as setup:
            setup.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            setup.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            setup.execute('''CREATE TABLE bob_storage_samples (
                slot BIGINT PRIMARY KEY,
                sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                database_bytes BIGINT NOT NULL,
                relation_bytes JSONB NOT NULL DEFAULT '{}'::jsonb,
                writer_stats JSONB NOT NULL DEFAULT '{}'::jsonb,
                entry_exit_metrics JSONB NOT NULL DEFAULT '{}'::jsonb)''')
            setup.execute('INSERT INTO bob_storage_samples(slot,database_bytes) VALUES (1,123)')
            setup.commit()
        try:
            with psycopg.connect(url) as reader, psycopg.connect(url) as owner:
                reader.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                owner.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                reader.execute('LOCK TABLE bob_storage_samples IN ACCESS SHARE MODE')
                # A no-op ALTER TABLE ... ADD COLUMN IF NOT EXISTS would request
                # AccessExclusiveLock and would time out here. Catalog-only
                # initialization must complete while the reader remains open.
                owner.execute("SET LOCAL lock_timeout='300ms'")
                self.isolated_init(owner)
                self.assertEqual(owner.execute('SELECT database_bytes FROM bob_storage_samples').fetchone()[0],123)
                owner.commit()
                reader.commit()
        finally:
            with psycopg.connect(url, autocommit=True) as cleanup:
                cleanup.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    def test_old_schema_migrates_only_missing_fields_without_losing_rows(self):
        import psycopg
        from psycopg import sql
        schema = 'storage_init_upgrade_' + uuid.uuid4().hex
        url = os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('''CREATE TABLE bob_storage_samples (
                    slot BIGINT PRIMARY KEY,
                    sampled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    database_bytes BIGINT NOT NULL)''')
                conn.execute('INSERT INTO bob_storage_samples(slot,database_bytes) VALUES (22,789)')
                self.isolated_init(conn)
                row = conn.execute('''SELECT database_bytes,relation_bytes,writer_stats,
                                      entry_exit_metrics FROM bob_storage_samples
                                      WHERE slot=22''').fetchone()
                self.assertEqual(row,(789,{},{},{}))
                self.isolated_init(conn)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_storage_samples').fetchone()[0],1)
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class StorageTests(unittest.TestCase):
    def test_evidence_preservation_deduplication_and_readonly_size_report(self):
        import psycopg
        from psycopg import sql
        schema='storage_budget_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                budget.init(conn)
                columns={row[0] for row in conn.execute('''SELECT column_name FROM information_schema.columns
                    WHERE table_schema=current_schema() AND table_name='bob_storage_samples' ''').fetchall()}
                self.assertIn('relation_bytes',columns)
                self.assertIn('writer_stats',columns)
                conn.execute('CREATE TABLE bob_decision_audit (id INT PRIMARY KEY,payload JSONB)')
                payload={'observations':[{'source':'gold-reference','value':4000,'valid':True} for _ in range(12)]}
                conn.execute('INSERT INTO bob_decision_audit VALUES (1,%s::jsonb)',(json.dumps(payload),))
                conn.execute('INSERT INTO bob_decision_audit VALUES (2,%s::jsonb)',(json.dumps(payload),))
                self.assertEqual(conn.execute('SELECT payload FROM bob_decision_audit WHERE id=2').fetchone()[0],payload)
                with patch.object(budget,'_NEXT',0):budget.maybe_observe(conn,1_800_000_000)
                with patch.object(budget,'_NEXT',0):budget.maybe_observe(conn,1_800_001_800)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_storage_samples').fetchone()[0],2)
                writer_row=conn.execute('SELECT writer_stats FROM bob_storage_samples ORDER BY slot DESC LIMIT 1').fetchone()[0]
                self.assertIsInstance(writer_row,dict)
                self.assertLessEqual(len(writer_row),10)
                self.assertNotIn('bob_settings',writer_row)
                # Telemetry retention never touches test data.
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_audit').fetchone()[0],2)
                import candle_reliability as candles_store
                from test_ema200_history_backfill import candle_series
                candles_store.init(conn)
                bars=candle_series(3,step=60000)
                for bar in bars:bar['source']=candles_store.SOURCES['biquote']
                candles_store.handle(conn,'write',dict(key='biquote/1m',rows=bars))
                location=conn.execute('SELECT ctid FROM bob_candle_checkpoints').fetchone()[0]
                candles_store.handle(conn,'write',dict(key='biquote/1m',rows=bars))
                self.assertEqual(conn.execute('SELECT ctid FROM bob_candle_checkpoints').fetchone()[0],location)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_candle_evidence').fetchone()[0],3)
                conn.commit();conn.execute('SET TRANSACTION READ ONLY')
                result=budget.report(conn)
                self.assertTrue(result['readOnly'])
                # Existing archiveWorker is a projected private field; ensure
                # one-batch readiness survives without turning other archives
                # into an independently verified original PNG backup.
                image = result['archiveWorker']['originalImageBackupReadiness']
                self.assertEqual(image,result['androidImageBackupReadiness'])
                self.assertTrue(image['readOnly'])
                self.assertIsNone(image['remoteOriginalBatchBackupVerified'])
                self.assertIsNone(image['independentOriginalBatchRestoreVerified'])
                self.assertFalse(image['originalImageDeletionAuthorized'])
                self.assertIsNone(image['diskBytesFreed'])
                self.assertFalse(result['evidenceDeleted'])
                self.assertEqual(result['growthStatus'],'needs-at-least-24-hours')
                self.assertEqual(result['relationGrowthStatus'],'observed')
                self.assertEqual(result['relationElapsedSeconds'],1800)
                # An unchanged relation can fall outside the top twelve as
                # new evaluation tables are added. Verify complete stored
                # snapshots, then independently check the bounded ranking.
                snapshots=conn.execute('''SELECT relation_bytes FROM
                    bob_storage_samples ORDER BY slot''').fetchall()
                before,after=(row[0] for row in snapshots)
                self.assertIn('bob_decision_audit',before)
                self.assertIn('bob_decision_audit',after)
                self.assertEqual(before['bob_decision_audit'],after['bob_decision_audit'])
                expected=[dict(table=name,bytesBefore=before[name],
                    bytesAfter=after[name],bytesDelta=after[name]-before[name])
                    for name in before.keys() & after.keys()]
                expected.sort(key=lambda item:(abs(item['bytesDelta']),item['table']),reverse=True)
                self.assertEqual(result['largestTableDeltas'],expected[:12])
                self.assertIn('not-total-disk',result['scope'])
                self.assertEqual(result['storageForensics']['status'],'observed')
                self.assertTrue(result['storageForensics']['readOnly'])
                self.assertIsNone(result['storageForensics']['reclaimableBytes'])
                self.assertFalse(result['storageForensics']['rebuildAuthorized'])
                self.assertIn(result['storageForensics']['day']['status'],('observed','no-common-relations','needs-24h-pair'))
                conn.commit()
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()
