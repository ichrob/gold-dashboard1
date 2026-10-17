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

    def test_http_error_no_retry(self):
        with patch.object(trial.requests,'post') as post:
            post.return_value.__enter__.return_value.status_code=401
            self.assertEqual(trial.capture('private','ZZcYAKr9FGY',[]),('http-401',[]))
            self.assertEqual(post.call_count,1)
            self.assertFalse(post.call_args.kwargs['allow_redirects'])

if __name__=='__main__':unittest.main()
