"""Bounded research quote probe; never an executable-price or order approval.

The pinned SDK supplies BidPrice/AskPrice, but no documented per-side source
clock. Reception time and LastTime must therefore never become quote times.
"""
from datetime import datetime, timezone
import math
import re
from urllib.parse import urlsplit

METRICS = ('BidPrice', 'AskPrice', 'BidVolume', 'AskVolume')
QUOTE_CODES = {'QUOTE_OBSERVED', 'QUOTE_INCOMPLETE', 'QUOTE_UNAVAILABLE',
               'IDENTITY_UNCONFIRMED'}


def validate_request(value):
    from snaptrade_portfolio import isin
    if not isinstance(value, dict) or set(value) not in ({'isin', 'currency'}, {'productId', 'isin', 'currency', 'exchangeId'}):
        raise ValueError('Exact product identity required')
    if not isin(value['isin']) or value['currency'] not in ('EUR', 'CHF'):
        raise ValueError('Invalid product identity')
    for key in ('productId', 'exchangeId') if 'productId' in value else ():
        if not isinstance(value[key], str) or not re.fullmatch(r'[1-9][0-9]{0,15}', value[key]):
            raise ValueError('Invalid broker identifier')
    return dict(value)


def identify_request(api, request):
    """Optional exact-ISIN lookup; ambiguity and truncated results fail closed."""
    request = validate_request(request)
    if 'productId' in request:
        return request
    from degiro_connector.trading.models.product_search import LookupRequest
    response = api.product_search(product_request=LookupRequest(
        search_text=request['isin'], limit=20, offset=0), raw=True)
    rows = response.get('products') if isinstance(response, dict) else None
    if not isinstance(rows, list) or len(rows) >= 20:
        return None
    matches = [r for r in rows if isinstance(r, dict) and
               r.get('isin') == request['isin'] and r.get('currency') == request['currency']]
    if len(matches) != 1:
        return None
    row = matches[0]
    try:
        return validate_request({**request, 'productId': str(row.get('id', '')),
                                 'exchangeId': str(row.get('exchangeId', ''))})
    except ValueError:
        return None


def resolve_product(value, response):
    """Require the selected broker ID, ISIN, currency and exchange together."""
    value = validate_request(value)
    if 'productId' not in value:
        return None
    data = response.get('data') if isinstance(response, dict) else None
    row = data.get(value['productId']) if isinstance(data, dict) else None
    if not isinstance(row, dict):
        return None
    if any(str(row.get(k)) != value[k] for k in ('isin', 'currency', 'exchangeId')):
        return None
    if 'productId' not in value or str(row.get('id')) != value['productId']:
        return None
    feed_id = row.get('vwdId')
    # Support only the documented numeric issueid mapping in this first probe.
    # vwdkey and unknown mapping types stay blocked rather than being guessed.
    if row.get('vwdIdentifierType') != 'issueid' or not isinstance(feed_id, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', feed_id):
        return None
    return feed_id


def quote_transport_permitted(method, url, session_id=None):
    p = urlsplit(url)
    if p.scheme != 'https' or p.netloc != 'degiro.quotecast.vwdservices.com' or p.fragment:
        return False
    if method == 'POST' and p.path == '/CORS/request_session':
        return True
    return (isinstance(session_id, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id))
            and p.path == '/CORS/' + session_id and not p.query and method in ('GET', 'POST'))


class QuoteObservation:
    """Merge partial messages without refreshing unchanged sides on heartbeat."""
    def __init__(self, feed_id):
        self.feed_id = feed_id
        self.values = {}
        self.received = {}

    def accept(self, metrics, received_at):
        for metric in metrics:
            name = metric.metric_type.value
            if metric.product_id != self.feed_id or name not in METRICS:
                continue
            value = metric.value
            try:
                number = float(value) if not isinstance(value, bool) else float('nan')
            except (ValueError, TypeError):
                number = float('nan')
            valid = math.isfinite(number) and (number > 0 if name.endswith('Price') else number >= 0)
            # Invalid updates invalidate an earlier side rather than retaining it.
            self.values[name] = number if valid else None
            self.received[name] = received_at

    def report(self):
        bid, ask = self.values.get('BidPrice'), self.values.get('AskPrice')
        complete = bid is not None and ask is not None and bid <= ask
        return {'code': 'QUOTE_OBSERVED' if complete else 'QUOTE_INCOMPLETE',
                'bid': bid, 'ask': ask,
                'bidReceivedAt': self.received.get('BidPrice'),
                'askReceivedAt': self.received.get('AskPrice'),
                'bidSourceAt': None, 'askSourceAt': None,
                'sourceTimesVerified': False, 'delayVerified': False,
                'isExecutableQuote': False, 'tradeApproved': False,
                'liveOrdersEnabled': False, 'researchOnly': True,
                'reason': 'SIDE_SOURCE_TIMESTAMPS_UNAVAILABLE' if complete else 'TWO_SIDED_QUOTE_UNAVAILABLE'}


