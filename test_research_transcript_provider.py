import json
import os
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlparse,parse_qs
import research_transcript_provider as p

PAYLOAD={'videoId':'GB1n0fEkfn4','channelId':p.CHANNEL}
RAW={'lang':'de','content':[{'lang':'de','offset':1500,'text':'Gold bleibt unter dem Widerstand. '+('Weitere wirtschaftliche Bedingungen bleiben für dieses Szenario relevant. '*8)}]}

class ProviderTests(unittest.TestCase):
    def test_disabled_without_key_and_invalid_identity(self):
        connect=Mock()
        with patch.dict(os.environ,{'SUPADATA_API_KEY':''}):
            with self.assertRaisesRegex(ValueError,'noch nicht eingerichtet'):p.handle(connect,PAYLOAD)
        connect.assert_not_called()
        for payload in [dict(PAYLOAD,channelId='other'),dict(PAYLOAD,videoId='https://evil.test')]:
            with self.assertRaises(ValueError):p.handle(connect,payload)
        connect.assert_not_called()
    def test_native_only_and_secret_never_in_url(self):
        response=Mock();response.status=200;response.read.return_value=json.dumps(RAW).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch.object(p.urllib.request,'build_opener',return_value=opener):result=p.fetch(PAYLOAD['videoId'],'fixture-secret')
        request=opener.open.call_args.args[0];query=parse_qs(urlparse(request.full_url).query)
        self.assertEqual(query['mode'],['native']);self.assertNotIn('fixture-secret',request.full_url)
        self.assertEqual(result['segments'][0]['at'],1.5)
        opener.open.side_effect=OSError('fixture-secret')
        with patch.object(p.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(ValueError) as caught:p.fetch(PAYLOAD['videoId'],'fixture-secret')
        self.assertNotIn('fixture-secret',str(caught.exception))
    def test_bad_response_and_unsupported_language(self):
        for data in [{},{'lang':'de','content':[]},dict(RAW,lang='fr'),{'lang':'de','content':[{'text':'x','offset':float('nan')}]}, {'lang':'de','content':[{'text':'x','offset':0,'lang':None}]}]:
            with self.assertRaises(ValueError):p.parse(data)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.connect=lambda:psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'])
        with self.connect() as conn:
            p.init(conn);conn.execute('DELETE FROM bob_research_transcripts');conn.execute('DELETE FROM bob_research_requests')
        self.key=patch.dict(os.environ,{'SUPADATA_API_KEY':'fixture-secret'});self.key.start();self.addCleanup(self.key.stop)
    def tearDown(self):
        with self.connect() as conn:
            conn.execute('DELETE FROM bob_research_transcripts');conn.execute('DELETE FROM bob_research_requests')
    def test_cache_survives_connections_and_failure_cooldown(self):
        fetch=Mock(return_value=p.parse(RAW))
        p.handle(self.connect,PAYLOAD,fetch);p.handle(self.connect,PAYLOAD,fetch);fetch.assert_called_once()
        with self.connect() as conn:self.assertEqual(conn.execute('SELECT count(*) FROM bob_research_requests').fetchone()[0],1)
        other=dict(PAYLOAD,videoId='abcdefghijk');failure=Mock(side_effect=ValueError('unavailable'))
        with self.assertRaises(ValueError):p.handle(self.connect,other,failure)
        with self.assertRaisesRegex(ValueError,'pausiert'):p.handle(self.connect,other,failure)
        failure.assert_called_once()
    def test_quota_blocks_before_network(self):
        with self.connect() as conn:
            for i in range(90):conn.execute('INSERT INTO bob_research_requests(claim) VALUES(%s)',(str(i),))
        fetch=Mock()
        with self.assertRaisesRegex(ValueError,'90 Versuche'):p.handle(self.connect,PAYLOAD,fetch)
        fetch.assert_not_called()
    def test_concurrent_calls_only_reserve_once(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        entered=threading.Event();release=threading.Event()
        def fetch(*_):entered.set();release.wait(5);return p.parse(RAW)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(p.handle,self.connect,PAYLOAD,fetch)
            self.assertTrue(entered.wait(3))
            try:
                with self.assertRaisesRegex(ValueError,'pausiert'):p.handle(self.connect,PAYLOAD,Mock())
            finally:release.set()
            self.assertEqual(first.result()['language'],'de')

if __name__=='__main__':unittest.main()

class ErrorReportingTests(unittest.TestCase):
    def test_provider_status_is_safe_and_specific(self):
        import io
        import urllib.error
        for status, code in [(401,'provider_auth'),(429,'provider_limit'),(503,'provider_unavailable'),(404,'provider_video')]:
            error=urllib.error.HTTPError('https://example.invalid',status,'secret-value',{},io.BytesIO(b'secret-value'))
            opener=Mock();opener.open.side_effect=error
            with patch.object(p.urllib.request,'build_opener',return_value=opener):
                with self.assertRaises(p.TranscriptError) as caught:p.fetch(PAYLOAD['videoId'],'secret-value')
            self.assertEqual(caught.exception.code,code)
            self.assertNotIn('secret-value',str(caught.exception))

    def test_internal_error_only_accepts_known_code(self):
        import io
        import urllib.error
        for data, expected in [({'errorCode':'cooldown','error':'secret-value'},'pausiert'),({'errorCode':'secret-value','error':'secret-value'},'HTTP 400')]:
            error=urllib.error.HTTPError('https://example.invalid',400,'secret-value',{},io.BytesIO(json.dumps(data).encode()))
            opener=Mock();opener.open.side_effect=error
            with patch.dict(os.environ,{'PUSH_SERVICE_URL':'https://internal.test','PUSH_SERVICE_TOKEN':'secret-value'}),patch.object(p.urllib.request,'build_opener',return_value=opener):
                with self.assertRaisesRegex(ValueError,expected) as caught:p.request(PAYLOAD['videoId'])
            self.assertNotIn('secret-value',str(caught.exception))

class RetryBudgetTests(unittest.TestCase):
    def test_hourly_retry_and_video_budget_preserve_global_limit(self):
        for recent,video_count,total,expected in [(True,0,0,'cooldown'),(False,3,3,'video_limit'),(False,2,90,'local_limit'),(False,2,89,None)]:
            conn=Mock();conn.__enter__=Mock(return_value=conn);conn.__exit__=Mock(return_value=False)
            def execute(sql,params=None):
                if sql.startswith('SELECT result'):
                    self.assertIn("interval '1 hour'",sql)
                    return Mock(fetchone=Mock(return_value=(None,recent)))
                if sql.startswith('SELECT count'):
                    return Mock(fetchone=Mock(return_value=(video_count if 'video_id=%s' in sql else total,)))
                return Mock()
            conn.execute.side_effect=execute
            fetch=Mock(return_value=p.parse(RAW))
            with patch.dict(os.environ,{'SUPADATA_API_KEY':'fixture'}):
                if expected:
                    with self.assertRaises(p.TranscriptError) as caught:p.handle(lambda:conn,PAYLOAD,fetch)
                    self.assertEqual(caught.exception.code,expected);fetch.assert_not_called()
                else:
                    p.handle(lambda:conn,PAYLOAD,fetch);fetch.assert_called_once()
                    self.assertTrue(any('INSERT INTO bob_research_requests(claim,video_id)' in call.args[0] for call in conn.execute.call_args_list))
