"""Synthetic forward observations: no broker connection or real orders."""
import copy
import json
import unittest
from unittest.mock import Mock
import paper_stop_study as study
import paper_simulation as sim
from test_paper_simulation import market, quote, NOW, ISIN

class StopStudyTests(unittest.TestCase):
    def case(self,profile='normal1000nov',direction='LONG'):
        m=market(direction)
        bars=[dict(instrument='XAU/USD',isOpen=False,openTime=NOW-(20-i)*300000,
                   low=95,high=105,close=100) for i in range(20)]
        c=sim.new_case(m,dict(isin=ISIN),quote(),NOW,bundle={'history':{'bars_by_tf':{'5m':bars}}})
        c['profile']=profile
        return c

    def step(self,s,seconds,gold,bid):
        at=NOW+seconds*1000
        return study.advance(s,{**market(s['direction']),'price':gold,'dataAt':at},quote(at,bid,bid+.1),at)

    def test_delayed_registration_cannot_import_a_later_stop(self):
        case=self.case()
        case['engine']['trade']['stop']=110
        state=study.create(case)
        self.assertEqual(state['engine']['trade']['stop'],90)
        self.assertEqual(state['variants']['bob']['stop'],90)

    def test_current_accounts_and_unique_ids(self):
        states=[study.create(self.case(p)) for p in study.PROFILES]
        self.assertEqual(len(set(s['id'] for s in states)),len(states))
        self.assertTrue(all(len(s['variants'])==5 for s in states))
        self.assertIsNone(study.create(self.case('retired')))

    def test_restart_keeps_peak_stop_and_short_product_orientation(self):
        for direction in ('LONG','SHORT'):
            with self.subTest(direction=direction):
                s=study.create(self.case(direction=direction))
                gold=105 if direction=='LONG' else 95
                s=self.step(s,30,gold,11)
                restored=json.loads(json.dumps(s))
                self.assertEqual(restored['variants']['trailing2']['stop'],10.78)
                uninterrupted=self.step(s,60,gold,10.7)
                restarted=self.step(restored,60,gold,10.7)
                self.assertEqual(restarted,uninterrupted)
                v=restarted['variants']['trailing2']
                self.assertEqual(v['status'],'observed-stop')
                self.assertEqual(v['bid'],10.7)
                self.assertIsNotNone(v['modelNetEur'])

    def test_stale_quote_cannot_raise_peak_or_fake_exit(self):
        s=study.create(self.case());original=copy.deepcopy(s)
        stale=study.advance(s,{**market(),'dataAt':NOW+120000},quote(NOW,50,51),NOW+120000)
        self.assertEqual(stale['variants'],s['variants'])
        self.assertTrue(stale['gap']);self.assertEqual(s,original)
        resumed=self.step(json.loads(json.dumps(stale)),150,89,8)
        self.assertEqual(resumed['variants']['trailing2']['status'],'inconclusive')
        self.assertIsNone(resumed['variants']['trailing2']['modelNetEur'])

    def test_duplicate_observation_and_reentry_are_isolated(self):
        s=self.step(study.create(self.case()),30,105,11)
        self.assertEqual(self.step(s,30,105,11),s)
        closed=self.step(s,60,89,8)
        new=self.case();new['id']='new-confirmed-setup'
        fresh=study.create(new)
        self.assertNotEqual(fresh['id'],closed['id'])
        self.assertEqual(fresh['variants']['trailing2']['peakBid'],10)
        self.assertEqual(fresh['variants']['trailing2']['stop'],9.8)

    def test_bob_stop_uses_shared_engine_and_survives_restore(self):
        s=self.step(study.create(self.case()),30,115,11)
        self.assertGreaterEqual(s['variants']['bob']['stop'],100)
        next_state=self.step(json.loads(json.dumps(s)),60,114,10.9)
        self.assertGreaterEqual(next_state['variants']['bob']['stop'],s['variants']['bob']['stop'])

    def test_report_filters_profile_and_version(self):
        conn=Mock();conn.execute.return_value.fetchall.return_value=[]
        report=study.report(conn,'2026-11-12','ema3000nov')
        self.assertEqual(conn.execute.call_args.args[1],('2026-11-12',study.VERSION,'ema3000nov'))
        self.assertFalse(report['promoted'])

import os
import uuid
@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'),'isolated CI PostgreSQL required')
class DatabaseRestartTests(unittest.TestCase):
    def test_committed_stop_survives_new_database_connection(self):
        import psycopg
        from psycopg import sql
        schema='stop_restart_'+uuid.uuid4().hex
        url=os.environ['BOB_TEST_DATABASE_URL']
        fixture=StopStudyTests()
        s=fixture.step(study.create(fixture.case()),30,105,11)
        try:
            with psycopg.connect(url) as conn:
                conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                study.init(conn)
                conn.execute('INSERT INTO bob_paper_stop_studies VALUES (%s,%s,FALSE,%s::jsonb)',(s['id'],s['day'],json.dumps(s)))
            # New connection: the prior process/transaction cannot supply state.
            with psycopg.connect(url) as conn:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                restored=conn.execute('SELECT payload FROM bob_paper_stop_studies WHERE id=%s',(s['id'],)).fetchone()[0]
                self.assertEqual(restored,s)
                stopped=fixture.step(restored,60,104,10.7)
                self.assertEqual(stopped['variants']['trailing2']['status'],'observed-stop')
                self.assertEqual(stopped['variants']['trailing2']['stop'],10.78)
        finally:
            with psycopg.connect(url) as conn:
                conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
