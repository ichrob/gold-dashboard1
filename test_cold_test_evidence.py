import copy
import os
from pathlib import Path
import re
import unittest
import uuid
from unittest.mock import patch
import cold_test_evidence as cold
import paper_entry_exit_comparison as engine
from test_cold_metrics import Drive


def sample():
    p = engine.seed({'ruleVersion':'synthetic-v1'}, {'analysisBarAt':1,'sourceAt':1}, 1, 'LONG')
    p.update(complete=True, checkedAt=2)
    for a in p['arms'].values():
        a.update(status='closed', modelNetEur=3., entryAt=1, exitAt=2,
            entryQuoteAt=1, exitQuoteAt=2, entryAsk=5., exitBid=6., entryDebit=20., units=4,
            choice={'isin':'SYNTHETIC'}, observedPeakPnlEur=4., observedTroughPnlEur=-1.,
            entryQuote={'originalInteger':9007199254740993,'details':'x'*400},
            exitQuote={'originalInteger':9007199254740993,'details':'y'*400},
            entryKoEvidence={'isin':'SYNTHETIC','source':'issuer'},
            exitKoEvidence={'isin':'SYNTHETIC','source':'issuer'},
            triggerBars=[],
            stopHistory=[{'stop':3,'bars':[{'close':4}]}]*20)
    return p


