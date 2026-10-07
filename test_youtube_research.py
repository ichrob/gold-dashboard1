import json
import unittest
from unittest.mock import patch
import youtube_research as y
import gold_research as g

ID='abcdefghijk'
URL='https://www.youtube.com/watch?v='+ID
CAP= 'https://www.youtube.com/api/timedtext?v='+ID+'&lang=en'

class YoutubeTests(unittest.TestCase):
    def data(self,status='OK',caption=CAP):
        p={'playabilityStatus':{'status':status},'videoDetails':{'videoId':ID,'channelId':'UCsl6Z6p7GOkczo8Cv-GH6Dg','author':'MCO Markets','title':'Gold will fall today'},'captions':{'playerCaptionsTracklistRenderer':{'captionTracks':[{'baseUrl':caption,'languageCode':'en','kind':'asr'}]}}}
        return ('var ytInitialPlayerResponse = '+json.dumps(p)+';').encode()
    def captions(self):
        return ('<transcript><text start="12">Gold will rise today. '+('This report discusses the market and its current economic environment. '*6)+'</text></transcript>').encode()
    def test_public_caption_content_not_title(self):
        result=y.analyze(URL,lambda url:self.data() if url==URL else self.captions())
        self.assertTrue(result['transcriptAnalyzed']);self.assertEqual(result['outlook'],'LONG')
        self.assertEqual(result['goldMoments'],[12]);self.assertTrue(result['automaticCaptions'])
        self.assertNotIn('text',result)
    def test_no_access_or_identity_bypass(self):
        for url in ['https://evil.example/watch?v='+ID,'http://www.youtube.com/watch?v='+ID,'https://www.youtube.com@evil.example/watch?v='+ID,'https://www.youtube.com/watch?v=bad']:
            with self.assertRaises(ValueError):y.video_id(url)
        for status in ('LOGIN_REQUIRED','UNPLAYABLE','ERROR'):
            with self.assertRaises(ValueError):y.player_metadata(self.data(status),ID)
        with self.assertRaises(ValueError):y.player_metadata(self.data(),'otheridabcd')
        for cap in ['https://evil.example/api/timedtext?v='+ID,'https://www.youtube.com/api/timedtext?v=otheridabcd']:
            with self.assertRaises(ValueError):y.analyze(URL,lambda _:self.data(caption=cap))
    def test_empty_json3_xml_and_short_caption(self):
        with self.assertRaises(ValueError):y.parse_captions(b'')
        with self.assertRaises(ValueError):y.parse_captions(b'<!DOCTYPE transcript><transcript/>')
        segments=y.parse_captions(json.dumps({'events':[{'tStartMs':2300,'segs':[{'utf8':'Gold rises'}]}]}).encode())
        self.assertEqual(segments[0]['at'],2.3)
        with self.assertRaises(ValueError):y.assess(segments,'en')
    def test_manual_text_explicitly_unverified_and_not_consensus(self):
        with patch.dict(y._manual,{},clear=True),patch.object(y,'read_url',return_value=self.data()):
            item=y.manual({'url':URL,'language':'de','transcript':'Gold wird heute steigen. '+('Eine Untersuchung der gegenwärtigen Marktlage und der allgemeinen Wirtschaft. '*7)})
            self.assertEqual(item['outlook'],'LONG');self.assertFalse(item['trustedTranscript']);self.assertIsNone(item['publishedAt'])
            self.assertEqual(len(y.manual_items()),1)
            report=g.summarize(dict(checkedAt=100,sources=[],items=[item]),100)
            self.assertEqual(report['videosAnalyzed'],1);self.assertEqual(report['consensus'],'ABWARTEN')
    def test_auto_source_channel_and_publication_preserved(self):
        result=y.analyze(URL,lambda url:self.data() if url==URL else self.captions())
        item={'url':URL,'sourceId':'mco-video','publishedAt':10,'publisher':'MCO Markets'}
        with patch.object(y,'analyze',return_value=result):y.enrich(item)
        self.assertEqual(item['publishedAt'],10);self.assertTrue(item['trustedTranscript'])
        with patch.object(y,'analyze',return_value={**result,'channelId':'wrong'}):
            bad=y.enrich({'url':URL,'sourceId':'mco-video'})
            self.assertFalse(bad['transcriptAnalyzed']);self.assertNotIn('trustedTranscript',bad)
    def test_pasted_transcript_replaces_unavailable_discovered_video(self):
        report={'checkedAt':100,'sources':[],'items':[{'channelId':g.MCO_CHANNEL,'title':'Gold outlook','url':URL,'kind':'YouTube','publishedAt':None,'coverage':'Videometadaten','outlook':'UNKLAR','horizon':'unbekannt'}]}
        with patch.dict(y._manual,{},clear=True),patch.object(g,'_report',report),patch.object(y,'read_url',return_value=self.data()):
            y.manual({'url':URL,'transcript':'Gold will rise today. '+('This text discusses the market and its development. '*8)})
            r=g.snapshot()
            self.assertEqual(len(r['items']),1);self.assertEqual(r['videosAnalyzed'],1)
            self.assertFalse(r['items'][0]['trustedTranscript'])

    def test_context_retains_conditions(self):
        result=y.assess([{'at':0,'text':'Gold remains bearish unless it breaks above 4260. Support is at 4165. '+('Economic context for this analysis is uncertain. '*8)}],'en')
        self.assertIn('unless it breaks above 4260',result['context'])
        self.assertEqual(result['outlook'],'UNKLAR')
    def test_empty_first_track_uses_second_and_discloses_all_empty(self):
        p=json.loads(self.data().decode().split(' = ')[1].rstrip(';'))
        p['captions']['playerCaptionsTracklistRenderer']['captionTracks'].append({'baseUrl':CAP+'&alt=de','languageCode':'de','kind':'asr'})
        raw=('var ytInitialPlayerResponse = '+json.dumps(p)+';').encode()
        result=y.analyze(URL,lambda u:raw if u==URL else self.captions() if 'alt=de' in u else b'')
        self.assertTrue(result['transcriptAnalyzed'])
        with self.assertRaisesRegex(ValueError,'vorhanden'):
            y.analyze(URL,lambda u:raw if u==URL else b'')
    def test_other_channels_and_non_gold_refused(self):
        for details in [{'channelId':'other','title':'Gold outlook'},{'channelId':g.MCO_CHANNEL,'title':'Silver outlook'}]:
            with self.assertRaises(ValueError):y.require_mco(details)

    def test_manual_automatic_fetch_result(self):
        result=y.analyze(URL,lambda url:self.data() if url==URL else self.captions())
        with patch.object(y,'analyze',return_value=result),patch.dict(y._manual,{},clear=True):
            item=y.manual({'url':URL});self.assertEqual(item['url'],URL);self.assertTrue(item['transcriptAnalyzed'])

if __name__=='__main__':unittest.main()
