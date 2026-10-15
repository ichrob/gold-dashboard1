"""Automatic MCO caption retry deduplication never evades provider quotas."""
import unittest
from unittest.mock import Mock, patch

import research_transcript_provider as provider
import youtube_research as research

VIDEO = 'abcdefghijk'
URL = 'https://www.youtube.com/watch?v=' + VIDEO


class Reply:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        return b'<html>Player metadata fixture</html>'


class ResearchBackoffTests(unittest.TestCase):
    def setUp(self):
        research._cache.clear()
        research._provider_failures.clear()

    def player(self, identity=VIDEO):
        return dict(videoDetails=dict(videoId=identity,
            channelId=provider.CHANNEL,title='Gold outlook',author='MCO Markets'),
            captions=dict(playerCaptionsTracklistRenderer=dict(captionTracks=[])))

    def test_video_budget_does_not_hit_internal_route_every_15_minutes(self):
        opener=Mock()
        opener.open.return_value=Reply()
        error=provider.TranscriptError('video_limit')
        with patch.object(research.urllib.request, 'build_opener', return_value=opener), \
             patch.object(research, 'player_metadata', return_value=self.player()), \
             patch.object(provider, 'request', side_effect=error) as request, \
             patch.object(research.time, 'time', return_value=10000):
            with self.assertRaises(provider.TranscriptError):
                research.analyze(URL)
            with self.assertRaises(provider.TranscriptError):
                research.analyze(URL)
            request.assert_called_once_with(VIDEO)
            self.assertEqual(research._provider_failures[VIDEO][1], 'video_limit')

        with patch.object(research.urllib.request, 'build_opener', return_value=opener), \
             patch.object(research, 'player_metadata', return_value=self.player()), \
             patch.object(provider, 'request', side_effect=error) as request, \
             patch.object(research.time, 'time', return_value=13601):
            with self.assertRaises(provider.TranscriptError):
                research.analyze(URL)
            request.assert_called_once_with(VIDEO)

    def test_old_video_cache_evicted_on_new_verified_mco_list(self):
        first=dict(channelId=provider.CHANNEL,url=URL)
        second=dict(channelId=provider.CHANNEL,
                    url='https://www.youtube.com/watch?v=lmnopqrstuv')
        research._provider_failures[VIDEO]=(1, 'cooldown')
        research._provider_failures['lmnopqrstuv']=(1,'video_limit')
        research.retain_only([second])
        self.assertNotIn(VIDEO,research._provider_failures)
        self.assertIn('lmnopqrstuv',research._provider_failures)
        research.retain_only([first])
        self.assertNotIn('lmnopqrstuv',research._provider_failures)

    def test_valid_manual_or_direct_caption_path_not_gated_by_provider_failure(self):
        # Source ownership and captions are checked before consulting the
        # optional Supadata negative cache.
        research._provider_failures[VIDEO]=(10000,'provider_auth_paused')
        caption_url='https://www.youtube.com/api/timedtext?v='+VIDEO+'&lang=en'
        original=self.player()
        original['captions']['playerCaptionsTracklistRenderer']['captionTracks']=[
            {'baseUrl':caption_url,'languageCode':'en'}]
        data=b'<transcript><text start="2">Gold could rise. '+(
            b'Gold market momentum and structure matter for this forecast. '*8
        )+b'</text></transcript>'
        opener=Mock()
        opener.open.return_value=Reply()
        with patch.object(research.urllib.request,'build_opener',return_value=opener), \
             patch.object(research,'player_metadata',return_value=original), \
             patch.object(research,'read_url',side_effect=[b'player',data]) as fetch, \
             patch.object(provider,'request') as request, \
             patch('research_enhancements.request',return_value={'summaryStatus':'test'}):
            # A caller-supplied reader is intentionally independent from the
            # live negative cache. It must still validate the caption URL.
            result=research.analyze(URL,fetch=fetch)
        self.assertTrue(result['transcriptAnalyzed'])
        request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
