import copy
import json
import unittest
from unittest.mock import patch
import gold_research as g
import youtube_research as y
import youtube_feed_archive as archive

class PublicFallbackTests(unittest.TestCase):
    now=1800000000
    def item(self,n):
        return dict(id='youtube-Video'+str(n).zfill(6),url='https://www.youtube.com/watch?v=Video'+str(n).zfill(6),
            title='Gold outlook '+str(n),kind='YouTube',channelId=g.MCO_CHANNEL,publisher='MCO Markets',
            publishedAt=self.now-n*86400,coverage='Videometadaten',outlook='UNKLAR',horizon='unbekannt')
    def player(self,item,members=False):
        identity=y.video_id(item['url'])
        value=dict(videoDetails=dict(videoId=identity,channelId=g.MCO_CHANNEL,title=item['title']),
            playabilityStatus=dict(status='UNPLAYABLE' if members else 'OK',reason='Members-only content' if members else ''),
            captions={'playerCaptionsTracklistRenderer':{'captionTracks':[dict(baseUrl='https://www.youtube.com/api/timedtext?v='+identity,languageCode='en')]}})
        return ('var ytInitialPlayerResponse = '+json.dumps(value)+';').encode()
    def test_three_restricted_uploads_do_not_exhaust_analysis_slots(self):
        items=[self.item(n) for n in range(1,10)];calls=[]
        def probe(url):
            calls.append(url);item=next(x for x in items if x['url']==url)
            return self.player(item,int(y.video_id(url)[-6:])<=3)
        selected,restricted,pages,fallback=g.choose_research_videos(items,probe)
        self.assertEqual([i['title'] for i in selected],['Gold outlook 4','Gold outlook 5','Gold outlook 6'])
        self.assertEqual(len(restricted),3);self.assertEqual(len(calls),6)
        self.assertTrue(fallback);self.assertTrue(all(i['publicFallback'] for i in selected))
        self.assertTrue(all(i['transcriptAnalyzed'] is False for i in restricted))
        self.assertEqual(len(archive.sanitize(selected)),3)
        self.assertTrue(all(i['publicFallback'] for i in archive.sanitize(selected)))
    def test_memberships_never_invoke_an_alternative_provider(self):
        items=[self.item(n) for n in range(1,13)]
        selected,restricted,pages,fallback=g.choose_research_videos(items,lambda url:self.player(next(i for i in items if i['url']==url),True))
        self.assertEqual(len(pages),9);self.assertEqual(len(restricted),9);self.assertEqual(selected,items[:3]);self.assertFalse(fallback)
        with patch('research_transcript_provider.request') as provider:
            for item in selected:y.enrich(item,player_raw=pages[item['url']])
            provider.assert_not_called()
    def test_network_failure_is_not_membership(self):
        items=[self.item(n) for n in range(1,5)]
        def fail(_):raise OSError('offline')
        selected,restricted,pages,fallback=g.choose_research_videos(items,fail)
        self.assertEqual(selected,items[:3]);self.assertEqual(restricted,[]);self.assertEqual(pages,{})
        self.assertFalse(fallback);self.assertNotIn('transcriptAccess',selected[0])
    def test_older_free_analysis_cannot_replace_newest_upload_direction(self):
        newest=[self.item(n) for n in range(1,4)]
        older=[dict(self.item(n),trustedTranscript=True,transcriptAnalyzed=True,outlook='LONG',publicFallback=True) for n in range(4,7)]
        report=g.summarize(dict(checkedAt=self.now,items=older,latestUploads=newest,restrictedUploads=newest,accessFallback=True,sources=[]),self.now)
        self.assertEqual(report['videosAnalyzed'],3);self.assertEqual(report['mcoOutlook'],'NICHT_ANALYSIERT')
        self.assertEqual(report['mcoAnalyzed'],0);self.assertIn('Ersatzvideos',report['mcoReason'])
        restored=g.summarize(dict(checkedAt=None,archived=True,items=older,accessFallback=True,sources=[]),self.now)
        self.assertEqual(restored['mcoOutlook'],'NICHT_ANALYSIERT')
    def test_preflight_watch_response_is_reused_for_captions(self):
        item=self.item(4);raw=self.player(item)
        captions=('<transcript><text start="12">Gold will rise today. '+('This report discusses support and resistance in the gold market. '*6)+'</text></transcript>').encode()
        with patch.dict(y._cache,{},clear=True),patch.object(y,'read_url',return_value=captions) as reader,patch('research_enhancements.request',return_value={}),patch('research_transcript_provider.request') as provider:
            result=y.analyze(item['url'],fetch=y.read_url,verified_item=item,player_raw=raw)
        self.assertTrue(result['transcriptAnalyzed']);self.assertEqual(reader.call_count,1)
        self.assertIn('/api/timedtext',reader.call_args.args[0]);provider.assert_not_called()
