"""Synthetic protocol/HTTP tests; never logs in or contacts a broker."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import timedelta
import degiro_quote_probe as q
import degiro_readonly as reader

REQUEST = {'productId': '123', 'isin': 'US0378331005', 'currency': 'EUR', 'exchangeId': '456'}
PRODUCT = {'data': {'123': {**REQUEST, 'id': '123', 'vwdId': '789', 'vwdIdentifierType': 'issueid'}}}


def metric(name, value, product='789'):
    return SimpleNamespace(metric_type=SimpleNamespace(value=name), value=value, product_id=product)


class QuoteTests(unittest.TestCase):
    def test_identity_never_uses_first_search_hit(self):
        self.assertEqual(q.resolve_product(REQUEST, PRODUCT), '789')
        for key in ('id', 'isin', 'currency', 'exchangeId', 'vwdId', 'vwdIdentifierType'):
            changed = json.loads(json.dumps(PRODUCT)); changed['data']['123'][key] = 'wrong'
            self.assertIsNone(q.resolve_product(REQUEST, changed), key)
        self.assertIsNone(q.resolve_product(REQUEST, {'data': {'999': PRODUCT['data']['123']}}))

    def test_invalid_requests(self):
        for payload in ({}, {**REQUEST, 'url': 'https://evil.example'}, {**REQUEST, 'productId': True},
                        {**REQUEST, 'isin': 'US0378331006'}, {**REQUEST, 'exchangeId': '../login'}):
            with self.assertRaises(ValueError): q.validate_request(payload)

    def test_transport_rejects_orders_redirects_and_unbound_sessions(self):
        root = 'https://degiro.quotecast.vwdservices.com'
        self.assertTrue(q.quote_transport_permitted('POST', root+'/CORS/request_session?version=1'))
        self.assertTrue(q.quote_transport_permitted('GET', root+'/CORS/abc', 'abc'))
        for method, url in [('POST', 'https://trader.degiro.nl/trading/secure/v5/order'),
                            ('GET', root+'/CORS/other'), ('DELETE', root+'/CORS/abc'),
                            ('GET', root+'/CORS/abc?token=x'), ('GET', root+'/CORS/abc#x'),
                            ('GET', 'http://degiro.quotecast.vwdservices.com/CORS/abc'),
                            ('GET', 'https://evil.example/CORS/abc')]:
            self.assertFalse(q.quote_transport_permitted(method, url, 'abc'))

    def test_partial_updates_heartbeat_and_last_trade_do_not_retimestamp_bid(self):
        o = q.QuoteObservation('789')
        o.accept([metric('BidPrice', 10)], '2026-01-01T12:00:00+00:00')
        o.accept([], '2026-01-01T12:00:01+00:00')
        o.accept([metric('LastTime', '12:00:02'), metric('AskPrice', 11, 'wrong')], '2026-01-01T12:00:02+00:00')
        self.assertEqual(o.report()['code'], 'QUOTE_INCOMPLETE')
        o.accept([metric('AskPrice', 11)], '2026-01-01T12:00:03+00:00')
        r = o.report()
        self.assertEqual(r['code'], 'QUOTE_OBSERVED')
        self.assertEqual(r['bidReceivedAt'], '2026-01-01T12:00:00+00:00')
        self.assertIsNone(r['bidSourceAt']); self.assertIsNone(r['askSourceAt'])
        self.assertFalse(r['isExecutableQuote']); self.assertFalse(r['sourceTimesVerified'])

    def test_bad_price_invalidates_previous_quote(self):
        for value in (None, True, 'NaN', float('inf'), -1, 0, 'broken'):
            o = q.QuoteObservation('789'); o.accept([metric('BidPrice', 10), metric('AskPrice', 11)], 't1')
            o.accept([metric('BidPrice', value)], 't2')
            self.assertEqual(o.report()['code'], 'QUOTE_INCOMPLETE')
        o = q.QuoteObservation('789'); o.accept([metric('BidPrice', 12), metric('AskPrice', 11)], 't1')
        self.assertEqual(o.report()['code'], 'QUOTE_INCOMPLETE')

    def test_parent_strips_sensitive_worker_fields_and_preserves_no_orders(self):
        reader._LAST_ATTEMPT = 0
        with patch.object(reader, 'status', return_value={'ready': True}), patch.object(reader.subprocess, 'run') as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({'code': 'QUOTE_OBSERVED', 'token': 'SECRET', 'bid': 10, 'ask': 11, 'bidReceivedAt':'2026-01-01T12:00:00+00:00','askReceivedAt':'2026-01-01T12:00:01+00:00'}))
            result = reader.probe('001234', REQUEST)
            self.assertTrue(result['twoSidedObserved']); self.assertFalse(result['isExecutableQuote'])
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertEqual(json.loads(run.call_args.kwargs['input'])['quoteRequest'], REQUEST)
            self.assertEqual(reader.probe('', REQUEST)['code'], 'COOLDOWN')
        reader._LAST_ATTEMPT = 0

    def test_real_sdk_protocol_partial_frames_and_cleanup(self):
        from degiro_connector.quotecast.tools.ticker_fetcher import TickerFetcher
        from degiro_connector.quotecast.models.ticker import Ticker
        frames = [[{'m':'a_req','v':['789.BidPrice',1]}, {'m':'a_req','v':['789.AskPrice',2]}, {'m':'un','v':[1,10]}], [{'m':'un','v':[2,11]}]]
        api = Mock(); api.get_products_info.return_value = PRODUCT
        tickers = [Ticker(json_text=json.dumps(f), request_duration=timedelta(seconds=1)) for f in frames]
        with patch.object(TickerFetcher, 'get_session_id', return_value='abc'), patch.object(TickerFetcher, 'subscribe', return_value=True) as sub, patch.object(TickerFetcher, 'fetch_ticker', side_effect=tickers) as fetch:
            r = q.sample(api, {'data': {'id': 42}}, REQUEST)
        self.assertEqual(r['code'], 'QUOTE_OBSERVED'); self.assertEqual(fetch.call_count, 2)
        self.assertEqual(sub.call_args.args[0].request_type, 'unsubscription')
        api.get_products_info.assert_called_once_with(product_list=[123], raw=True)
        self.assertEqual(api.method_calls, [unittest.mock.call.get_products_info(product_list=[123], raw=True)])

    def test_missing_identity_never_contacts_quotecast(self):
        from degiro_connector.quotecast.tools.ticker_fetcher import TickerFetcher
        api = Mock(); api.get_products_info.return_value = {}
        with patch.object(TickerFetcher, 'get_session_id') as connect:
            self.assertEqual(q.sample(api, {'data': {'id': 42}}, REQUEST)['code'], 'IDENTITY_UNCONFIRMED')
            connect.assert_not_called()

    def test_unavailable_protocol_message_does_not_leave_old_bid(self):
        from degiro_connector.quotecast.tools.ticker_fetcher import TickerFetcher
        from degiro_connector.quotecast.models.ticker import Ticker
        api = Mock(); api.get_products_info.return_value = PRODUCT
        ticker = Ticker(json_text='[{"m":"ue","v":[1]}]', request_duration=timedelta())
        with patch.object(TickerFetcher,'get_session_id',return_value='abc'), patch.object(TickerFetcher,'subscribe',return_value=True), patch.object(TickerFetcher,'fetch_ticker',return_value=ticker) as fetch:
            self.assertEqual(q.sample(api, {'data':{'id':42}}, REQUEST)['code'], 'QUOTE_UNAVAILABLE')
            self.assertEqual(fetch.call_count, 1)

    def test_quote_probe_does_not_replace_portfolio_test_receipt(self):
        reader._LAST_RESULT = {'code':'READ_OK'}
        with patch.object(reader, '_probe', return_value={'code':'QUOTE_INCOMPLETE'}):
            reader.probe('', REQUEST)
        self.assertEqual(reader._LAST_RESULT['code'], 'READ_OK')
        self.assertEqual(reader._LAST_QUOTE_RESULT['code'], 'QUOTE_INCOMPLETE')
        reader._LAST_RESULT = reader._LAST_QUOTE_RESULT = None

    def test_success_without_values_or_clocks_is_not_confirmed(self):
        result = q.safe_report({'code':'QUOTE_OBSERVED', 'bid':'SECRET', 'ask':11})
        self.assertFalse(result['twoSidedObserved']); self.assertNotIn('SECRET',json.dumps(result))

    def test_worker_quote_branch_reads_no_portfolio_and_never_orders(self):
        from degiro_readonly_worker import run
        import logging
        previous = logging.root.manager.disable
        api = Mock(); api.get_client_details.return_value = {'data':{'intAccount':123, 'id':42}}
        try:
            with patch.dict('os.environ', {'BOB_DEGIRO_USERNAME':'synthetic','BOB_DEGIRO_PASSWORD':'synthetic'}), patch('degiro_connector.trading.api.API', return_value=api), patch.object(q, 'sample', return_value={'code':'QUOTE_INCOMPLETE'}) as sample:
                result = run('', quote_request=REQUEST)
            self.assertEqual(result['code'], 'QUOTE_INCOMPLETE')
            api.get_update.assert_not_called()
            self.assertEqual([c[0] for c in api.method_calls], ['connect', 'get_client_details'])
            sample.assert_called_once_with(api, {'data':{'intAccount':123,'id':42}}, REQUEST)
        finally:
            logging.disable(previous)

    def test_real_sdk_transport_is_bounded_and_redirects_disabled(self):
        import requests
        api = Mock(); api.get_products_info.return_value = PRODUCT
        frames = [{'m':'a_req','v':['789.BidPrice',1]}, {'m':'a_req','v':['789.AskPrice',2]}, {'m':'un','v':[1,10]}, {'m':'un','v':[2,11]}]
        bodies = [json.dumps({'sessionId':'abc'}), '[]', json.dumps(frames), '[]']
        calls = []
        def send(session, request, **kwargs):
            calls.append((request.method, request.url, kwargs))
            response = requests.Response(); response.status_code = 200
            response._content = bodies[len(calls)-1].encode()
            return response
        with patch.object(requests.Session, 'send', new=send):
            result = q.sample(api, {'data':{'id':42}}, REQUEST)
        self.assertEqual(result['code'], 'QUOTE_OBSERVED')
        self.assertEqual([c[0] for c in calls], ['POST','POST','GET','POST'])
        for _, url, options in calls:
            self.assertTrue(url.startswith('https://degiro.quotecast.vwdservices.com/CORS/'))
            self.assertFalse(options['allow_redirects'])
            self.assertEqual(options['timeout'], (3,5))

    def test_heartbeat_only_stops_after_three_polls(self):
        from degiro_connector.quotecast.tools.ticker_fetcher import TickerFetcher
        from degiro_connector.quotecast.models.ticker import Ticker
        api = Mock(); api.get_products_info.return_value = PRODUCT
        heartbeat = Ticker(json_text='[{"m":"h"}]',request_duration=timedelta())
        with patch.object(TickerFetcher,'get_session_id',return_value='abc'), patch.object(TickerFetcher,'subscribe',return_value=True), patch.object(TickerFetcher,'fetch_ticker',return_value=heartbeat) as fetch:
            self.assertEqual(q.sample(api, {'data':{'id':42}}, REQUEST)['code'], 'QUOTE_INCOMPLETE')
        self.assertEqual(fetch.call_count, 3)
