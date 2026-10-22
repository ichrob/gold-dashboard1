import json,unittest,base64
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,MagicMock,patch
import psycopg
import push_server
import decision_audit as audit
import bob_problem_mirror as mirror
import bob_problems
from test_bob_problems import issue

class OperationalIsolation(unittest.TestCase):
    def test_authentication_has_reserved_connections_without_increasing_total(self):
        with patch.object(push_server,'DATABASE_URL','fixture'),patch.object(push_server,'_db_pool',None),patch.object(push_server,'_auth_db_pool',None),patch.object(push_server,'ConnectionPool') as factory,patch.object(push_server.atexit,'register'):
            normal=Mock();auth=Mock();factory.side_effect=[normal,auth]
            push_server.db();push_server.db(auth=True);push_server.db(auth=True)
            self.assertEqual(factory.call_count,2)
            self.assertEqual(sum(c.kwargs['max_size'] for c in factory.call_args_list),8)
            self.assertEqual(auth.connection.call_count,2)
            self.assertEqual(normal.connection.call_count,1)
    def test_recent_timeout_still_advances_archive_and_throttles(self):
        conn=MagicMock()
        with patch.object(audit,'_harvest_at',0),patch.object(audit.time,'time',return_value=100),patch.object(audit,'_next_harvest_horizon',return_value=60),patch.object(audit,'_harvest_recent',side_effect=psycopg.errors.QueryCanceled),patch.object(audit,'_harvest_horizon') as archive,patch('builtins.print'):
            audit.harvest(conn);audit.harvest(conn)
            archive.assert_called_once_with(conn,60)
    def test_archive_timeout_retries_smaller_batch_in_new_savepoint(self):
        conn=MagicMock()
        with patch.object(audit,'_harvest_at',0),patch.object(audit.time,'time',return_value=100),patch.object(audit,'_next_harvest_horizon',return_value=15),patch.object(audit,'_harvest_recent'),patch.object(audit,'_harvest_horizon',side_effect=[psycopg.errors.QueryCanceled(),None]) as archive:
            audit.harvest(conn)
            self.assertEqual(archive.call_args_list[-1].kwargs,{'batch_size':8})
            self.assertEqual(conn.transaction.call_count,3)
    def test_oldest_horizon_choice_is_durable_and_skips_busy_rows(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=(240,)
        self.assertEqual(audit._next_harvest_horizon(conn),240)
        self.assertIn('attempted_at NULLS FIRST',conn.execute.call_args_list[0].args[0])
        self.assertIn('SKIP LOCKED',conn.execute.call_args_list[0].args[0])

class PublicProblemSnapshot(unittest.TestCase):
    def setUp(self):self.now=datetime.now(timezone.utc)
    def opener(self,data):
        response=MagicMock();response.__enter__.return_value=response;response.read.return_value=json.dumps(data).encode()
        return Mock(return_value=response)
    def test_read_rebuilds_links_and_retains_original_check_time(self):
        report=bob_problems.from_issues([issue('scanner-unreachable',5)],now=self.now)
        report['problems'][0]['url']='https://untrusted.invalid'
        out=mirror.read(opener=self.opener(dict(version=1,checkedAt=report['checkedAt'],problems=report['problems'])),now=self.now)
        self.assertEqual(out['problems'][0]['url'],'https://github.com/ichrob/gold-dashboard1/issues/5')
        self.assertEqual(out['checkedAt'],report['checkedAt'])
    def test_expired_or_future_zero_is_not_success(self):
        for minutes in (-30,3):
            at=self.now+timedelta(minutes=minutes)
            with self.assertRaises(ValueError):mirror.read(opener=self.opener(dict(version=1,checkedAt=at.isoformat(),problems=[])),now=self.now)
    def test_publish_never_exports_issue_body_or_credentials(self):
        row=issue('scanner-unreachable',5);row['body']='secret quote, account and token';row['user']={'login':'ichrob'}
        request=Mock(side_effect=[[row],[row],{'sha':'old'},{'commit':{}}])
        mirror.publish(token='private-token',repo='ichrob/gold-dashboard1',requester=request)
        data=request.call_args.kwargs['data'];payload=base64.b64decode(data['content']).decode()
        self.assertNotIn('secret quote',payload);self.assertNotIn('private-token',payload)
        self.assertEqual(data['branch'],'bob-status');self.assertEqual(data['sha'],'old')
    def test_publish_recovers_open_issue_from_search_when_list_is_empty(self):
        row=issue('scanner-unreachable',5);row['user']={'login':'github-actions[bot]'}
        writes=[]
        def request(method,path,**kwargs):
            if method=='GET' and path.startswith('/issues?'):return []
            if method=='GET' and path.startswith('/search/issues?'):return {'items':[row]}
            if method=='GET' and path.startswith('/contents/'):return {'sha':'old'}
            if method=='PUT':writes.append(kwargs['data']);return {'commit':{}}
            raise AssertionError((method,path))
        self.assertEqual(mirror.publish(token='private-token',repo='ichrob/gold-dashboard1',requester=request),1)
        payload=json.loads(base64.b64decode(writes[0]['content']))
        self.assertEqual(len(payload['problems']),1)
        self.assertEqual(payload['problems'][0]['number'],5)
    def test_new_snapshot_recovers_before_public_api_quota_resets(self):
        from urllib.error import HTTPError
        with patch.object(bob_problems,'_CACHED',None),patch.object(bob_problems,'_RETRY_AFTER',0),patch.object(mirror,'read',side_effect=[ValueError('not yet published'),{'status':'ok','count':0,'problems':[]}]),patch.object(bob_problems,'fetch_open_issues',side_effect=HTTPError(bob_problems.ISSUES_URL,429,'limited',{'Retry-After':'1800'},None)) as api,patch('builtins.print'):
            self.assertEqual(bob_problems.snapshot(clock=lambda:100)['status'],'unavailable')
            self.assertEqual(bob_problems.snapshot(clock=lambda:221)['status'],'ok')
            api.assert_called_once()

    def test_default_reader_uses_snapshot_without_public_api_quota(self):
        with patch.object(bob_problems,'_CACHED',None),patch.object(mirror,'read',return_value={'status':'ok','count':0,'problems':[]}),patch.object(bob_problems,'fetch_open_issues') as api:
            self.assertEqual(bob_problems.snapshot()['status'],'ok');api.assert_not_called()

import os,uuid
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DurableScheduling(unittest.TestCase):
    def test_all_horizons_are_selected_before_repeating_after_commit(self):
        schema='harvest_rotation_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
            conn.execute('CREATE TABLE bob_decision_harvest_cursor(horizon INTEGER PRIMARY KEY,attempted_at TIMESTAMPTZ)')
            conn.execute('INSERT INTO bob_decision_harvest_cursor(horizon) SELECT unnest(%s::integer[])',(list(audit.HARVEST_HORIZONS),))
            seen=[]
            for _ in audit.HARVEST_HORIZONS:
                seen.append(audit._next_harvest_horizon(conn));conn.commit()
            self.assertEqual(seen,list(audit.HARVEST_HORIZONS))
            self.assertEqual(audit._next_harvest_horizon(conn),seen[0])
            conn.execute('DROP SCHEMA '+schema+' CASCADE')
