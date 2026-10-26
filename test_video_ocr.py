import base64
import io
import json
import os
import unittest
from unittest.mock import patch
import video_ocr as o

class OcrTests(unittest.TestCase):
    def test_box_clamps_and_does_not_promote_confidence(self):
        rows=[([[-2,2],[200,2],[200,30],[-2,30]],'RSI 61.8',.99),([[0,0]]*4,'bad',float('nan'))]
        lines=o.lines_checked(rows,80,40,2)
        self.assertEqual(lines[0]['bounds'],[0,1,80,14]);self.assertFalse(lines[0]['verified']);self.assertTrue(lines[0]['numeric'])
    def test_timeout_never_calls_paid_fallback(self):
        with patch.object(o.subprocess,'run',side_effect=o.subprocess.TimeoutExpired('ocr',35)) as run:
            r=o.run([]);self.assertEqual(r['status'],'error');self.assertEqual(run.call_count,1)
            self.assertNotIn('GEMINI_API_KEY',run.call_args.kwargs['env']);self.assertEqual(run.call_args.kwargs['timeout'],35)
    def test_real_offline_image(self):
        from importlib.util import find_spec
        if find_spec('rapidocr_onnxruntime') is None:
            self.skipTest('OCR dependencies not installed')
        try:
            from PIL import Image,ImageDraw,ImageFont
        except ImportError:self.skipTest('OCR dependencies not installed')
        im=Image.new('RGB',(480,270),'white');draw=ImageDraw.Draw(im)
        font=ImageFont.truetype('DejaVuSans.ttf',24)
        draw.text((15,35),'XAU/USD 15m',fill='black',font=font)
        draw.text((15,90),'RSI (14): 61.8',fill='black',font=font)
        draw.text((15,150),'Gold: 4200.50',fill='black',font=font)
        b=io.BytesIO();im.save(b,'JPEG');frame=dict(at=30,dataUrl='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode())
        result=o.run([frame,dict(frame,isCover=True)])
        self.assertEqual(result['status'],'complete');self.assertEqual(len(result['images']),1)
        text=' '.join(l['text'] for l in result['images'][0]['lines'])
        self.assertIn('61.8',text);self.assertIn('4200.50',text)
        self.assertTrue(all(l['verified'] is False for l in result['images'][0]['lines']))

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class OcrDatabaseTests(unittest.TestCase):
    def test_cached_version_changed_images_and_cascade(self):
        import psycopg,uuid
        from psycopg import sql
        from contextlib import contextmanager
        schema='ocr_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)));conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            conn.execute('CREATE TABLE bob_research_enhancements(video_id TEXT PRIMARY KEY,frames JSONB,updated_at TIMESTAMPTZ DEFAULT now())');o.init(conn);conn.commit()
            @contextmanager
            def connect():yield conn
            try:
                conn.execute("INSERT INTO bob_research_enhancements(video_id,frames) VALUES('test','[{\"isCover\":true}]'::jsonb)");conn.commit()
                with patch.object(o,'run'):
                    calls=[]
                    def runner(frames):calls.append(frames);return {'status':'no-timed-images','images':[]}
                    self.assertEqual(o.tick(connect,runner),'no-timed-images');self.assertEqual(o.tick(connect,runner),'idle');self.assertEqual(len(calls),1)
                    self.assertEqual(o.report(conn,'test')['status'],'no-timed-images')
                    conn.execute("UPDATE bob_research_enhancements SET frames='[{\"isCover\":false}]'::jsonb");conn.commit()
                    self.assertEqual(o.report(conn,'test')['status'],'pending')
                    o.tick(connect,runner);self.assertEqual(len(calls),2)
                    conn.execute('DELETE FROM bob_research_enhancements');self.assertEqual(conn.execute('SELECT count(*) FROM bob_video_ocr').fetchone()[0],0)
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()
