import json
import os
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlparse,parse_qs
import research_transcript_provider as p

PAYLOAD={'videoId':'GB1n0fEkfn4','channelId':p.CHANNEL}
RAW={'language':'de','transcript':[{'lang':'de','start':1.5,'text':'Gold bleibt unter dem Widerstand. '+('Weitere wirtschaftliche Bedingungen bleiben für dieses Szenario relevant. '*8)}]}

class ProviderTests(unittest.TestCase):
    def test_invalid_identity_never_reaches_database(self):
        connect=Mock()
        for payload in [dict(PAYLOAD,channelId='other'),dict(PAYLOAD,videoId='https://evil.test')]:
            with self.assertRaises(ValueError):p.handle(connect,payload)
        connect.assert_not_called()
    def test_native_only_and_secret_never_in_url(self):
        response=Mock();response.status=200;response.read.return_value=json.dumps(RAW).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        with patch.object(p.urllib.request,'build_opener',return_value=opener):result=p.fetch(PAYLOAD['videoId'])
        request=opener.open.call_args.args[0];query=parse_qs(urlparse(request.full_url).query)
        self.assertEqual(urlparse(request.full_url).netloc,'api.freetranscriptapi.com')
        self.assertEqual(query['video_url'],[PAYLOAD['videoId']])
        self.assertEqual(set(request.headers),{'Accept'})
        self.assertNotIn('mode',query)
        self.assertIn('FreeTranscriptAPI',result['provider'])
        self.assertEqual(result['segments'][0]['at'],1.5)
        opener.open.side_effect=OSError('fixture-secret')
        with patch.object(p.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(ValueError) as caught:p.fetch(PAYLOAD['videoId'])
        self.assertNotIn('fixture-secret',str(caught.exception))
    def test_bad_response_and_unsupported_language(self):
        for data in [{},{'language':'de','transcript':[]},dict(RAW,language='fr'),{'language':'de','transcript':[{'text':'x','start':float('nan')}]}, {'language':'de','transcript':[{'text':'x','start':0,'lang':None}]}]:
            with self.assertRaises(ValueError):p.parse(data)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.connect=lambda:psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'])
        with self.connect() as conn:
            import youtube_feed_archive as archive
            archive.init(conn)
            conn.execute('DELETE FROM bob_youtube_feed_archive WHERE feed_key=%s',(archive.KEY,))
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
    def test_no_key_needed_and_legacy_key_never_sent(self):
        fetch=Mock(return_value=p.parse(RAW))
        with patch.dict(os.environ,{'SUPADATA_API_KEY':' \tfixture-secret\n '}):
            p.handle(self.connect,PAYLOAD,fetch)
        fetch.assert_called_once_with(PAYLOAD['videoId'])

    def test_provider_auth_blocks_other_video_without_burning_credits(self):
        bad=Mock(side_effect=p.TranscriptError('provider_auth'))
        with self.assertRaises(p.TranscriptError) as first:
            p.handle(self.connect,PAYLOAD,bad)
        self.assertEqual(first.exception.code,'provider_auth')
        other=dict(PAYLOAD,videoId='abcdefghijk')
        unused=Mock(return_value=p.parse(RAW))
        with self.assertRaises(p.TranscriptError) as blocked:
            p.handle(self.connect,other,unused)
        self.assertEqual(blocked.exception.code,'provider_auth_paused')
        unused.assert_not_called()
        with self.connect() as conn:
            count=conn.execute('SELECT count(*) FROM bob_research_requests').fetchone()[0]
            self.assertEqual(count,1)
            code=conn.execute('SELECT error_code FROM bob_research_requests').fetchone()[0]
            self.assertEqual(code,'provider_auth')
            conn.execute("UPDATE bob_research_requests SET attempted_at=now()-interval '7 hours' WHERE error_code='provider_auth'")
        restored=p.handle(self.connect,other,unused)
        self.assertEqual(restored['language'],'de')
        unused.assert_called_once()

    def test_forbidden_video_does_not_block_other_videos(self):
        bad=Mock(side_effect=p.TranscriptError('provider_forbidden'))
        with self.assertRaises(p.TranscriptError) as first:
            p.handle(self.connect,PAYLOAD,bad)
        self.assertEqual(first.exception.code,'provider_forbidden')
        with self.connect() as conn:
            self.assertEqual(conn.execute('SELECT error_code FROM bob_research_requests').fetchone()[0],'provider_forbidden')
        with self.assertRaises(p.TranscriptError) as retry:
            p.handle(self.connect,PAYLOAD,bad)
        self.assertEqual(retry.exception.code,'cooldown')
        bad.assert_called_once()
        other=dict(PAYLOAD,videoId='abcdefghijk')
        allowed=Mock(return_value=p.parse(RAW))
        self.assertEqual(p.handle(self.connect,other,allowed)['language'],'de')
        allowed.assert_called_once()

    def test_provider_rate_limit_pauses_all_videos_one_hour(self):
        bad=Mock(side_effect=p.TranscriptError('provider_limit'))
        with self.assertRaises(p.TranscriptError) as first:
            p.handle(self.connect,PAYLOAD,bad)
        self.assertEqual(first.exception.code,'provider_limit')
        other=dict(PAYLOAD,videoId='abcdefghijk')
        untouched=Mock()
        with self.assertRaises(p.TranscriptError) as blocked:
            p.handle(self.connect,other,untouched)
        self.assertEqual(blocked.exception.code,'provider_limit_paused')
        untouched.assert_not_called()

    def test_quota_blocks_before_network(self):
        with self.connect() as conn:
            for i in range(18):conn.execute("INSERT INTO bob_research_requests(claim,provider) VALUES(%s,'freetranscriptapi')",(str(i),))
        fetch=Mock()
        with self.assertRaisesRegex(ValueError,'18 Versuche'):p.handle(self.connect,PAYLOAD,fetch)
        fetch.assert_not_called()
    def test_old_provider_limits_do_not_block_free_provider(self):
        with self.connect() as conn:
            for i in range(90):
                conn.execute("INSERT INTO bob_research_requests(claim,video_id,error_code) VALUES(%s,%s,'provider_auth')",(str(i),PAYLOAD['videoId']))
            conn.execute("INSERT INTO bob_research_transcripts(video_id,attempted_at,claim) VALUES(%s,now(),'legacy')",(PAYLOAD['videoId'],))
        fetch=Mock(return_value=p.parse(RAW))
        with patch.dict(os.environ,{'SUPADATA_API_KEY':''}):
            result=p.handle(self.connect,PAYLOAD,fetch)
        self.assertIn('FreeTranscriptAPI',result['provider'])
        fetch.assert_called_once_with(PAYLOAD['videoId'])

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
        for status, code in [(401,'provider_auth'),(403,'provider_forbidden'),(429,'provider_limit'),(503,'provider_unavailable'),(404,'provider_video')]:
            error=urllib.error.HTTPError('https://example.invalid',status,'secret-value',{},io.BytesIO(b'secret-value'))
            opener=Mock();opener.open.side_effect=error
            with patch.object(p.urllib.request,'build_opener',return_value=opener):
                with self.assertRaises(p.TranscriptError) as caught:p.fetch(PAYLOAD['videoId'])
            self.assertEqual(caught.exception.code,code)
            self.assertNotIn('secret-value',str(caught.exception))

    def test_internal_error_only_accepts_known_code(self):
        import io
        import urllib.error
        for data, expected in [({'errorCode':'provider_forbidden','error':'secret-value'},'HTTP 403'),({'errorCode':'provider_auth','error':'secret-value'},'HTTP 401'),({'errorCode':'cooldown','error':'secret-value'},'pausiert'),({'errorCode':'secret-value','error':'secret-value'},'HTTP 400')]:
            error=urllib.error.HTTPError('https://example.invalid',400,'secret-value',{},io.BytesIO(json.dumps(data).encode()))
            opener=Mock();opener.open.side_effect=error
            with patch.dict(os.environ,{'PUSH_SERVICE_URL':'https://internal.test','PUSH_SERVICE_TOKEN':'secret-value'}),patch.object(p.urllib.request,'build_opener',return_value=opener):
                with self.assertRaisesRegex(ValueError,expected) as caught:p.request(PAYLOAD['videoId'])
            self.assertNotIn('secret-value',str(caught.exception))

class RetryBudgetTests(unittest.TestCase):
    def test_hourly_retry_and_video_budget_preserve_global_limit(self):
        for recent,video_count,total,expected in [(True,0,0,'cooldown'),(False,3,3,'video_limit'),(False,2,18,'local_limit'),(False,2,17,None)]:
            conn=Mock();conn.__enter__=Mock(return_value=conn);conn.__exit__=Mock(return_value=False)
            def execute(sql,params=None):
                if 'FROM bob_youtube_feed_archive' in sql:
                    return Mock(fetchone=Mock(return_value=None))
                if sql.startswith('SELECT result'):
                    self.assertIn("interval '1 hour'",sql)
                    return Mock(fetchone=Mock(return_value=(None,recent)))
                if sql.startswith('SELECT EXISTS'):
                    return Mock(fetchone=Mock(return_value=(False,)))
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
                    self.assertTrue(any('INSERT INTO bob_research_requests(claim,video_id,provider)' in call.args[0] for call in conn.execute.call_args_list))
