import copy
import unittest
import gold_research as g

class ResearchTests(unittest.TestCase):
    now=1791334800
    def feed(self,title='Gold will rise today',date='Wed, 07 Oct 2026 00:00:00 GMT',url='https://www.fxstreet.com/analysis/gold'):
        return f'<rss><channel><item><title>{title}</title><description>Gold price outlook today.</description><pubDate>{date}</pubDate><link>{url}</link></item></channel></rss>'.encode()
    def test_past_is_not_forecast_or_dollar_inversion(self):
        self.assertEqual(g.classify('Gold rises today','Dollar falls.','Internet')['outlook'],'UNKLAR')
        self.assertEqual(g.classify('Gold price update','Dollar rises today.','Internet')['trend'],'UNKLAR')
        self.assertEqual(g.classify('Gold will rise today','', 'Internet')['outlook'],'LONG')
        self.assertEqual(g.classify('Gold will not rise today','', 'Internet')['outlook'],'UNKLAR')
        self.assertEqual(g.classify('Gold could rise if yields fall','', 'Internet')['outlook'],'UNKLAR')
        self.assertEqual(g.classify('Gold will rise today','', 'YouTube')['outlook'],'UNKLAR')
    def test_dates_bad_links_and_duplicates(self):
        items,n=g.parse_feed(self.feed(),g.SOURCES[0],self.now)
        self.assertEqual(n,1);self.assertTrue(items[0]['current'])
        self.assertFalse(g.parse_feed(self.feed(date='unknown'),g.SOURCES[0],self.now)[0][0]['current'])
        self.assertFalse(g.parse_feed(self.feed(date='Wed, 07 Oct 2030 00:00:00 GMT'),g.SOURCES[0],self.now)[0][0]['current'])
        self.assertEqual(g.parse_feed(self.feed(url='https://evil.example/gold'),g.SOURCES[0],self.now)[0],[])
        r=g.collect(self.now,lambda source:self.feed())
        self.assertEqual(len(r['items']),1)
    def test_no_majority_from_one_publisher_or_stale_articles(self):
        item=g.parse_feed(self.feed(),g.SOURCES[0],self.now)[0][0]
        r=dict(checkedAt=self.now,items=[item,{**item,'id':'another'}],sources=[])
        self.assertEqual(g.summarize(r,self.now)['consensus'],'ABWARTEN')
        r['items'][1]['publisher']='Independent fixture'
        self.assertEqual(g.summarize(r,self.now)['consensus'],'LONG')
        self.assertEqual(g.summarize(r,self.now+1801)['consensus'],'ABWARTEN')
        r['items'][1]['horizon']='längerfristig'
        self.assertEqual(g.summarize(r,self.now)['consensus'],'ABWARTEN')
    def test_failure_counts_not_as_neutral_and_html_stripped(self):
        def fail(_):raise OSError('offline')
        r=g.summarize(g.collect(self.now,fail),self.now)
        self.assertEqual(r['successfulFeeds'],0);self.assertEqual(r['scanned'],0);self.assertEqual(r['consensus'],'ABWARTEN')
        self.assertEqual(g.clean('<script>evil()</script><b>Gold</b>'),'Gold')
        with self.assertRaises(ValueError):g.parse_feed(b'<!DOCTYPE rss><rss/>',g.SOURCES[0],self.now)
    def test_research_tab_and_safe_rendering_contract(self):
        from pathlib import Path
        source=Path('Bob.html').read_text()
        panel=source[source.index('<section id="goldResearchPanel"'):source.index('</main>')]
        self.assertIn("research:'Recherche'",source)
        self.assertIn("move(byId('goldResearchPanel'),'research')",source)
        self.assertIn("['research','⌕','Recherche']",source)
        self.assertIn("n.textContent=text",panel)
        self.assertNotIn('.innerHTML',panel)
        self.assertIn("r.videosAnalyzed",panel)
        self.assertIn("r.fullTexts",panel)

    def test_only_explicit_structured_article_body(self):
        import json
        body='Gold will rise today. '*20
        raw=('<script type="application/ld+json">'+json.dumps({'@graph':[{'articleBody':body}]})+'</script>').encode()
        self.assertIn('Gold will rise',g.article_text(raw))
        self.assertIsNone(g.article_text(b'<html>Gold will rise today</html>'))

if __name__=='__main__':unittest.main()
