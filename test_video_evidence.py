import base64
import copy
import io
import unittest
from unittest.mock import patch
import video_evidence as e
import video_ocr as o

class EvidenceTests(unittest.TestCase):
    def frame(self):
        from PIL import Image
        b=io.BytesIO();Image.new('RGB',(400,200),'white').save(b,'JPEG')
        return dict(at=30,dataUrl='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode())
    def test_image_validation_and_provenance(self):
        frame=self.frame();clean=e.checked_frames([frame])[0]
        self.assertTrue(clean['userProvided']);self.assertFalse(clean['isCover'])
        for frames in ([frame]*6,[frame,frame],[dict(frame,at=float('nan'))],[dict(frame,dataUrl='https://untrusted.example/')]):
            with self.assertRaises(ValueError):e.checked_frames(frames)
        import research_enhancements as r
        self.assertEqual(r.validated_frames([clean]),[])
    def test_screenshot_merge_preserves_other_sections(self):
        frame=self.frame();frame.update(sourceKind='screenshot',sectionAt=20)
        clean=e.checked_frames([frame])[0]
        self.assertEqual(clean['sourceKind'],'screenshot')
        self.assertEqual(clean['sectionAt'],20)
        old=[dict(clean,at=40,sectionAt=40),dict(clean,at=10)]
        result=e.merge_screenshot(old,clean)
        self.assertEqual([f['at'] for f in result],[30,40])
        with self.assertRaises(ValueError):e.checked_frames([dict(frame,sectionAt=float('nan'))])
        with self.assertRaises(ValueError):e.merge_screenshot([dict(clean,at=i,sectionAt=i) for i in range(5)],clean)

    def test_reads_bypass_writer_lock_but_writes_remain_serialized(self):
        from contextlib import contextmanager

        class Result:
            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Conn:
            def __init__(self):
                self.queries = []

            def execute(self, query, params=None):
                self.queries.append(str(query))
                if 'SELECT frames,summary' in str(query):
                    return Result(([], None))
                return Result()

            def commit(self):
                pass

        conn = Conn()

        @contextmanager
        def connect():
            yield conn

        patches = (patch('youtube_feed_archive.is_retained', return_value=True),
                   patch('video_ocr.report', return_value={'status': 'none'}))
        with patches[0], patches[1]:
            result = e.handle(connect, dict(videoId='abcdefghijk'))
            self.assertEqual(result['frames'], [])
            self.assertFalse(any('pg_advisory_xact_lock' in query for query in conn.queries))

            conn.queries.clear()
            e.handle(connect, dict(videoId='abcdefghijk', action='write',
                                   assignedByUser=True, frames=[self.frame()]))
            self.assertTrue(any('pg_advisory_xact_lock' in query for query in conn.queries))

    def test_agreement_conflicts_dedup_and_time(self):
        def image(index,at,text):return dict(index=index,at=at,width=400,height=200,lines=[dict(text=text,numeric=True,bounds=[10,10,100,20],verified=False)])
        frames=[dict(dataUrl=str(i)) for i in range(3)]
        images=[image(0,30,'RSI 61.8'),image(1,32,'RSI 61.8')]
        result=o.compare_images(images,frames)
        self.assertEqual(result[0]['lines'][0]['readingStatus'],'repeated');self.assertFalse(result[0]['lines'][0]['verified'])
        result=o.compare_images(images+[image(2,34,'RSI 61.9')],frames)
        self.assertEqual(result[0]['lines'][0]['readingStatus'],'conflict')
        result=o.compare_images([image(0,30,'RSI 61.8'),image(1,300,'RSI 61.8')],frames)
        self.assertEqual(result[0]['lines'][0]['readingStatus'],'single')
        result=o.compare_images([image(0,30,'RSI 61.8'),image(1,32,'RSI 61.8')],[dict(dataUrl='same')]*2)
        self.assertEqual(result[0]['lines'][0]['readingStatus'],'single')

import os
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class EvidenceDatabaseTests(unittest.TestCase):
    def test_store_read_rate_limit_and_retention(self):
        import psycopg,uuid
        from psycopg import sql
        from contextlib import contextmanager
        import research_enhancements
        schema='evidence_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)));conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            research_enhancements.init(conn);conn.commit()
            @contextmanager
            def connect():yield conn
            try:
                payload=dict(videoId='abcdefghijk',action='write',assignedByUser=True,frames=[EvidenceTests().frame()])
                with patch('youtube_feed_archive.is_retained',return_value=False):
                    with self.assertRaises(ValueError):e.handle(connect,payload)
                conn.rollback()
                with patch('youtube_feed_archive.is_retained',return_value=True):
                    result=e.handle(connect,payload);self.assertTrue(result['frames'][0]['userProvided']);self.assertEqual(result['ocr']['status'],'pending')
                    with self.assertRaises(ValueError):e.handle(connect,payload)
                    conn.rollback()
                    result=e.handle(connect,dict(videoId='abcdefghijk'));self.assertEqual(len(result['frames']),1)
                    conn.execute("UPDATE bob_research_enhancements SET summary=%s::jsonb", ('{"kind":"ai","sections":[],"visualNotes":[{}]}',));conn.commit()
                    screenshot=dict(EvidenceTests().frame(),at=50,sourceKind='screenshot',sectionAt=45)
                    result=e.handle(connect,dict(videoId='abcdefghijk',action='append-screenshot',assignedByUser=True,frames=[screenshot]))
                    self.assertEqual(len(result['frames']),2)
                    self.assertEqual(result['summary']['kind'],'ai')
                    self.assertNotIn('visualNotes',result['summary'])
                    conn.execute("DELETE FROM bob_research_enhancements");conn.commit()
                    self.assertEqual(conn.execute('SELECT count(*) FROM bob_video_ocr').fetchone()[0],0)
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()
