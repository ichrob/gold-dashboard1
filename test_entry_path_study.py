import unittest
from entry_path_study import evaluate,PROTOCOL

class PathTests(unittest.TestCase):
    def setUp(self):
        self.at=1800000000000
        self.base=self.row(0,4000)
    def row(self,minutes,price,**kw):
        return dict(dict(at=self.at+minutes*60000,priceAt=self.at+minutes*60000,price=price,valid=True,ready=True,direction='LONG',cohort='v1'),**kw)
    def test_fixed_filter_and_horizons_costs(self):
        rows=[self.row(-15,3980),self.row(-5,3990)]+[self.row(m,4010) for m in PROTOCOL['horizons']]
        r=evaluate(self.base,rows,self.at+3700000)
        self.assertFalse(r['candidateKeep']);self.assertEqual(len(r['horizons']),4)
        self.assertEqual(r['comparison'][0]['candidate'],0)
        self.assertAlmostEqual(r['comparison'][0]['baseline'],.21)
        self.assertGreater(r['earlierComparison'][0]['earlier'],r['earlierComparison'][0]['baseline'])
    def test_future_wrong_version_and_stale_do_not_fill_gaps(self):
        for bad in [self.row(60,4010,at=self.at+4000000),self.row(60,4010,cohort='other'),self.row(62,4010)]:
            r=evaluate(self.base,[bad],self.at+3900000)
            self.assertEqual(r['horizons'][-1]['status'],'missing')
            self.assertFalse(r['comparison'])
    def test_short_direction_extrema_and_gaps(self):
        base=dict(self.base,direction='SHORT')
        rows=[self.row(-15,4020),self.row(10,4040),self.row(60,3960)]
        r=evaluate(base,rows,self.at+3800000)
        self.assertFalse(r['candidateKeep']);self.assertAlmostEqual(r['observedAdversePct'],-1)
        self.assertAlmostEqual(r['observedFavorablePct'],1)
        self.assertLess(r['coveragePct'],5)
        self.assertEqual(r['horizons'][0]['status'],'missing')
    def test_neutral_early_false_alarm_and_no_hindsight_direction(self):
        base=dict(self.base,ready=False,direction='NEUTRAL')
        r=evaluate(base,[self.row(-5,4010),self.row(60,3990)],self.at+3800000)
        self.assertFalse(r['comparison']);self.assertIsNone(r['horizons'][-1]['directionalPct'])
        self.assertLess(r['earlierComparison'][0]['earlier'],0)
        self.assertEqual(r['earlierComparison'][0]['baseline'],0)
    def test_missing_prior_is_unknown_not_keep(self):
        r=evaluate(self.base,[self.row(60,4100)],self.at+3800000)
        self.assertIsNone(r['candidateKeep']);self.assertFalse(r['comparison'])
    def test_full_sample_coverage_and_duplicate_clock(self):
        rows=[self.row(i/2,4000) for i in range(1,121)]
        r=evaluate(self.base,rows+rows,self.at+3600000)
        self.assertEqual(r['coveragePct'],100)


class EntryPathDatabaseReadTests(unittest.TestCase):
    def test_indexed_windows_preserve_observations(self):
        from unittest.mock import Mock
        from entry_path_study import read, VERSION, PROTOCOL

        at = 1800000000000
        base = dict(at=at, priceAt=at, price=4000, valid=True,
                    ready=True, direction='LONG', cohort='v1')
        old = dict(base, at=at-7200000, priceAt=at-7200000)
        one = dict(base, at=at+3600000, priceAt=at+3600000, price=4020)
        class Cursor:
            def __init__(self, values): self.values = values
            def fetchone(self): return self.values
            def fetchall(self): return self.values
        queries = []
        class Conn:
            def execute(self, query, params):
                queries.append((query, params))
                if 'bob_improvement_protocol' in query:
                    return Cursor((PROTOCOL,))
                if 'FROM bob_improvement_trials' in query:
                    return Cursor([(at, 'development', base),
                                   (at-7200000, 'validation', old)])
                if 'FROM bob_improvement_observations o' in query:
                    self.assert_window(params)
                    return Cursor([(one,)] if params[1] == at-900000 else [])
                raise AssertionError('unexpected SQL')
            def assert_window(self, params):
                assert params[1] in (at-900000, at-7200000-900000)
                assert params[2] - params[1] == 4800000
        result = read(Conn(), 'fixed-campaign', at+3800000)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['horizons'][-1]['status'], 'observed')
        self.assertEqual(result['items'][1]['horizons'][-1]['status'], 'missing')
        self.assertEqual(len(queries), 4)
        self.assertTrue(all('WITH trials AS' not in q for q,_ in queries))
        self.assertTrue(all('ORDER BY o.slot' in q for q,_ in queries[2:]))
        self.assertEqual([p for _,p in queries[2:]],
                         [('fixed-campaign', at-900000, at+3900000),
                          ('fixed-campaign', at-7200000-900000, at-7200000+3900000)])


import os
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class EntryPathPostgresTests(unittest.TestCase):
    def test_multi_trial_indexed_read_keeps_all_original_samples(self):
        import json
        import uuid
        import psycopg
        from psycopg import sql
        from entry_path_study import read, VERSION, PROTOCOL

        schema = 'entrypath_bounded_' + uuid.uuid4().hex
        base_at = 1800000000000
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('CREATE TABLE bob_improvement_protocol (id TEXT PRIMARY KEY, payload JSONB)')
                conn.execute('CREATE TABLE bob_improvement_trials (campaign TEXT, slot BIGINT, phase TEXT, payload JSONB, PRIMARY KEY(campaign,slot))')
                conn.execute('CREATE TABLE bob_improvement_observations (campaign TEXT, slot BIGINT, payload JSONB, PRIMARY KEY(campaign,slot))')
                conn.execute('INSERT INTO bob_improvement_protocol VALUES (%s,%s::jsonb)',
                             (VERSION, json.dumps(PROTOCOL)))
                base = dict(at=base_at, priceAt=base_at, price=4000,
                            valid=True, ready=True, direction='LONG', cohort='v1')
                conn.execute('INSERT INTO bob_improvement_trials VALUES (%s,%s,%s,%s::jsonb)',
                             ('campaign', base_at, 'development', json.dumps(base)))
                # The original prior-move guard must retain its real 15m
                # observation, otherwise the 60m comparison stays unconfirmed.
                prior = dict(base, at=base_at-900000, priceAt=base_at-900000, price=3990)
                conn.execute('INSERT INTO bob_improvement_observations VALUES (%s,%s,%s::jsonb)',
                             ('campaign', base_at-900000, json.dumps(prior)))
                # Every 30 s in the one-hour post-trial interval stays present;
                # it must not turn into an artificially full/empty sample.
                for n in range(1,121):
                    item = dict(base, at=base_at+n*30000, priceAt=base_at+n*30000,
                                price=4000+n/100)
                    conn.execute('INSERT INTO bob_improvement_observations VALUES (%s,%s,%s::jsonb)',
                                 ('campaign', base_at+n*30000, json.dumps(item)))
                conn.commit()
                result = read(conn, 'campaign', base_at+3700000)
                self.assertEqual(result['items'][0]['coveragePct'], 100)
                self.assertEqual(result['items'][0]['horizons'][-1]['status'], 'observed')
                self.assertEqual(result['items'][0]['comparison'][0]['baseline'],
                                 result['items'][0]['horizons'][-1]['directionalPct'] - PROTOCOL['costPct'][0])
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_improvement_observations').fetchone()[0], 121)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()
