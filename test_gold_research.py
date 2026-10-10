import json
import unittest
from unittest.mock import patch
import gold_research as g

class ResearchTests(unittest.TestCase):
    now=1791334800
    def feed(self,channel=None):
        channel=channel or g.MCO_CHANNEL
        entries=''
        for identity,title in [('abcdefghijk','Gold outlook'),('lmnopqrstuv','Gold outlook'),('silverabcde','Silver outlook')]:
            entries+=f'<entry><yt:channelId>{channel}</yt:channelId><title>{title}</title><published>2026-10-07T00:00:00Z</published><link href="https://www.youtube.com/watch?v={identity}"/><media:group><media:description>Gold is mentioned in a standard channel footer.</media:description></media:group></entry>'
        return f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/"><yt:channelId>{channel}</yt:channelId>{entries}</feed>'.encode()
    def test_reduced_weekend_research_schedule(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        utc = ZoneInfo('UTC')
        weekday=datetime(2026,10,9,22,59,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()
        closed=datetime(2026,10,10,9,0,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()
        monday=datetime(2026,10,12,0,0,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()
        self.assertEqual(g.refresh_interval(weekday),900)
        self.assertEqual(g.refresh_interval(closed),7200)
        self.assertEqual(g.refresh_interval(monday),900)
        data=dict(checkedAt=closed-3600,items=[],sources=[])
        self.assertTrue(g.summarize(data,closed)['fresh'])
        self.assertEqual(g.summarize(data,closed)['intervalSeconds'],7200)

    def test_only_mco_gold_and_distinct_video_ids(self):
        self.assertEqual(len(g.SOURCES),1);self.assertEqual(g.SOURCES[0]['publisher'],'MCO Markets')
        r=g.collect(self.now,lambda _:self.feed())
        self.assertEqual(len(r['items']),2);self.assertEqual(r['sources'][0]['scanned'],3)
        self.assertNotEqual(r['items'][0]['url'],r['items'][1]['url'])
        with self.assertRaises(ValueError):g.parse_feed(self.feed('other'),g.SOURCES[0],self.now)
    def test_old_other_sources_and_manual_items_excluded(self):
        item=g.parse_feed(self.feed(),g.SOURCES[0],self.now)[0][0]
        other={**item,'channelId':'other','publisher':'Other'}
        silver={**item,'title':'Silver outlook'}
        report=dict(checkedAt=self.now,items=[item,other,silver],sources=[])
        self.assertEqual(len(g.summarize(report,self.now)['items']),1)
        with patch.object(g,'_report',report),patch('youtube_research.manual_items',return_value=[other,silver]):
            self.assertEqual(len(g.snapshot()['items']),1)
    def test_one_channel_never_becomes_independent_consensus(self):
        items=g.parse_feed(self.feed(),g.SOURCES[0],self.now)[0]
        for item in items:item.update(trustedTranscript=True,outlook='LONG',horizon='Intraday')
        r=g.summarize(dict(checkedAt=self.now,items=items,sources=[]),self.now)
        self.assertEqual(r['consensus'],'ABWARTEN');self.assertEqual(r['counts']['LONG'],2)
        self.assertEqual(g.summarize(dict(checkedAt=self.now,items=items,sources=[]),self.now+1801)['counts']['LONG'],0)
    def test_channel_page_fallback_scoped_to_selected_uploads(self):
        def row(title,identity):return {'richItemRenderer':{'content':{'lockupViewModel':{'contentId':identity,'contentType':'LOCKUP_CONTENT_TYPE_VIDEO','metadata':{'lockupMetadataViewModel':{'title':{'content':title}}}}}}}
        root={'metadata':{'channelMetadataRenderer':{'externalId':g.MCO_CHANNEL}},'contents':{'twoColumnBrowseResultsRenderer':{'tabs':[{'tabRenderer':{'selected':True,'content':{'richGridRenderer':{'contents':[row('Gold outlook','abcdefghijk'),row('Silver outlook','lmnopqrstuv')]}}}}]}},'recommendations':row('Gold other channel','wrongabcdef')}
        raw=('var ytInitialData = '+json.dumps(root)+';').encode()
        items,n=g.channel_listing(raw,self.now)
        self.assertEqual(n,2);self.assertEqual(len(items),1);self.assertIsNone(items[0]['publishedAt'])
        root['metadata']['channelMetadataRenderer']['externalId']='other'
        with self.assertRaises(ValueError):g.channel_listing(('var ytInitialData = '+json.dumps(root)).encode(),self.now)
    def test_failure_not_counted_as_neutral(self):
        def fail(_):raise OSError('offline')
        r=g.summarize(g.collect(self.now,fail),self.now)
        self.assertEqual(r['successfulFeeds'],0);self.assertEqual(r['scanned'],0);self.assertEqual(r['counts']['UNKLAR'],0)
        with self.assertRaises(ValueError):g.parse_feed(b'<!DOCTYPE rss><rss/>',g.SOURCES[0],self.now)
    def test_conditional_text_not_unconditional_prediction(self):
        self.assertEqual(g.classify('Gold will rise today','','Internet')['outlook'],'LONG')
        self.assertEqual(g.classify('Gold will not rise today','','Internet')['outlook'],'UNKLAR')
        self.assertEqual(g.classify('Gold could rise if yields fall','','Internet')['outlook'],'UNKLAR')
    def test_research_safe_rendering(self):
        from pathlib import Path
        source=Path('Bob.html').read_text();panel=source[source.index('<section id="goldResearchPanel"'):source.index('</main>')]
        self.assertIn('n.textContent=text',panel);self.assertNotIn('.innerHTML',panel);self.assertIn('x.context',panel)
        self.assertNotIn('FXStreet',panel);self.assertNotIn('World Gold Council',panel)

if __name__=='__main__':unittest.main()
