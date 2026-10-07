import json
import unittest
from unittest.mock import patch
import youtube_research as y

URL='https://www.youtube.com/watch?v=abcdefghijk'
TITLE='Gold price outlook for today explained'
CHANNEL='World Gold Council'
ROW={'url':URL,'title':TITLE,'channel':CHANNEL}

class ScreenshotTests(unittest.TestCase):
    def test_visible_link_needs_no_search(self):
        def no_search(_):raise AssertionError('No search needed')
        for text in [URL,'YouTube\nyoutu.be/abcdefghijk\nGold']:
            self.assertEqual(y.resolve_screenshot(text,no_search)['url'],URL)
    def test_title_and_channel_must_both_match(self):
        text='YouTube\n'+TITLE+'\n'+CHANNEL+'\nSubscribe'
        self.assertEqual(y.resolve_screenshot(text,lambda _: [ROW])['url'],URL)
        for bad in [TITLE+'\nAnother Channel',TITLE[:22]+'...\n'+CHANNEL,'Gold\n'+CHANNEL]:
            with self.assertRaises(ValueError):y.resolve_screenshot(bad,lambda _:[ROW])
    def test_duplicate_titles_and_multiple_links_refused(self):
        with self.assertRaises(ValueError):y.resolve_screenshot(TITLE+'\n'+CHANNEL,lambda _:[ROW,{**ROW,'url':'https://www.youtube.com/watch?v=lmnopqrstuv'}])
        with self.assertRaises(ValueError):y.resolve_screenshot(URL+'\nhttps://youtu.be/lmnopqrstuv')
    def test_search_parses_data_without_executing_script(self):
        data={'contents':[{'videoRenderer':{'videoId':'abcdefghijk','title':{'runs':[{'text':TITLE}]},'ownerText':{'runs':[{'text':CHANNEL}]}}}]}
        raw=('var ytInitialData = '+json.dumps(data)+'; throw Error("untrusted");').encode()
        rows=y.search_videos('Gold outlook',lambda _:raw)
        self.assertEqual(rows,[{**ROW,'publishedText':'','viewsText':''}])
    def test_wrapped_title_without_channel_offers_selection_without_analysis(self):
        text='Beschreibung\nGold Futures & Spot: Watch This Support\nZone\n200 6.390 23h\nLikes Aufrufe Hochgeladen\nGold Elliott Wave analysis'
        rows=[{**ROW,'title':'Gold Futures & Spot: Watch This Support Zone','channel':'MCO Markets','publishedText':'23 hr ago','viewsText':'6,396 views'},
              {**ROW,'url':'https://www.youtube.com/watch?v=lmnopqrstuv','title':'Gold Futures & Spot: Watch This Support Zone','channel':'MCO Markets','publishedText':'6 days ago'}]
        with self.assertRaises(y.VideoSelectionRequired) as caught:
            y.resolve_screenshot(text,lambda _:rows)
        with patch.object(y,'resolve_screenshot',side_effect=caught.exception),patch.object(y,'manual') as analysis:
            result=y.from_screenshot({'screenshotText':text})
        self.assertFalse(result['ok']);self.assertEqual(result['candidates'],rows);analysis.assert_not_called()

    def test_resolved_video_does_not_claim_analysis_when_captions_fail(self):
        with patch.object(y,'resolve_screenshot',return_value=ROW),patch.object(y,'manual',side_effect=ValueError('empty captions')):
            r=y.from_screenshot({'screenshotText':'fixture'})
        self.assertFalse(r['ok']);self.assertEqual(r['resolved']['url'],URL);self.assertNotIn('item',r)
    def test_resolved_video_automatically_runs_content_analysis(self):
        with patch.object(y,'resolve_screenshot',return_value=ROW),patch.object(y,'manual',return_value={'transcriptWords':100}) as analysis:
            r=y.from_screenshot({'screenshotText':'fixture'})
        self.assertTrue(r['ok']);analysis.assert_called_once_with({'url':URL})

if __name__=='__main__':unittest.main()
