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

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
    def test_database_survives_restart(self):
        import psycopg
        url=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(url) as conn:
            store.init(conn)
            saved=store.handle(conn,'write',{'items':[example()]})
            self.assertEqual(saved['saved'],1)
        with psycopg.connect(url) as conn:
            result=store.handle(conn,'read',{})
            self.assertEqual(len(result['items']),1)
            self.assertTrue(result['displayOnly'])
            conn.execute('DELETE FROM bob_youtube_feed_archive WHERE feed_key=%s',(store.KEY,))

if __name__=='__main__':
    unittest.main()