class PolicyTests(unittest.TestCase):
    def test_brief_exposes_counts_not_archive_locations(self):
        import storage_brief
        r=storage_brief.project({'status':'observed','coldTests':{
            'status':'observed','offloadedRows':2,'logicalJsonBytesReduced':1234,
            'fileId':'PRIVATE', 'lastCycle':{'status':'backup-proof-not-fresh','secret':'PRIVATE'}}})
        self.assertEqual(r['coldTests']['offloadedRows'],2)
        self.assertEqual(r['coldTests']['lastCycleStatus'],'backup-proof-not-fresh')
        self.assertNotIn('PRIVATE',str(r))

    def test_future_test_tables_must_join_reviewed_backup(self):
        import evidence_archive
        for module in ('paper_entry_exit_comparison.py','research_restart.py','paper_shadow_studies.py'):
            tables = set(re.findall(r'CREATE TABLE IF NOT EXISTS (bob_\w+)',Path(module).read_text()))
            self.assertTrue(tables <= evidence_archive.selected_tables(), (module, tables))
        self.assertTrue(cold.BACKUP_TABLES <= evidence_archive.selected_tables())

    def test_open_hot_unknown_and_incomplete_are_never_eligible(self):
        p = sample(); now = 2*86400000
        self.assertTrue(cold.eligible(p,now))
        for changes in ({'complete':False},{'checkedAt':now},{'version':'future-v2'}):
            self.assertFalse(cold.eligible({**p,**changes},now))
        p['arms'][engine.ARMS[0]]['status']='open'
        self.assertFalse(cold.eligible(p,now))

    def test_closed_case_missing_exit_ko_original_is_not_eligible(self):
        p=sample();now=2*86400000
        p['arms'][engine.ARMS[0]].pop('exitKoEvidence')
        self.assertFalse(cold.eligible(p,now))

    def test_projection_keeps_evaluation_and_unknown_fields(self):
        p=sample(); p['futureMetadata']={'x':2}; before=copy.deepcopy(p)
        projected=cold.projection(p)
        self.assertEqual(p,before)
        self.assertEqual(projected['futureMetadata'],p['futureMetadata'])
        for key,a in p['arms'].items():
            self.assertEqual(projected['arms'][key],{k:v for k,v in a.items() if k not in cold.DETAILS})


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.c=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True)
        self.schema='test_cold_tests_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+self.schema)
        self.c.execute('SET search_path TO '+self.schema)
        engine.init(self.c);cold.init(self.c)
        self.drive=Drive();self.p=sample()
        self.secret=patch.dict(os.environ,{'PUSH_SERVICE_TOKEN':'synthetic-test-only-secret-'+('x'*32)})
        self.secret.start()
        for key,complete,payload in [('old',True,self.p),('active',False,self.p),('hot',True,{**self.p,'checkedAt':2*86400000})]:
            self.c.execute('INSERT INTO bob_entry_exit_comparison VALUES(%s,%s,%s::jsonb)',(key,complete,cold.codec.encoded(payload).decode()))

    def tearDown(self):
        self.secret.stop();self.c.execute('DROP SCHEMA '+self.schema+' CASCADE');self.c.close()

    def evaluate(self):
        import paper_comparison_report as report
        with self.c.transaction():
            return report.report(self.c)

    def test_round_trip_preserves_both_reports_and_full_original(self):
        before=self.evaluate();summary=engine.report(self.c)
        result=cold.offload_batch(self.c,self.drive,now_ms=2*86400000)
        self.assertEqual(result['movedRows'],1)
        self.assertGreater(result['originalJsonBytes'],result['referenceJsonBytes'])
        self.assertIsNone(result['physicalBytesFreed'])
        self.assertEqual(self.evaluate(),before)
        self.assertEqual(engine.report(self.c),summary)
        self.assertTrue(all(blob.startswith(b'BOBCOLD1') for blob in self.drive.files.values()))
        cold.codec._CACHE.clear()
        self.assertEqual(cold.get(self.c,'old',drive=self.drive),self.p)
        for key in ('hot','active'):
            self.assertNotIn(cold.TAG,self.c.execute('SELECT payload FROM bob_entry_exit_comparison WHERE id=%s',(key,)).fetchone()[0])
        self.drive.corrupt=True
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.get(self.c,'old',drive=self.drive)
        # Results remain locally readable during a Drive outage; originals fail explicitly.
        self.assertEqual(self.evaluate(),before)

    def test_long_mixed_history_retains_full_stream_and_local_preview(self):
        # Fast preview stays bounded, while the independent streaming
        # evaluation retains all older and new no-entry cases.
        import json
        original = engine.report(self.c)
        self.assertEqual(original['episodesSampled'],3)
        no_entry = dict(version=engine.VERSION, complete=True, checkedAt=2,
            ruleVersion='synthetic-v1', startedAt=2, direction='LONG',
            arms={arm:dict(status='no-entry',reason='no-valid-entry')
                  for arm in engine.ARMS})
        for i in range(205):
            self.c.execute('''INSERT INTO bob_entry_exit_comparison
                VALUES(%s,TRUE,%s::jsonb)''',
                ('small-no-entry-%03d'%i,json.dumps(no_entry)))
        baseline = engine.report(self.c)
        self.assertEqual(baseline['episodesSampled'],200)
        self.assertEqual(baseline['variants'][engine.ARMS[0]]['no-entry'],200)
        self.assertTrue(baseline['truncated'])
        self.assertEqual(baseline['sourceScope'],'recent-200-preview-only')
        complete_before=self.evaluate()
        self.assertEqual(complete_before['episodes'],208)
        self.assertEqual(cold.offload_batch(self.c,self.drive,
            now_ms=2*86400000)['movedRows'],1)
        self.assertEqual(engine.report(self.c),baseline)
        self.assertEqual(self.evaluate(),complete_before)
        self.drive.corrupt=True
        # Drive outage prevents original-detail restore but not local
        # results, including old cases absent from the bounded preview.
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):
            cold.get(self.c,'old',drive=self.drive)
        self.assertEqual(engine.report(self.c),baseline)
        self.assertEqual(self.evaluate(),complete_before)
        self.assertEqual(self.c.execute(
            'SELECT count(*) FROM bob_entry_exit_comparison').fetchone()[0],208)

    def test_bad_download_does_not_change_original(self):
        self.drive.corrupt=True
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.offload_batch(self.c,self.drive,now_ms=2*86400000)
        self.assertEqual(cold.get(self.c,'old'),self.p)
        self.assertEqual(self.c.execute('SELECT count(*) FROM bob_cold_test_batches').fetchone()[0],0)

    def test_concurrent_update_is_not_overwritten(self):
        def change():
            self.c.execute("UPDATE bob_entry_exit_comparison SET complete=FALSE WHERE id='old'")
        self.drive.on_upload=change
        self.assertEqual(cold.offload_batch(self.c,self.drive,now_ms=2*86400000)['movedRows'],0)
        self.assertEqual(cold.get(self.c,'old'),self.p)

    def test_bad_readthrough_rolls_back(self):
        with patch.object(cold,'resolve',side_effect=cold.codec.ColdArchiveUnavailable):
            with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.offload_batch(self.c,self.drive,now_ms=2*86400000)
        self.assertEqual(cold.get(self.c,'old'),self.p)
        self.assertEqual(self.c.execute('SELECT count(*) FROM bob_cold_test_batches').fetchone()[0],0)
