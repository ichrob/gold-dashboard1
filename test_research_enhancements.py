import base64
import io
import json
import os
import unittest
from unittest.mock import patch
try:
    from PIL import Image
except ImportError:
    Image = None
import research_enhancements as r

VIDEO = 'wjLMQ7QfMiM'
SEGMENTS = [{'at': 0, 'text': 'Gold bleibt unter 4000 vorsichtig.'},
            {'at': 450, 'text': 'Nur wenn Gold über 4100 steigt, gilt das bullische Szenario.'}]
SPEC = 'https://i.ytimg.com/sb/' + VIDEO + '/storyboard3_L$L/$N.jpg?sqp=x|160#90#100#5#5#5000#M$M#signature'


class DB:
    def __init__(self, row=None, count=(0, 0)):
        self.row = row; self.count = count; self.queries = []; self.value = None
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, args=()):
        self.queries.append((query, args))
        self.value = self.row if query.startswith('SELECT fingerprint') else self.count if query.startswith('SELECT count') else None
        return self
    def fetchone(self): return self.value
    def commit(self): pass


class ResearchTests(unittest.TestCase):
    def test_summary_keeps_late_evidence(self):
        out = r.summary_checked({'sections': [{'label': 'Bedingung', 'text': 'Bullisch erst über 4100.', 'segmentIds': [1]}]}, SEGMENTS)
        self.assertEqual(out['sections'][0]['evidence'][0]['at'], 450)

    def test_summary_rejects_invented_prices_and_missing_evidence(self):
        for text, refs in [('Ziel 4500.', [1]), ('Gold steigt.', []), ('Gold steigt.', [7]), ('Gold steigt.', [True])]:
            with self.assertRaises(ValueError):
                r.summary_checked({'sections': [{'label': 'Test', 'text': text, 'segmentIds': refs}]}, SEGMENTS)

    def test_full_transcript_request_and_no_tools(self):
        def reader(req, timeout):
            body = json.loads(req.data)
            indexed = json.loads(body['contents'][0]['parts'][0]['text'])
            self.assertEqual([{'at': item['at'], 'text': item['text']} for item in indexed], SEGMENTS)
            self.assertEqual([item['id'] for item in indexed], [0, 1])
            schema = body['generationConfig']['responseSchema']
            self.assertEqual(schema['properties']['sections']['items']['required'], ['label', 'text', 'segmentIds'])
            self.assertNotIn('tools', body)
            self.assertNotIn('secret', req.full_url)
            return json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps({'sections': [{'label': 'Fazit', 'text': 'Gold unter 4000.', 'segmentIds': [0]}]})}]}}]}).encode()
        self.assertEqual(r.generate(SEGMENTS, 'secret', reader)['kind'], 'ai')

    def test_images_share_one_ai_request_and_only_coarse_visual_notes_survive(self):
        frame = {'at': 450, 'dataUrl': 'data:image/jpeg;base64,'+
                 base64.b64encode(bytes.fromhex('ffd8') + bytes(120) + bytes.fromhex('ffd9')).decode()}
        def reader(req, timeout):
            body=json.loads(req.data)
            self.assertEqual(len(body['contents']), 1)
            parts=body['contents'][0]['parts']
            self.assertEqual(parts[-1]['inlineData']['mimeType'], 'image/jpeg')
            self.assertEqual(parts[-1]['inlineData']['data'], frame['dataUrl'].split(',')[1])
            self.assertIn('frameNotes', body['generationConfig']['responseSchema']['properties'])
            response={'sections':[{'label':'Bedingung','text':'Gold über 4100.','segmentIds':[1]}],
                      'frameNotes':[{'frameId':0,'kind':'chart'},{'frameId':3,'kind':'chart'},
                                    {'frameId':0,'kind':'speaker'}]}
            return json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(response)}]}}]}).encode()
        out = r.generate(SEGMENTS, 'secret', reader, frames=[frame])
        self.assertEqual(out['sections'][0]['evidence'][0]['at'],450)
        self.assertEqual(out['visualNotes'], [{'frameId': 0, 'kind': 'chart', 'label': 'Mögliche Chartansicht'}])
        self.assertIn('nicht daraus abgelesen', out['scope'])

    def test_no_untrusted_frame_or_unverified_numbers(self):
        bad={'at': 4, 'dataUrl':'data:image/png;base64,'+('A'*150)}
        self.assertEqual(r.validated_frames([bad]),[])
        with self.assertRaises(ValueError):
            r.summary_checked({'sections':[{'label':'Kursziel','text':'Der Chart zeigt 5000.','segmentIds':[0]}]},SEGMENTS,
                              frames=[bad])

    def test_partial_grounding_retains_only_supported_sections(self):
        sections = [
            {'label': 'Kurzfazit', 'text': 'Gold bleibt unter 4000.', 'segmentIds': [0]},
            {'label': 'Long-Szenario', 'text': 'Gold steigt bis 4500.', 'segmentIds': [1]},
            {'label': 'Risiken', 'text': 'Gold steigt.', 'segmentIds': []},
        ]
        result = r.summary_checked({'sections': sections}, SEGMENTS, keep_valid_sections=True)
        self.assertTrue(result['partial'])
        self.assertEqual(len(result['sections']), 1)
        self.assertEqual(result['sections'][0]['evidence'][0]['at'], 0)
        self.assertIn('verworfen', result['note'])
        with self.assertRaises(ValueError):
            r.summary_checked({'sections': sections[1:]}, SEGMENTS, keep_valid_sections=True)
        with self.assertRaises(ValueError):
            r.summary_checked({'sections': sections}, SEGMENTS)

    def test_partial_generation_rejected(self):
        with self.assertRaises(ValueError):
            r.generate(SEGMENTS, 'secret', lambda *a, **k: b'{"candidates":[{"finishReason":"MAX_TOKENS"}]}')

    def test_frames_use_correct_sheet_and_time(self):
        plans = r.storyboard_plan(SPEC, VIDEO, [{'at': 132, 'label': 'Level'}])
        self.assertIn('/M1.jpg', plans[0]['url'])
        self.assertEqual((plans[0]['at'], plans[0]['col'], plans[0]['row']), (130, 1, 0))

    def test_frames_refuse_wrong_video_host_and_no_timing(self):
        for spec in [SPEC.replace(VIDEO, 'abcdefghijk'), SPEC.replace('i.ytimg.com', 'localhost'), SPEC.replace('#5000#', '#0#')]:
            self.assertEqual(r.storyboard_plan(spec, VIDEO, [{'at': 10}]), [])

    @unittest.skipIf(Image is None, "Pillow is installed only in the push runtime")
    def test_saved_frame_is_real_crop(self):
        im = Image.new('RGB', (800, 450), 'red'); im.paste((0, 255, 0), (160, 0, 320, 90))
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=100)
        frames = r.frames_saved(VIDEO, SPEC, [{'at': 5, 'label': 'Level'}], lambda *a, **k: buf.getvalue())
        crop = Image.open(io.BytesIO(base64.b64decode(frames[0]['dataUrl'].split(',')[1])))
        self.assertEqual(crop.size, (160, 90)); self.assertGreater(crop.getpixel((80, 40))[1], 240)

    @unittest.skipIf(Image is None, "Pillow required")
    def test_public_thumbnail_is_real_jpeg_and_explicitly_not_visual_evidence(self):
        image=Image.new('RGB', (480, 360), 'red')
        buf=io.BytesIO(); image.save(buf, 'JPEG')
        frame=r.public_cover(VIDEO, lambda req,timeout:buf.getvalue())
        self.assertTrue(frame['isCover'])
        self.assertIn('Titelbild',frame['source'])
        self.assertEqual(r.validated_frames([frame]),[])
        self.assertEqual(r.summary_fingerprint(SEGMENTS,[frame]),r.summary_fingerprint(SEGMENTS))
        Image.open(io.BytesIO(base64.b64decode(frame['dataUrl'].split(',',1)[1]))).verify()

    def test_new_frame_extractor_retries_old_failed_24h_attempt_without_ai_billing(self):
        db=DB(row=('other',None,None,False,True,'legacy','retry_paused'))
        thumbnail={'at':0,'isCover':True,'dataUrl':'data:image/jpeg;base64,'+'A'*120}
        with (patch.dict(os.environ,{},clear=True),
              patch('youtube_research.read_url',side_effect=ValueError('YouTube metadata unavailable')),
              patch.object(r,'public_cover',return_value=thumbnail) as cover,
              patch.object(r,'generate') as ai):
            out=r.handle(lambda:db,{'videoId':VIDEO,'channelId':r.CHANNEL,'segments':SEGMENTS})
        cover.assert_called_once()
        ai.assert_not_called()
        self.assertEqual(out['frames'][0]['isCover'],True)
        self.assertIn('Titelbild',out['frameStatus'])
        self.assertTrue(any('frame_version=%s' in q for q,_ in db.queries))

    @unittest.skipIf(Image is None, "Pillow required")
    def test_missing_storyboard_cell_does_not_discard_another_valid_cell(self):
        spec='https://i.ytimg.com/sb/'+VIDEO+'/storyboard3_L$L/$N.jpg?sqp=x|160#90#80#5#5#5000#M$M#signature'
        image=Image.new('RGB',(800,450),'green'); buf=io.BytesIO(); image.save(buf,'JPEG')
        calls=[]
        def reader(req,timeout):
            calls.append(req.full_url)
            if 'M0.jpg' in req.full_url: raise OSError('first sprite unavailable')
            return buf.getvalue()
        frames=r.frames_saved(VIDEO,spec,[{'at':5,'label':'First'},{'at':130,'label':'Second'}],reader)
        self.assertEqual(len(frames),1)
        self.assertEqual(frames[0]['at'],130)
        self.assertGreaterEqual(len(calls),2)

    def test_no_billing_confirmation_means_no_ai_request(self):
        db = DB(row=('other', None, None, False, True, r.FRAME_FORMAT_VERSION, 'retry_paused'))
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'secret'}, clear=True), patch.object(r, 'generate') as call:
            out = r.handle(lambda: db, {'videoId': VIDEO, 'channelId': r.CHANNEL, 'segments': SEGMENTS})
        call.assert_not_called(); self.assertIn('fehlt', out['summaryStatus'])
        self.assertFalse(any('INSERT INTO bob_research_ai_requests' in q for q, _ in db.queries))

    def test_quota_exhaustion_never_calls_ai(self):
        db = DB(row=('other', None, None, False, True), count=(10, 0))
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'secret', 'BOB_GEMINI_FREE_PROJECT': 'confirmed-no-billing'}, clear=True), patch.object(r, 'generate') as call:
            out = r.handle(lambda: db, {'videoId': VIDEO, 'channelId': r.CHANNEL, 'segments': SEGMENTS})
        call.assert_not_called(); self.assertIn('Abruflimit', out['summaryStatus'])

    def test_persisted_result_reused_without_key(self):
        fp = r.hashlib.sha256(json.dumps([r.MODEL, r.SUMMARY_FORMAT_VERSION, SEGMENTS], sort_keys=True).encode()).hexdigest()
        db = DB(row=(fp, {'kind': 'ai'}, [{'at': 5}], True, True, r.FRAME_FORMAT_VERSION, 'stored'))
        with patch.dict(os.environ, {}, clear=True), patch.object(r, 'generate') as call:
            out = r.handle(lambda: db, {'videoId': VIDEO, 'channelId': r.CHANNEL, 'segments': SEGMENTS})
        call.assert_not_called(); self.assertEqual(out['summary']['kind'], 'ai'); self.assertEqual(len(out['frames']), 1)

    def test_failure_hides_provider_details_and_no_retry(self):
        db = DB(row=('other', None, None, False, True, r.FRAME_FORMAT_VERSION, 'retry_paused'))
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'secret', 'BOB_GEMINI_FREE_PROJECT': 'confirmed-no-billing'}, clear=True), patch.object(r, 'generate', side_effect=RuntimeError('secret raw provider body')) as call:
            out = r.handle(lambda: db, {'videoId': VIDEO, 'channelId': r.CHANNEL, 'segments': SEGMENTS})
        self.assertEqual(call.call_count, 1); self.assertNotIn('secret', json.dumps(out))


if __name__ == '__main__': unittest.main()