def safe_report(data):
    """Allow only typed quote evidence out of the isolated worker."""
    result = QuoteObservation('').report()
    result['code'] = data['code']
    for key in ('bid', 'ask'):
        value = data.get(key)
        result[key] = value if type(value) in (int, float) and math.isfinite(value) and value > 0 else None
    for key in ('bidReceivedAt', 'askReceivedAt'):
        value = data.get(key)
        try:
            clock = datetime.fromisoformat(value) if isinstance(value, str) and len(value) <= 40 else None
            result[key] = clock.isoformat() if clock and clock.tzinfo is not None else None
        except ValueError:
            result[key] = None
    if result['code'] == 'QUOTE_OBSERVED' and (result['bid'] is None or result['ask'] is None
            or result['bid'] > result['ask'] or not result['bidReceivedAt'] or not result['askReceivedAt']):
        result['code'] = 'QUOTE_INCOMPLETE'
    result['twoSidedObserved'] = result['code'] == 'QUOTE_OBSERVED'
    result['identityMatched'] = result['code'] in {'QUOTE_OBSERVED', 'QUOTE_INCOMPLETE'}
    result['ok'] = result['twoSidedObserved']
    result['reason'] = ('SIDE_SOURCE_TIMESTAMPS_UNAVAILABLE' if result['ok'] else result['code'])
    result['checkedAt'] = datetime.now(timezone.utc).isoformat()
    return result


def sample(api, details, request):
    """At most three polls, no retries, no alternate hosts, no order methods."""
    import logging
    import requests
    from degiro_connector.core.constants.headers import HEADERS
    from degiro_connector.quotecast.models.ticker import TickerRequest
    from degiro_connector.quotecast.tools.ticker_fetcher import TickerFetcher
    from degiro_connector.quotecast.tools.ticker_to_metric_list import TickerToMetricList

    request = validate_request(request)
    request = identify_request(api, request)
    if request is None:
        return {'code': 'IDENTITY_UNCONFIRMED'}
    product = api.get_products_info(product_list=[int(request['productId'])], raw=True)
    feed_id = resolve_product(request, product)
    if feed_id is None:
        return {'code': 'IDENTITY_UNCONFIRMED'}
    data = details.get('data') if isinstance(details, dict) else None
    token = data.get('id') if isinstance(data, dict) else None
    if type(token) is not int or token <= 0:
        return {'code': 'QUOTE_UNAVAILABLE'}

    class QuoteSession(requests.Session):
        session_id = None

        def send(self, request, **kwargs):
            if not quote_transport_permitted(request.method, request.url, self.session_id):
                raise ValueError('Outside quote transport allowlist')
            kwargs.update(timeout=(3, 5), allow_redirects=False)
            response = super().send(request, **kwargs)
            if response.status_code != 200:
                raise ValueError('Quote transport rejected response')
            if len(response.content) > 262144:
                raise ValueError('Quote response too large')
            return response

    logger = logging.getLogger('bob.degiro.quote-probe')
    observation = QuoteObservation(feed_id)
    with QuoteSession() as session:
        session.trust_env = False
        session.headers.update(HEADERS)
        session_id = TickerFetcher.get_session_id(user_token=token, session=session, logger=logger)
        if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id):
            return {'code': 'QUOTE_UNAVAILABLE'}
        session.session_id = session_id
        subscription = TickerRequest(request_type='subscription', request_map={feed_id: list(METRICS)})
        if TickerFetcher.subscribe(subscription, session_id, session=session, logger=logger) is not True:
            return {'code': 'QUOTE_UNAVAILABLE'}
        # A single decoder preserves the protocol's registration map across polls.
        decoder = TickerToMetricList()
        try:
            for _ in range(3):
                ticker = TickerFetcher.fetch_ticker(session_id, session=session, logger=logger)
                if ticker is None:
                    return {'code': 'QUOTE_UNAVAILABLE'}
                # The SDK ignores `ue` (unavailable), which would retain an old side.
                # Fail the sample instead of returning an obsolete two-sided quote.
                import json
                messages = json.loads(ticker.json_text)
                if not isinstance(messages, list) or any(not isinstance(m, dict) or m.get('m') in ('ue', 'd', 'sr') for m in messages):
                    return {'code': 'QUOTE_UNAVAILABLE'}
                observation.accept(decoder.parse(ticker), datetime.now(timezone.utc).isoformat())
                if observation.report()['code'] == 'QUOTE_OBSERVED':
                    break
            return observation.report()
        finally:
            # Cleanup only; no repeated login or subscription on failure.
            TickerFetcher.subscribe(TickerRequest(request_type='unsubscription',
                request_map={feed_id: list(METRICS)}), session_id, session=session, logger=logger)
