"""Actual PostgreSQL durability, retry deduplication and atomic archive rollback."""
import os
import uuid
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import strategy_lab_store as store
import strategy_lab

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class RevisionStorageTests(unittest.TestCase):
    def test_revisions_survive_reconnect_and_failed_archive_rolls_back(self):
        import psycopg
        from psycopg import sql
        url=os.environ['BOB_TEST_DATABASE_URL']; schema='research_revision_'+uuid.uuid4().hex
        with psycopg.connect(url) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                store.init(conn)
                report=dict(mode='RESEARCH_ONLY',version=strategy_lab.VERSION,status='evaluated',
                    approved=False,orderExecutionEnabled=False,brokerConnected=False,
                    affectsLiveSignals=False,closedBars=650,rangeMs=[1700000000000,1701000000000])
                conn.execute("INSERT INTO bob_strategy_lab_daily VALUES ('2020-01-01',now(),1,'evaluated','old','{}')")
                with patch.object(store,'datetime',wraps=datetime) as dt:
                    dt.now.return_value=datetime(2026,10,12,9,tzinfo=ZoneInfo('Europe/Zurich'))
                    payload=dict(day='2026-10-12',report=report)
                    store.handle(conn,'write',payload)
                    store.handle(conn,'write',payload)
                    report['closedBars']=651
                    store.handle(conn,'write',payload)
                    conn.commit()
                    self.assertEqual(conn.execute('SELECT count(*) FROM bob_strategy_lab_revisions').fetchone()[0],2)
                    self.assertEqual(conn.execute('SELECT count(*) FROM bob_strategy_lab_daily').fetchone()[0],2)
                    conn.commit()
                    original=store.archive_current;calls=[]
                    def fail_second(db,day):
                        calls.append(day)
                        if len(calls)==2:raise RuntimeError('archive unavailable')
                        original(db,day)
                    report['closedBars']=652
                    with self.assertRaises(RuntimeError),patch.object(store,'archive_current',side_effect=fail_second):
                        with conn.transaction():store.handle(conn,'write',payload)
                with psycopg.connect(url) as reopened:
                    reopened.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                    self.assertEqual(reopened.execute("SELECT report->>'closedBars' FROM bob_strategy_lab_daily WHERE run_day='2026-10-12'").fetchone()[0],'651')
                    self.assertEqual(reopened.execute('SELECT count(*) FROM bob_strategy_lab_revisions').fetchone()[0],2)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()
