import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from datetime import datetime
import future_analysis as f
import market_cards as m
from test_future_analysis import payload, NOW

class SharedFeedTests(unittest.TestCase):
    def test_cards_and_reference_share_request_and_preserve_time(self):
        data = payload()
        data['chart']['result'][0]['meta'].update(regularMarketPrice=4200, chartPreviousClose=3900)
        with patch.object(f, '_chart_cache', {}), patch.object(f, '_chart_retry', {}), patch.object(f, '_chart_errors', {}), patch.object(f, '_fetch_chart', return_value=data) as fetch, patch.object(f, 'datetime') as clock, patch.object(m.time, 'time', return_value=NOW.timestamp()):
            clock.now.return_value = NOW
            clock.fromtimestamp.side_effect = datetime.fromtimestamp
            reference = f.fetch_reference(NOW)
            card = m.fetch_quote(f.SYMBOL)
            fetch.assert_called_once_with('5m', '5d')
            self.assertEqual(card['at'], reference['underlyingAt'])
            self.assertIsNone(card['changePct'])
            self.assertEqual(data['chart']['result'][0]['meta']['chartPreviousClose'],3900)

    def test_rate_limit_blocks_other_interval_and_cards_until_deadline(self):
        error = HTTPError('https://example.invalid',429,'limited',{'Retry-After':'1200'},None)
        with patch.object(f, '_chart_cache', {}), patch.object(f, '_chart_retry', {}), patch.object(f, '_chart_errors', {}), patch.object(f, '_chart_failures', {}), patch.object(f.time, 'monotonic', return_value=100) as clock, patch.object(f, '_fetch_chart', side_effect=error) as fetch:
            with self.assertRaises(HTTPError): f.fetch_chart('1h','6mo')
            with self.assertRaises(URLError): m.fetch_quote(f.SYMBOL)
            with self.assertRaises(URLError): f.fetch_reference(NOW)
            fetch.assert_called_once()
            self.assertEqual(f.reference_failure(URLError('cooldown'))[0],1200)
            clock.return_value = 1300
            fetch.side_effect = None
            fetch.return_value = {'recovered': True}
            self.assertEqual(f.fetch_chart('5m','5d'),{'recovered':True})
            self.assertEqual(fetch.call_count,2)

if __name__ == '__main__': unittest.main()
