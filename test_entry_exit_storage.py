"""Redacted fixed-window footprint tests; no archive or trading mutations."""
import json
import os
import unittest
import uuid

import entry_exit_storage as footprint
import storage_brief


class Conn:
    def __init__(self):
        self.calls=[]
    def execute(self,sql,args=()):
        self.calls.append((sql,args));return self
    def fetchone(self):
        sql=self.calls[-1][0]
        if 'pg_relation_size(c.oid)' in sql:return (8192,16384,40960,16384)
        if 'count(*)' in sql:return (2,1,1,6000,4000,2000,0)
        raise AssertionError(sql)
    def fetchall(self):
        return [('closed',18),('open',18)]


def metrics(total,logical,cases=1,complete=1,open_=0):
    return {'totalBytes':total,'heapBytes':total//4,'indexBytes':total//4,
        'toastBytes':total//2,'otherBytes':0,'episodes':cases,
        'completeEpisodes':complete,'openEpisodes':open_,'archivedEpisodes':0,
        'logicalPayloadBytes':logical,'completeLogicalPayloadBytes':logical,
        'openLogicalPayloadBytes':0}


def row(slot,database,relation,parts=None):
    return (slot,database,{footprint.TABLE:relation},{},parts or {},
            '2026-11-05 00:00:00+00:00')


class FootprintTests(unittest.TestCase):
    START=1793862000  # 2026-11-05 08:00 Europe/Zurich
    END=1793912400    # 2026-11-05 22:00 Europe/Zurich

    def test_existing_relation_slots_are_exact_but_parts_are_not_invented(self):
        result=footprint.report(Conn(),[
            row(self.START,700000000,24576),row(self.END,710000000,57344)],
            now=self.END+1)
        day=result['firstCompletedTradeDay']
        self.assertTrue(day['exact'])
        self.assertEqual(day['relationBytesDelta'],32768)
        self.assertEqual(day['databaseBytesDelta'],10000000)
        self.assertEqual(day['components']['status'],'needs-fixed-endpoint-measurement')
        self.assertIsNone(day['components']['deltas'])
        self.assertEqual(result['current']['toastBytes'],16384)
        self.assertEqual(result['completeLogicalBytesPerCase'],4000)
        self.assertNotIn('private-id',json.dumps(result).lower())

    def test_new_fixed_endpoint_parts_measure_each_component_and_logical_growth(self):
        result=footprint.report(Conn(),[
            row(self.START,700000000,40000,metrics(40000,3000)),
            row(self.END,701000000,60000,metrics(60000,9000,2,1,1))],
            now=self.END+1)
        parts=result['firstCompletedTradeDay']['components']
        self.assertEqual(parts['status'],'observed')
        self.assertEqual(parts['deltas']['totalBytes'],20000)
        self.assertEqual(parts['deltas']['logicalPayloadBytes'],6000)
        self.assertEqual(parts['deltas']['episodes'],1)

    def test_missing_endpoint_is_explicit_and_brief_is_bounded(self):
        raw=footprint.report(Conn(),[row(self.START,700000000,40000)],now=self.END+1)
        self.assertEqual(raw['firstCompletedTradeDay']['status'],'missing-endpoint')
        brief=storage_brief.project({'status':'observed','entryExitStorage':raw})['entryExitStorage']
        self.assertFalse(brief['firstCompletedTradeDay']['exact'])
        self.assertIsNone(brief['firstCompletedTradeDay']['relationBytesDelta'])
        self.assertIsNone(brief['physicalBytesFreed'])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_fixed_sample_has_exact_counts_and_no_original_values(self):
        import psycopg
        from psycopg import sql
        import paper_entry_exit_comparison as engine
        schema='entry_exit_storage_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                engine.init(conn)
                payload=engine.seed({'ruleVersion':'r'},
                    {'analysisBarAt':1,'sourceAt':1},1,'LONG')
                conn.execute('INSERT INTO bob_entry_exit_comparison VALUES(%s,FALSE,%s::jsonb)',
                             ('private-id',json.dumps(payload)))
                measured=footprint.sample(conn)
                self.assertEqual(measured['episodes'],1)
                self.assertEqual(measured['openEpisodes'],1)
                self.assertGreater(measured['totalBytes'],0)
                self.assertNotIn('private-id',json.dumps(measured))
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()


if __name__=='__main__':unittest.main()
