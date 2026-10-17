import contextlib
import io
import json
import os
import unittest
from unittest.mock import MagicMock,patch
import browserless_profile as p
import browserless_trial as t

class ProfileTests(unittest.TestCase):
    def test_missing_secret_no_request(self):
        with patch.dict(os.environ,{},clear=True),patch.object(p.requests,'get') as get:
            self.assertEqual(p.profile_revision(),('not-configured',None));get.assert_not_called()

    def test_only_metadata_endpoint_and_safe_errors(self):
        with patch.dict(os.environ,{'BROWSERLESS_API_TOKEN':'private-token'}),patch.object(p.requests,'get') as get:
            r=get.return_value.__enter__.return_value;r.status_code=200
            r.iter_content.return_value=[json.dumps({'name':p.PROFILE,'updatedAt':'2026-10-17','cookies':'never-return'}).encode()]
            state,rev=p.profile_revision();self.assertEqual(state,'profile-ready');self.assertEqual(len(rev),24)
            self.assertNotIn('download',get.call_args.args[0]);self.assertFalse(get.call_args.kwargs['allow_redirects'])
            get.side_effect=RuntimeError('private-token');self.assertEqual(p.profile_revision(),('profile-unavailable',None))

    def test_fixed_profile_and_no_authenticated_page_logs(self):
        with patch.object(t.requests,'post') as post,contextlib.redirect_stdout(io.StringIO()) as out:
            r=post.return_value.__enter__.return_value;r.status_code=200
            r.iter_content.return_value=[json.dumps({'videoId':'abcdefghijk','status':'access-blocked','diagnostic':{'text':'private name'}}).encode()]
            self.assertEqual(t.capture('private-token','abcdefghijk',[],profile=p.PROFILE),('access-blocked',[]))
            self.assertEqual(post.call_args.kwargs['params']['profile'],p.PROFILE)
            self.assertEqual(out.getvalue(),'')
            post.reset_mock();self.assertEqual(t.capture('x','abcdefghijk',[],profile='other'),('invalid-profile',[]));post.assert_not_called()

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_reservation_dedup_quota_and_retention(self):
        import psycopg,uuid
        from psycopg import sql
        import research_enhancements
        schema='profile_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            research_enhancements.init(conn);p.init(conn);conn.commit()
            @contextlib.contextmanager
            def connect():
                yield conn
                conn.commit()
            try:
                conn.execute("INSERT INTO bob_research_enhancements(video_id,fingerprint,summary) VALUES('abcdefghijk','test',%s::jsonb)",(json.dumps({'sections':[{'evidence':[{'at':18}]}]}),));conn.commit()
                with patch.object(p,'profile_revision',return_value=('profile-ready','revision')),patch('youtube_feed_archive.is_retained',return_value=True),patch.object(p.threading,'Thread') as thread:
                    self.assertEqual(p.start(connect,'abcdefghijk')['status'],'running')
                    self.assertEqual(p.start(connect,'abcdefghijk')['status'],'running');self.assertEqual(thread.call_count,1)
                    conn.execute("UPDATE bob_browserless_profile_jobs SET status='access-blocked'");conn.commit()
                    self.assertEqual(p.status(connect,'abcdefghijk')['status'],'access-blocked')
                    conn.execute("INSERT INTO bob_browserless_profile_jobs(job,video_id,status) VALUES('two','abcdefghijk','access-blocked'),('three','abcdefghijk','access-blocked')");conn.commit()
                    with patch.object(p,'profile_revision',return_value=('profile-ready','changed')):
                        self.assertEqual(p.start(connect,'abcdefghijk')['status'],'quota')
                    with patch('youtube_feed_archive.is_retained',return_value=False):
                        self.assertEqual(p.start(connect,'abcdefghijk')['status'],'video-removed')
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()
