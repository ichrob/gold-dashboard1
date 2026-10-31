"""One-shot production-pilot coordinator regressions: no repeat or secret leak."""
import os
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

import decision_product_pilot as pilot


class PilotControlsTests(unittest.TestCase):
    def test_disabled_without_strict_operator_command(self):
        connect=Mock()
        with patch.dict(os.environ,{
                'BOB_DECISION_PRODUCT_PILOT_ONCE':'',
                'BOB_COLD_DECISION_PRODUCTS_ENABLED':'0'}):
            self.assertIsNone(pilot.configuration())
            self.assertEqual(pilot.run_once(connect=connect),
                             {'status':'disabled','movedRows':0})
        connect.assert_not_called()

    def test_unapproved_or_malformed_config_never_starts(self):
        valid={'id':'single-pilot-test','confirmed':True,'maxUpdates':1}
        for value in ({**valid,'maxUpdates':2},{**valid,'confirmed':False},
                      {**valid,'id':'unsafe space'},
                      {**valid,'password':'must-not-accept'},{}):
            with self.subTest(value=value),patch.dict(os.environ,{
                'BOB_DECISION_PRODUCT_PILOT_ONCE':json.dumps(value),
                'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
                self.assertIsNone(pilot.configuration())
        with patch.dict(os.environ,{
                'BOB_DECISION_PRODUCT_PILOT_ONCE':json.dumps(valid),
                'BOB_COLD_DECISION_PRODUCTS_ENABLED':'0'}):
            self.assertIsNone(pilot.configuration())

    def test_stale_restore_stops_before_create_table(self):
        cfg={'id':'single-pilot-test','confirmed':True,'maxUpdates':1}
        conn=MagicMock()
        conn.autocommit=True
        conn.__enter__.return_value=conn
        with patch.dict(os.environ,{
                'BOB_DECISION_PRODUCT_PILOT_ONCE':json.dumps(cfg),
                'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}), \
             patch.object(pilot,'_preflight',return_value='backup-proof-not-fresh'), \
             patch.object(pilot,'init') as init:
            result=pilot.run_once(connect=lambda:conn,now=100000)
        self.assertEqual(result,{'status':'backup-proof-not-fresh','movedRows':0})
        init.assert_not_called()
        conn.execute.assert_not_called()


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL fixture')
class PilotClaimPGTests(unittest.TestCase):
    def test_claim_is_durable_exactly_once_across_two_invocations(self):
        import psycopg
        import uuid
        cfg={'id':'oct31-single-row','confirmed':True,'maxUpdates':1}
        schema='pilot_test_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                # Each independent pilot invocation owns and closes its own
                # connection; never reuse a connection closed by `with`.
                def factory():
                    return psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],
                        autocommit=True,options='-c search_path='+schema)
                expected={'status':'verified-offload','movedRows':1,'readThroughVerified':True}
                invoke=Mock(return_value=expected)
                with patch.dict(os.environ,{
                         'BOB_DECISION_PRODUCT_PILOT_ONCE':json.dumps(cfg),
                         'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}), \
                     patch.object(pilot,'_preflight',
                                  return_value='approved-for-single-row-pilot'):
                    first=pilot.run_once(connect=factory,invoke=invoke,now=100000)
                    second=pilot.run_once(connect=factory,invoke=invoke,now=100000)
                self.assertEqual(first['status'],'verified-offload')
                self.assertEqual(first['movedRows'],1)
                self.assertEqual(second,{'status':'already-claimed','movedRows':0})
                self.assertEqual(invoke.call_count,1)
                self.assertEqual(invoke.call_args.kwargs['max_updates'],1)
                self.assertEqual(conn.execute(
                    'SELECT count(*) FROM bob_cold_decision_pilot_attempts').fetchone()[0],1)
                last=pilot.status(conn)
                self.assertEqual(last['status'],'verified-offload')
                self.assertEqual(last['movedRows'],1)
                self.assertNotIn('oct31-single-row',json.dumps(last))
                self.assertIsNone(last['diskBytesFreed'])
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_exception_is_recorded_once_without_original_or_credentials(self):
        import psycopg
        import uuid
        schema='pilot_error_'+uuid.uuid4().hex
        cfg={'id':'one-exception','confirmed':True,'maxUpdates':1}
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                # Each independent pilot invocation owns and closes its own
                # connection; never reuse a connection closed by `with`.
                def factory():
                    return psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],
                        autocommit=True,options='-c search_path='+schema)
                invoke=Mock(side_effect=RuntimeError('secret-DSN'))
                with patch.dict(os.environ,{
                        'BOB_DECISION_PRODUCT_PILOT_ONCE':json.dumps(cfg),
                        'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}), \
                     patch.object(pilot,'_preflight',
                                  return_value='approved-for-single-row-pilot'):
                    result=pilot.run_once(connect=factory,invoke=invoke,now=100000)
                    retry=pilot.run_once(connect=factory,invoke=invoke,now=100000)
                self.assertEqual(result['status'],'failed')
                self.assertEqual(result['errorType'],'RuntimeError')
                self.assertNotIn('secret-DSN',json.dumps(result))
                self.assertEqual(retry['status'],'already-claimed')
                self.assertEqual(invoke.call_count,1)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')
