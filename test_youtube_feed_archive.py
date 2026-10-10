import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import youtube_feed_archive as store
import gold_research as research
import os

CHANNEL=store.CHANNEL
def example(vid='AaBbCcDdE01'):
    return dict(channelId=CHANNEL,kind='YouTube',title='Gold Marktanalyse heute',
        url='https://www.youtube.com/watch?v='+vid,publishedAt=1760000000,
        transcript='DO NOT STORE MY PRIVATE TRANSCRIPT',sourceId='mco-video')

class YoutubeFeedArchiveTests(unittest.TestCase):
    def test_verified_public_video_only(self):
        accepted=store.sanitize([example(),dict(example(),channelId='wrong'),dict(example(),url='https://evil.test/watch?v=AaBbCcDdE01'),dict(example(),title='Markets other metals'),dict(example(),url='https://www.youtube.com/watch?v=bad')])
        self.assertEqual(len(accepted),1)
        self.assertNotIn('transcript',accepted[0])
        self.assertEqual(accepted[0]['url'],'https://www.youtube.com/watch?v=AaBbCcDdE01')
        self.assertFalse(accepted[0]['trustedTranscript'])
        self.assertEqual(accepted[0]['outlook'],'UNKLAR')
        self.assertTrue(research.allowed_item(accepted[0]))

    def test_archived_is_never_fresh_direction_vote(self):
        item=store.sanitize([example()])[0]
        item['publishedAt']=1760000000
        report=dict(checkedAt=1760000000,sources=[],items=[item],archived=True)
        result=research.summarize(report,now=1760000030)
        self.assertFalse(result['fresh'])
        self.assertEqual(result['consensus'],'ABWARTEN')
        self.assertEqual(result['videosFound'],1)

    def test_only_three_metadata_entries_and_no_transcript_contents(self):
        ids=['AaBbCcDdE04','AaBbCcDdE03','AaBbCcDdE02','AaBbCcDdE01']
        records=[example(vid) for vid in ids]
        sanitized=store.sanitize(records)
        self.assertEqual(len(sanitized),3)
        self.assertEqual(store.selected_ids(sanitized),ids[:3])
        self.assertTrue(all('transcript' not in x for x in sanitized))

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
    def test_purge_evicted_transcript_ai_and_frames_without_resetting_quota(self):
        import psycopg
        import research_transcript_provider as provider
        import research_enhancements as enhancements
        url=os.environ['BOB_TEST_DATABASE_URL']
        ids=['AaBbCcDdE04','AaBbCcDdE03','AaBbCcDdE02','AaBbCcDdE01']
        with psycopg.connect(url) as conn:
            store.init(conn); provider.init(conn); enhancements.init(conn)
            conn.execute('DELETE FROM bob_youtube_feed_archive WHERE feed_key=%s',(store.KEY,))
            conn.execute('DELETE FROM bob_research_transcripts WHERE video_id=ANY(%s::text[])',(ids,))
            conn.execute('DELETE FROM bob_research_enhancements WHERE video_id=ANY(%s::text[])',(ids,))
            conn.execute('DELETE FROM bob_research_requests WHERE claim=%s',('retention-fixture',))
            for vid in ids:
                conn.execute("""INSERT INTO bob_research_transcripts(video_id,result,attempted_at,claim)
                    VALUES(%s,'{"segments":[{"text":"Gold"}]}',now(),%s)""",(vid,'claim-'+vid))
                conn.execute("""INSERT INTO bob_research_enhancements(video_id,fingerprint,summary,frames)
                    VALUES(%s,'fixture','{"sections":[]}','[{"dataUrl":"base64-heavy"}]')""",(vid,))
            conn.execute('INSERT INTO bob_research_requests(claim,video_id) VALUES(%s,%s)',
                         ('retention-fixture',ids[-1]))
            self.assertEqual(store.handle(conn,'write',{'items':[example(vid) for vid in ids]})['saved'],3)
            self.assertFalse(store.is_retained(conn,ids[-1]))
            self.assertTrue(store.is_retained(conn,ids[0]))
            rows=conn.execute('SELECT video_id FROM bob_research_transcripts').fetchall()
            self.assertNotIn(ids[-1], [x[0] for x in rows])
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_research_enhancements WHERE video_id=%s',
                                          (ids[-1],)).fetchone()[0],0)
            # The provider retains only an anonymous timestamp for quota safety.
            self.assertIsNone(conn.execute('SELECT video_id FROM bob_research_requests WHERE claim=%s',
                                           ('retention-fixture',)).fetchone()[0])
            conn.execute('DELETE FROM bob_youtube_feed_archive WHERE feed_key=%s',(store.KEY,))
            conn.execute('DELETE FROM bob_research_transcripts WHERE video_id=ANY(%s::text[])',(ids,))
            conn.execute('DELETE FROM bob_research_enhancements WHERE video_id=ANY(%s::text[])',(ids,))
            conn.execute('DELETE FROM bob_research_requests WHERE claim=%s',('retention-fixture',))

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
    def test_database_survives_restart(self):
        import psycopg
        url=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(url) as conn:
            store.init(conn)
            import research_transcript_provider as provider
            import research_enhancements as enhancements
            provider.init(conn); enhancements.init(conn)
            saved=store.handle(conn,'write',{'items':[example()]})
            self.assertEqual(saved['saved'],1)
        with psycopg.connect(url) as conn:
            result=store.handle(conn,'read',{})
            self.assertEqual(len(result['items']),1)
            self.assertTrue(result['displayOnly'])
            conn.execute('DELETE FROM bob_youtube_feed_archive WHERE feed_key=%s',(store.KEY,))

if __name__=='__main__':
    unittest.main()
