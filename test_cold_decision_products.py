"""Reader-only regressions for immutable shared decision product archives."""
import unittest
from unittest.mock import Mock, patch

import cold_decision_products as cold


class DecisionProductsReaderTests(unittest.TestCase):
    def test_inline_originals_are_returned_without_sql_or_network(self):
        conn = Mock()
        for value in ({'products':[{'isin':'EXAMPLE','price':9007199254740993}]},
                      {'products':[]}, {'products':None}, {}, None):
            self.assertIs(cold.resolve(conn,'decision-one',value),value)
        conn.execute.assert_not_called()

    def test_verified_shared_array_preserves_exact_values_and_isolation(self):
        import cold_metrics as codec
        products=[{'isin':'EXAMPLE','price':9007199254740993,
                   'quotedAt':'2026-10-01T11:30:00Z','selected':False}]
        h=codec.digest(codec.encoded(products))
        pointer={'origin':'background','recordedAt':1790854200000,cold.TAG:h}
        file_hash='a'*64
        row=[h,cold.SCOPE,0,None,{'products':products}]
        for decision_id in ('first-decision','second-decision'):
            conn=Mock()
            conn.execute.side_effect=[
                Mock(fetchone=lambda:(h,)),
                Mock(fetchone=lambda:('example-file',file_hash,0))]
            with patch.object(codec,'read_chunk',return_value=[row]) as download:
                original=cold.resolve(conn,decision_id,pointer)
            self.assertEqual(original['products'],products)
            self.assertEqual(original['recordedAt'],1790854200000)
            self.assertNotIn(cold.TAG,original)
            original['products'][0]['price']=0
            self.assertEqual(products[0]['price'],9007199254740993)
            self.assertEqual(conn.execute.call_args_list[0].args[1],(decision_id,))
            download.assert_called_once_with(None,'example-file',file_hash,conn=conn)

    def test_identity_mismatch_corruption_missing_chunk_or_invalid_pointer_fails_closed(self):
        import cold_metrics as codec
        products=[{'isin':'EXAMPLE','price':1}]
        h=codec.digest(codec.encoded(products))
        original={'direction':'LONG',cold.TAG:h}
        good=[h,cold.SCOPE,0,None,{'products':products}]
        failing_cases=[
            (original,(None,None),[good]), # no ledger
            (original,('different',None),[good]),
            (original,(h,None),[good]), # missing object
            (original,(h,('example','a'*64,501)),[good]), # invalid index
            (original,(h,('example','a'*64,0)),[[h,cold.SCOPE,0,None,{'products':[]}]]),
            (original,(h,('example','a'*64,0)),[[h,'other',0,None,{'products':products}]]),
            ({**original,'products':[]},(h,('example','a'*64,0)),[good]),
            ({**original,cold.TAG:'invalid'},(h,('example','a'*64,0)),[good]),
        ]
        for payload,(bound,loc),chunk in failing_cases:
            with self.subTest(payload=payload,bound=bound,loc=loc):
                conn=Mock()
                conn.execute.side_effect=[
                    Mock(fetchone=lambda:(bound,) if bound is not None else None),
                    Mock(fetchone=lambda:loc)]
                with patch.object(codec,'read_chunk',return_value=chunk):
                    with self.assertRaises(codec.ColdArchiveUnavailable) as error:
                        cold.resolve(conn,'decision',payload)
                self.assertIn('incomplete',str(error.exception))
                self.assertNotIn('EXAMPLE',str(error.exception))

    def test_missing_drive_raises_not_empty_products(self):
        import cold_metrics as codec
        products=[{'isin':'EXAMPLE'}]
        h=codec.digest(codec.encoded(products))
        conn=Mock()
        conn.execute.side_effect=[
            Mock(fetchone=lambda:(h,)),
            Mock(fetchone=lambda:('example-file','a'*64,0))]
        with patch.object(codec,'read_chunk',side_effect=codec.ColdArchiveUnavailable('private token')):
            with self.assertRaises(codec.ColdArchiveUnavailable) as error:
                cold.resolve(conn,'decision',{cold.TAG:h})
        self.assertNotIn('private token',str(error.exception))


class DecisionProductsIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(__import__('os').environ.get('BOB_TEST_DATABASE_URL'),'CI PG integration')
    def test_existing_inline_decisions_remain_exact_without_new_ledger_tables(self):
        import os
        import psycopg
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE TEMP TABLE bob_decision_audit (id text PRIMARY KEY,payload jsonb)')
            original={'products':[{'isin':'EXAMPLE','entry':9007199254740993}],
                      'marketEvaluable':True,'recordedAt':1790854200000}
            conn.execute('INSERT INTO bob_decision_audit VALUES(%s,%s)',
                         ('decision',Jsonb(original)))
            rid,payload=conn.execute('SELECT id,payload FROM bob_decision_audit').fetchone()
            with conn.transaction():
                conn.execute('SET TRANSACTION READ ONLY')
                self.assertEqual(cold.resolve(conn,rid,payload),original)
            self.assertEqual(conn.execute('SELECT payload FROM bob_decision_audit').fetchone()[0],original)
            conn.rollback()
