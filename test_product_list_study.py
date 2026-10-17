import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
import product_list_study as study
from test_product_trade_history import PRODUCT,SPOTS,NOW
from test_product_comparison_worker import QUOTE

class ListStudyTests(unittest.TestCase):
    def test_only_user_list_not_catalogue_or_legacy(self):
        feed=dict(listOrigin='degiro-screenshot',products=[dict(isin=PRODUCT['isin'])])
        self.assertEqual(study.listed(feed),{PRODUCT['isin']})
        self.assertEqual(study.listed(dict(feed,listOrigin='legacy')),set())
    def current(self):
        model={k:PRODUCT[k] for k in ('isin','direction','ratio','strike','ko')}
        with patch('hybrid_product_price.model_for',return_value=model):
            return study.anchor(dict(QUOTE,metadata={'currency':'EUR'}),SPOTS,NOW)
    def test_never_compare_anchor_to_itself(self):
        current=self.current()
        self.assertIsNotNone(current)
        self.assertIsNone(study.sample(current,current,QUOTE,SPOTS,NOW))
    def test_later_observation_and_model_isolation(self):
        old=self.current();old['createdAt']=(NOW-timedelta(minutes=2)).isoformat()
        old['product']['referenceAt']=(NOW-timedelta(minutes=2)).isoformat()
        row=study.sample(old,self.current(),QUOTE,SPOTS,NOW)
        self.assertIsNotNone(row)
        changed=self.current();changed['product']['strike']+=1
        self.assertIsNone(study.sample(old,changed,QUOTE,SPOTS,NOW))
        changed=self.current();changed['source']='Other'
        self.assertIsNone(study.sample(old,changed,QUOTE,SPOTS,NOW))
        old['createdAt']=(NOW-timedelta(minutes=31)).isoformat()
        self.assertIsNone(study.sample(old,self.current(),QUOTE,SPOTS,NOW))
    def test_held_out_improvement_and_reversal(self):
        rows=[dict(identity='a',at=i*60000,quoted=10.2,estimated=10,currency='EUR') for i in range(10)]
        result=study.metrics(rows)
        self.assertEqual(result['status'],'improved')
        self.assertAlmostEqual(result['correctedMae'],0)
        for r in rows[6:]:r['quoted']=9.8
        self.assertEqual(study.metrics(rows)['status'],'rejected')
        rows[-1]=dict(rows[-1],identity='b',currency='CHF')
        result=study.metrics(rows)
        self.assertEqual(result['evaluationCount'],1)
        self.assertNotIn('rawMae',result)
    def test_runs_without_any_trade_query(self):
        class DB:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,args=None):
                self.sql=sql;queries.append(sql);return self
            def fetchone(self):return (dict(listOrigin='degiro-screenshot',products=[dict(isin=PRODUCT['isin'])]),)
            def fetchall(self):return []
            def commit(self):pass
        queries=[]
        with patch.object(study,'anchor',return_value=self.current()):
            study.tick(DB,{'spots':SPOTS},lambda _:QUOTE,NOW)
        self.assertTrue(any('INSERT INTO bob_list_price_anchors' in q for q in queries))
        self.assertFalse(any('bob_real_trades' in q for q in queries))

import os
import uuid
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration runs in CI')
class PersistenceTests(unittest.TestCase):
    def test_durable_dedup_and_summary_without_trade_table(self):
        import psycopg
        from psycopg import sql
        from datetime import datetime,timezone
        schema='list_study_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                study.init(conn)
                now=datetime.now(timezone.utc)
                row=dict(identity='fixture',isin=PRODUCT['isin'],at=int(now.timestamp()*1000),quoted=10.2,estimated=10,currency='EUR')
                import json
                for _ in range(2):
                    conn.execute('INSERT INTO bob_list_price_pairs VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',('fixture',PRODUCT['isin'],now,json.dumps(row)))
                conn.commit()
                self.assertEqual(study.summaries(conn,{PRODUCT['isin']})[PRODUCT['isin']]['count'],1)
                conn.commit()
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
