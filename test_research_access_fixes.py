"""Research read path regressions. Synthetic fixtures, no live data or orders."""
import copy
import json
import os
import unittest
import uuid
from unittest.mock import MagicMock, Mock, patch

import bob_mcp
import research_readout
import server
import push_server


def request(focus='research'):
    return {'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':'bob_diagnostics','arguments':{'focus':focus}}}


class ResearchAccessTests(unittest.TestCase):
    def test_research_focus_loads_report_independently_of_fast_simulation(self):
        stored={'status':'observed','items':[{'calculatedAt':'original-clock',
            'report':{'mode':'RESEARCH_ONLY','approved':False,'closedBars':1200}}]}
        before=copy.deepcopy(stored)
        with patch.object(server,'read_private_report_for_mcp',return_value=stored) as reader, \
             patch.object(server.gold_research,'snapshot',return_value={}), \
             patch.object(server.strategy_lab_background,'status',return_value={}):
            fast=Mock(side_effect=AssertionError('must not load live/history'))
            _,out=bob_mcp.handle(request(),Mock(),fast,
                research_reader=server.read_research_diagnostics_for_mcp)
        reader.assert_called_once_with('/research-status');fast.assert_not_called()
        data=json.loads(out['result']['content'][0]['text'])
        self.assertEqual(data['areas']['strategyReport'],stored)
        self.assertNotIn('simulationAndPush',data['areas'])
        self.assertEqual(stored,before)

    def test_other_focus_and_legacy_readers_keep_original_behavior(self):
        fast=Mock(return_value={'areas':{'background':{'status':'ok'}}})
        research=Mock(side_effect=AssertionError('no research for sources'))
        bob_mcp.handle(request('sources'),Mock(),fast,research_reader=research)
        fast.assert_called_once();research.assert_not_called()
        fast.reset_mock()
        bob_mcp.handle(request(),Mock(),fast)
        fast.assert_called_once()

    def test_research_callback_cannot_bypass_diagnostics_scope(self):
        research=Mock(side_effect=AssertionError('no unauthorized reads'))
        _,response=bob_mcp.handle(request(),Mock(),None,research_reader=research)
        self.assertTrue(response['result']['isError']);research.assert_not_called()
        self.assertIn('insufficient_scope',response['result']['_meta']['mcp/www_authenticate'][0])

    def test_internal_route_requires_service_auth_before_db_admission(self):
        for token in ('','wrong'):
            handler=object.__new__(push_server.Handler)
            handler.path='/research-status';handler.headers={'X-Bob-Push-Token':token}
            with patch.object(push_server,'PUSH_SERVICE_TOKEN','synthetic-test-token'), \
                 patch.object(push_server,'read_db_report') as read, \
                 patch.object(push_server,'db') as db,patch.object(push_server,'send_json') as send:
                handler.do_GET()
            read.assert_not_called();db.assert_not_called()
            self.assertEqual(send.call_args.args[1],401)

    def test_internal_route_admits_reader_before_connection(self):
        handler=object.__new__(push_server.Handler)
        handler.path='/research-status';handler.headers={'X-Bob-Push-Token':'synthetic-test-token'}
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','synthetic-test-token'), \
             patch.object(push_server,'read_db_report',return_value={'status':'empty'}) as read, \
             patch.object(push_server,'db') as db,patch.object(push_server,'send_json') as send:
            handler.do_GET()
        read.assert_called_once_with('research-status',research_readout.bounded_read)
        db.assert_not_called();self.assertEqual(send.call_args.args[1],200)

    def test_bounded_read_is_single_select_with_original_clocks_and_redaction(self):
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[({'day':'2026-10-28',
            'calculatedAt':'original','report':{'mode':'RESEARCH_ONLY',
                'credential':'do-not-leak','closedBars':1200,
                'foldSelection':{'policy':'latest-12-complete-chronological','selected':12},
                'learningCycle':{'newIndependentEvidence':False}}},)]
        out=research_readout.bounded_read(conn)
        sql=[call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(sql[:2],['SET TRANSACTION READ ONLY',"SET LOCAL statement_timeout='1500ms'"])
        self.assertEqual(len(sql),3);self.assertTrue(sql[2].startswith('SELECT'))
        self.assertIn('LIMIT 1',sql[2]);self.assertNotIn('do-not-leak',json.dumps(out))
        self.assertEqual(out['items'][0]['calculatedAt'],'original')
        self.assertEqual(out['items'][0]['report']['foldSelection']['selected'],12)
        self.assertFalse(out['items'][0]['report']['learningCycle']['newIndependentEvidence'])

    def test_read_failure_rolls_back_and_is_distinct_from_empty(self):
        conn=MagicMock();conn.execute.side_effect=RuntimeError('private-error')
        failed=research_readout.bounded_read(conn)
        self.assertEqual(failed['status'],'unavailable')
        self.assertNotIn('private-error',json.dumps(failed))
        self.assertIs(conn.transaction.return_value.__exit__.call_args.args[0],RuntimeError)
        empty=MagicMock();empty.execute.return_value.fetchall.return_value=[]
        self.assertEqual(research_readout.bounded_read(empty)['status'],'empty')


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class ResearchReadDatabaseTests(unittest.TestCase):
    def test_real_read_only_transaction_reads_latest_without_writes(self):
        import psycopg
        from psycopg import sql
        schema='research_reader_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('CREATE TABLE bob_strategy_lab_daily(run_day date,calculated_at timestamptz,last_bar_at bigint,status text,report jsonb)')
                conn.execute("INSERT INTO bob_strategy_lab_daily VALUES ('2026-10-27',now(),1,'evaluated','{}'),('2026-10-28',now(),2,'evaluated','{}')")
                conn.commit()
                original_read=research_readout.read
                def verified_read(connection):
                    self.assertEqual(connection.execute('SHOW transaction_read_only').fetchone()[0],'on')
                    return original_read(connection)
                with patch.object(research_readout,'read',side_effect=verified_read):
                    out=research_readout.bounded_read(conn)
                self.assertEqual(out['status'],'observed')
                self.assertEqual(out['items'][0]['day'],'2026-10-28')
                self.assertEqual(conn.execute("SELECT count(*) FROM bob_strategy_lab_daily").fetchone()[0],2)
                conn.rollback()
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()


if __name__=='__main__':unittest.main()
