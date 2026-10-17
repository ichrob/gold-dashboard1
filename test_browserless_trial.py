import contextlib
import io
import unittest
from unittest.mock import patch, MagicMock
import browserless_trial as trial

class BrowserlessTrialTests(unittest.TestCase):
    def test_missing_token_never_connects(self):
        connect=MagicMock()
        with patch.dict('os.environ',{},clear=True),contextlib.redirect_stdout(io.StringIO()):
            trial.run_once(connect)
        connect.assert_not_called()

    def test_reserved_attempt_never_calls_provider(self):
        conn=MagicMock();connect=MagicMock()
        connect.return_value.__enter__.return_value=conn
        conn.execute.return_value.fetchone.side_effect=[([],),({'sections':[{'evidence':[{'at':18}]}]},),None]
        with patch.dict('os.environ',{'BROWSERLESS_API_TOKEN':'private'}),patch('youtube_feed_archive.sanitize',return_value=[{}]),patch('youtube_feed_archive.selected_ids',return_value=['ZZcYAKr9FGY']),patch.object(trial,'capture') as capture,contextlib.redirect_stdout(io.StringIO()):
            trial.run_once(connect)
        capture.assert_not_called()

    def test_secret_errors_are_not_returned(self):
        with patch.object(trial.requests,'post',side_effect=RuntimeError('secret-token')):
            self.assertEqual(trial.capture('secret-token','ZZcYAKr9FGY',[{'at':18}]),('capture-failed',[]))

    def response(self, body):
        import json
        response=MagicMock();response.status_code=200
        response.iter_content.return_value=[json.dumps(body).encode()]
        return response

    def test_wrapped_response_preserves_diagnostic(self):
        body={'data':{'videoId':'ZZcYAKr9FGY','status':'playback-unavailable','frames':[]},'type':'application/json'}
        with patch.object(trial.requests,'post') as post:
            post.return_value.__enter__.return_value=self.response(body)
            self.assertEqual(trial.capture('private','ZZcYAKr9FGY',[]),('playback-unavailable',[]))

    def test_wrapped_identity_still_checked(self):
        with patch.object(trial.requests,'post') as post:
            post.return_value.__enter__.return_value=self.response({'data':{'videoId':'wrong','frames':[]}})
            self.assertEqual(trial.capture('private','ZZcYAKr9FGY',[]),('identity-unconfirmed',[]))

    def test_unwrapped_and_unknown_diagnostic(self):
        with patch.object(trial.requests,'post') as post:
            post.return_value.__enter__.return_value=self.response({'videoId':'ZZcYAKr9FGY','status':'secret-token','frames':[]})
            self.assertEqual(trial.capture('private','ZZcYAKr9FGY',[]),('no-video-frames',[]))

    def test_http_error_no_retry(self):
        with patch.object(trial.requests,'post') as post:
            post.return_value.__enter__.return_value.status_code=401
            self.assertEqual(trial.capture('private','ZZcYAKr9FGY',[]),('http-401',[]))
            self.assertEqual(post.call_count,1)
            self.assertFalse(post.call_args.kwargs['allow_redirects'])

if __name__=='__main__':unittest.main()
