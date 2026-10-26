"""Personal DEGIRO holdings reader. No orders, refresh fees, or broker login.

Only the user-owned Personal API key is accepted. Configuration is encrypted
before using the existing private settings store; no credentials in responses.
Holdings never enter product approvals, MyTrade, or paper account balances.
"""
import base64
import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import math
import os
import re
import threading
import time
import zlib
from collections import Counter
import snaptrade_portfolio as portfolio
import snaptrade_gold_history as gold_history
import snaptrade_trade_insights as insights
import snaptrade_quality as quality
import snaptrade_csv_link as csv_link
import snaptrade_identity as identity
import snaptrade_trades as trades
import snaptrade_quotes as holding_quotes
import degiro_research_review
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ORIGIN = 'https://api.snaptrade.com'
INTERVAL = 600
BACKGROUND_INTERVAL = 21600
CATALOG_RECHECK_SECONDS = 86400  # Manual broker instrument-list test; never an intraday price feed.
MAX_BODY = 2_000_000
_LOCK = threading.RLock()
_FETCH_LOCK = threading.Lock()
_CONFIG = None
_GENERATION = 0
_LOADED = False
_THREAD = None
_WAKE = threading.Event()
_NEXT = 0.0
_LAST_ATTEMPT = 0.0
_INTERACTIVE_UNTIL = 0.0
_STATE = {'code': 'SETUP_REQUIRED', 'snapshot': None}
_LEDGER = {}
_LEDGER_OWNER = None
_QUOTE_THREAD = None
_QUOTE_CURSOR = 0
_CATALOG_LOCK = threading.Lock()
_CATALOG_LAST_ATTEMPT = 0.0
_CATALOG_STATE = {'code': 'NOT_TESTED'}
# One bounded account-scoped symbol lookup, never order preflight or quote.
_SYMBOL_LOCK = threading.Lock()
_SYMBOL_ACCOUNT_ID = None  # Internal only, never in authenticated status/diagnostics.
_SYMBOL_PROBED = False
_SYMBOL_STATE = {'code': 'NOT_TESTED'}
ID = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
# SnapTrade Personal shares a 10-requests/minute bucket for account data.
# One holdings cycle uses positions, balances and orders (3 calls), so reserve
# two spare slots and cap historical activity reads to five pages (5 calls).
# Five-page request budget stays fixed. Larger histories resume in later cycles.
ACTIVITY_OFFSETS = tuple(range(0, 2500, 500))
HISTORY_MAX_ROWS = 20_000
HISTORY_MAX_BYTES = 4_000_000
HISTORY_JOURNAL_BYTES = 3_000_000
HISTORY_PAGING_VERSION = 1

def activity_rows(data):
    # Lossless removal of empty optional placeholders reduces encrypted history
    # memory without dropping any observed amounts, identities or timestamps.
    return [{k:v for k,v in row.items() if k in ('key','name','date','type') or v not in (None,'')}
            for row in portfolio.journal_rows(data,'activities',number,text)]


def activity_due(old, now=None):
    now = time.time() if now is None else now
    elapsed = now - old.get('attemptedEpoch', 0)
    resumable = (old.get('code') == 'READ_OK' and old.get('activityCoverageReason') == 'PAGE_LIMIT'
                 and old.get('pagingVersion') == HISTORY_PAGING_VERSION
                 and type(old.get('nextOffset')) is int
                 and 0 < old['nextOffset'] < HISTORY_MAX_ROWS)
    return elapsed >= (INTERVAL if resumable else 86400) or old.get('schemaVersion') != trades.SCHEMA or old.get('pagingVersion') != HISTORY_PAGING_VERSION

# A separate, filtered historical trade-coverage observation; these are
# account-history BUY/SELL counts, never a complete account audit or FIFO proof.
TRADE_COVERAGE_OFFSETS = (0, 1000, 2000)
TRADE_COVERAGE_INTERVAL = 7 * 86400
TRADE_COVERAGE_SCHEMA = 1


class ReadError(Exception):
    def __init__(self, code, retry_after=0):
        self.code = code
        self.retry_after = retry_after


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def cipher():
    # The isolated paper smoke workflow intentionally has no crypto packages.
    # Encryption is needed only when the owner configures a real connection.
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ReadError('CRYPTO_UNAVAILABLE') from None
    secret = os.environ.get('PUSH_SERVICE_TOKEN', '')
    if not secret:
        raise ReadError('STORE_UNAVAILABLE')
    key = hashlib.sha256(('bob-snaptrade-personal-v1\0' + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def storage(action, payload=None):
    base = os.environ.get('PUSH_SERVICE_URL', '').rstrip('/')
    token = os.environ.get('PUSH_SERVICE_TOKEN', '')
    if not base or not token:
        raise ReadError('STORE_UNAVAILABLE')
    if not base.startswith(('https://', 'http://')):
        base = 'https://' + base
    request = Request(base + '/snaptrade-settings/' + action,
                      data=json.dumps(payload or {}).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'X-Bob-Push-Token': token})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError()
        return json.loads(body)
    except Exception:
        raise ReadError('STORE_UNAVAILABLE') from None


def validate_config(payload):
    if not isinstance(payload, dict) or set(payload) != {'clientId', 'consumerKey', 'personalFreeConfirmed'}:
        raise ValueError('Nur Personal-Zugangsdaten zulässig.')
    if payload['personalFreeConfirmed'] is not True:
        raise ValueError('Kostenlosen Personal-Zugang bestätigen.')
    result = {}
    for field in ('clientId', 'consumerKey'):
        value = payload[field]
        if not isinstance(value, str) or not 8 <= len(value) <= 256 or not re.fullmatch(r'[A-Za-z0-9_.~+/=-]+', value):
            raise ValueError('Ungültiger Personal-Schlüssel.')
        result[field] = value
    result['personalFreeConfirmed'] = True
    return result


def load_config():
    global _CONFIG, _LOADED
    with _LOCK:
        if _LOADED:
            return
        data = storage('read')
        sealed = data.get('sealed')
        try:
            config = validate_config(json.loads(cipher().decrypt(sealed.encode()))) if sealed else None
        except Exception:
            raise ReadError('SETTINGS_UNREADABLE') from None
        _CONFIG, _LOADED = config, True


def configure(payload):
    global _CONFIG, _LOADED, _GENERATION, _NEXT, _LAST_ATTEMPT, _CATALOG_LAST_ATTEMPT, _SYMBOL_PROBED, _SYMBOL_ACCOUNT_ID
    config = validate_config(payload)
    sealed = cipher().encrypt(json.dumps(config).encode()).decode()
    with _LOCK:
        if storage('save', {'sealed': sealed}).get('saved') is not True:
            raise ReadError('STORE_UNAVAILABLE')
        _CONFIG, _LOADED = config, True
        _GENERATION += 1
        _NEXT = 0
        _LAST_ATTEMPT = 0
        _STATE.clear()
        _STATE.update(code='READY', snapshot=None)
        _CATALOG_LAST_ATTEMPT = 0.0
        _CATALOG_STATE.clear(); _CATALOG_STATE.update(code='NOT_TESTED')
        _SYMBOL_PROBED, _SYMBOL_ACCOUNT_ID = False, None
        _SYMBOL_STATE.clear(); _SYMBOL_STATE.update(code='NOT_TESTED')
    start()
    _WAKE.set()
    return status()


def disconnect():
    global _CONFIG, _LOADED, _GENERATION, _NEXT, _LAST_ATTEMPT, _LEDGER_OWNER, _CATALOG_LAST_ATTEMPT, _SYMBOL_PROBED, _SYMBOL_ACCOUNT_ID
    with _LOCK:
        if storage('delete').get('deleted') is not True:
            raise ReadError('STORE_UNAVAILABLE')
        _CONFIG, _LOADED = None, True
        _GENERATION += 1
        _NEXT = 0
        _LAST_ATTEMPT = 0
        _STATE.clear()
        _STATE.update(code='SETUP_REQUIRED', snapshot=None)
        _LEDGER.clear()
        _LEDGER_OWNER = None
        _CATALOG_LAST_ATTEMPT = 0.0
        _CATALOG_STATE.clear(); _CATALOG_STATE.update(code='NOT_TESTED')
        _SYMBOL_PROBED, _SYMBOL_ACCOUNT_ID = False, None
        _SYMBOL_STATE.clear(); _SYMBOL_STATE.update(code='NOT_TESTED')
    return status()


def permitted(path):
    return path in ('/authorizations', '/brokerages/DEGIRO/instruments') or any(re.fullmatch(pattern, path) for pattern in (
        rf'/connections/{ID}/accounts', rf'/accounts/{ID}/positions/all', rf'/accounts/{ID}/balances/v2',
        rf'/accounts/{ID}/orders', rf'/accounts/{ID}/activities'))


def api_get(path, config, params=None):
    if not permitted(path):
        raise ReadError('PATH_REJECTED')
    params = params or {}
    if params:
        permitted_standard = (path.endswith('/activities') and set(params) == {'offset', 'limit'}
                              and params['limit'] == 500 and type(params['offset']) is int
                              and 0 <= params['offset'] < HISTORY_MAX_ROWS and params['offset'] % 500 == 0)
        permitted_filtered = (path.endswith('/activities') and set(params) == {'offset', 'limit', 'type'}
                              and params['limit'] == 1000 and params['offset'] in TRADE_COVERAGE_OFFSETS
                              and params['type'] == 'BUY,SELL')
        if not (permitted_standard or permitted_filtered):
            raise ReadError('PATH_REJECTED')
    query = urlencode({'clientId': config['clientId'], 'timestamp': int(time.time()), **params})
    # Current official SDK signs the exact resource path used by the request.
    signed = json.dumps({'content': None, 'path': path, 'query': query}, sort_keys=True, separators=(',', ':'))
    signature = base64.b64encode(hmac.new(config['consumerKey'].encode(), signed.encode(), hashlib.sha256).digest()).decode()
    request = Request(ORIGIN + path + '?' + query, method='GET', headers={
        'Accept': 'application/json', 'Signature': signature, 'User-Agent': 'BobPersonalReadOnly/1.0'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ReadError('RESPONSE_TOO_LARGE')
        return json.loads(body)
    except HTTPError as exc:
        retry_after = 0
        if exc.code == 429:
            for key in ('Retry-After', 'X-RateLimit-Reset', 'X-RateLimit-Account-Reset'):
                raw = (exc.headers or {}).get(key, '')
                if re.fullmatch(r'[0-9]{1,6}', str(raw)):
                    retry_after = max(retry_after, min(86400, int(raw)))
        raise ReadError({401: 'AUTH_REQUIRED', 403: 'ACCESS_DENIED', 429: 'RATE_LIMITED', 402: 'PLAN_REQUIRED'}.get(exc.code, 'PROVIDER_UNAVAILABLE'), retry_after) from None
    except ReadError:
        raise
    except Exception:
        raise ReadError('PROVIDER_UNAVAILABLE') from None


def api_search_account_symbol(account_id, config, query):
    """One account-supported symbol reference search; POST has no trading effect.

    Signed exactly as documented for Personal API. Never accepts arbitrary
    paths, query terms or account IDs from the mobile client.
    """
    import degiro_catalog
    if (not isinstance(account_id, str) or not re.fullmatch(ID, account_id)
            or query != degiro_catalog.SEEDS[0][0]):
        raise ReadError('PATH_REJECTED')
    path = '/accounts/' + account_id + '/symbols'
    body = {'substring': query}
    canonical_query = urlencode({'clientId': config['clientId'], 'timestamp': int(time.time())})
    signed = json.dumps({'content': body, 'path': path, 'query': canonical_query},
                        sort_keys=True, separators=(',', ':'))
    signature = base64.b64encode(hmac.new(config['consumerKey'].encode(),
                                         signed.encode(), hashlib.sha256).digest()).decode()
    request = Request(ORIGIN + path + '?' + canonical_query,
                      data=json.dumps(body, separators=(',', ':')).encode('utf-8'),
                      method='POST', headers={'Accept': 'application/json',
                                             'Content-Type': 'application/json',
                                             'Signature': signature,
                                             'User-Agent': 'BobPersonalReadOnly/1.0'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(200_001)
        if len(raw) > 200_000:
            raise ReadError('RESPONSE_TOO_LARGE')
        return json.loads(raw)
    except HTTPError as exc:
        raise ReadError({401:'AUTH_REQUIRED',403:'ACCESS_DENIED',
                         429:'RATE_LIMITED',402:'PLAN_REQUIRED'}.get(
                             exc.code,'SEARCH_UNAVAILABLE')) from None
    except ReadError:
        raise
    except Exception:
        raise ReadError('SEARCH_UNAVAILABLE') from None


def auto_probe_account_symbol(search=None):
    """At most one account-supported read-only symbol query per process.

    Only after a successful saved DEGIRO holdings read; zero requests if
    there is no unique account. Rate-limit failures are not retried.
    """
    global _SYMBOL_PROBED
    import degiro_catalog
    if not _SYMBOL_LOCK.acquire(blocking=False):
        return False
    try:
        with _LOCK:
            if (_SYMBOL_PROBED or _CONFIG is None or _STATE.get('code') != 'READ_OK'
                    or not _SYMBOL_ACCOUNT_ID):
                return False
            _SYMBOL_PROBED = True
            aid, config, generation = _SYMBOL_ACCOUNT_ID, dict(_CONFIG), _GENERATION
        target = degiro_catalog.SEEDS[0][0]
        try:
            data = (search or api_search_account_symbol)(aid, config, target)
            result = degiro_research_review.summarize_symbol_search(data, target)
        except ReadError as exc:
            result = dict(code=exc.code, resultCount=None, exactSymbolCandidates=None)
        except ValueError:
            result = dict(code='INVALID_RESPONSE', resultCount=None, exactSymbolCandidates=None)
        with _LOCK:
            if generation == _GENERATION:
                _SYMBOL_STATE.clear()
                _SYMBOL_STATE.update(result, checkedAt=utcnow(),
                    accountTradabilityVerified=False, completeGoldCatalog=False,
                    executableQuoteVerified=False, tradeApproved=False)
        return True
    finally:
        _SYMBOL_LOCK.release()


def rows(data, wrapped=True):
    value = data.get('results') if wrapped and isinstance(data, dict) else data
    if not isinstance(value, list) or len(value) > 1000 or any(not isinstance(x, dict) for x in value):
        raise ReadError('INVALID_RESPONSE')
    return value


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return str(result) if result.is_finite() and abs(result.adjusted()) < 50 and len(str(value)) <= 100 else None
    except (InvalidOperation, ValueError):
        return None


def text(value, length=160):
    return value[:length] if isinstance(value, str) else ''


def source_time(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None or dt.timestamp() > time.time() + 30:
            return None
        return dt.isoformat()
    except (ValueError, OverflowError):
        return None


def normalize_positions(data):
    result = []
    for row in rows(data):
        instrument = row.get('instrument')
        if not isinstance(instrument, dict):
            raise ReadError('INVALID_RESPONSE')
        item = {'symbol': text(instrument.get('symbol')), 'name': text(instrument.get('description')),
                       'kind': text(instrument.get('kind'), 32), 'units': number(row.get('units')),
                       'currency': text(row.get('currency'), 3), 'valuationPrice': number(row.get('price')),
                       'isin': None, 'identityVerified': False, 'tradeApproved': False,
                       'missing': ['isin', 'gold-product-evidence', 'original-bid-ask-time']}
        item['rawSymbol'] = text(instrument.get('raw_symbol'), 80)
        item['stableInstrumentId'] = bool(isinstance(instrument.get('id'), str) and re.fullmatch(ID, instrument['id']))
        item['providerIsin'] = portfolio.isin(instrument.get('raw_symbol')) or portfolio.isin(instrument.get('symbol'))
        result.append(portfolio.enrich_position(row, item, number, text))
    return {'positions': result, 'sourceAt': source_time((data.get('data_freshness') or {}).get('as_of'))}


def read_snapshot(config, get=api_get):
    connections = rows(get('/authorizations', config), wrapped=False)
    relevant = [c for c in connections if isinstance(c.get('brokerage'), dict) and c['brokerage'].get('slug') == 'DEGIRO']
    if not relevant:
        raise ReadError('CONNECT_DEGIRO')
    if len(relevant) > 3:
        raise ReadError('TOO_MANY_ACCOUNTS')
    accounts, limitations, disabled = [], [], False
    seen = set()
    for connection in relevant:
        if connection['brokerage'].get('enabled') is False or connection['brokerage'].get('maintenance_mode') is True:
            raise ReadError('PROVIDER_UNAVAILABLE')
        if connection.get('disabled') is not False:
            disabled = True
            continue
        if connection.get('type') != 'read':
            raise ReadError('READ_CONNECTION_REQUIRED')
        cid = connection.get('id')
        if not isinstance(cid, str) or not re.fullmatch(ID, cid):
            raise ReadError('INVALID_RESPONSE')
        freshness = connection.get('data_freshness_mode') or {}
        mode = 'realtime' if freshness.get('institution') == freshness.get('snaptrade') == 'realtime' else 'delayed-or-unknown'
        for account in rows(get('/connections/' + cid + '/accounts', config)):
            aid = account.get('id')
            if not isinstance(aid, str) or not re.fullmatch(ID, aid) or account.get('connection_id') != cid or aid in seen:
                raise ReadError('INVALID_RESPONSE')
            if account.get('kind') != 'investment':
                continue
            seen.add(aid)
            if len(seen) > 3:
                raise ReadError('TOO_MANY_ACCOUNTS')
            positions = normalize_positions(get('/accounts/' + aid + '/positions/all', config))
            balances = get('/accounts/' + aid + '/balances/v2', config)
            if not isinstance(balances, dict) or balances.get('account_id') != aid:
                raise ReadError('INVALID_RESPONSE')
            cash = [{'currency': text(x.get('currency'), 3), 'amount': number(x.get('amount'))} for x in rows(balances.get('cash'), wrapped=False)]
            net = account.get('net_value') or {}
            net = net if isinstance(net, dict) else {}
            accounts.append({'accountKey': portfolio.identity(aid), 'providerAccountId': aid,
                             'netValue': {'amount': number(net.get('amount')), 'currency': text(net.get('currency'), 3)},
                             'positions': positions['positions'], 'positionsSourceAt': positions['sourceAt'],
                             'cash': cash, 'cashSourceAt': source_time((balances.get('data_freshness') or {}).get('as_of')),
                             'freshnessMode': mode})
    if disabled:
        limitations.append('Eine DEGIRO-Verbindung ist deaktiviert; erneut bei SnapTrade anmelden.')
    if not accounts:
        raise ReadError('AUTH_REQUIRED' if disabled else 'NO_ACCOUNTS')
    return {'observedAt': utcnow(), 'accounts': accounts, 'completeConnections': not disabled,
            'limitations': limitations, 'goldProductCoverage': 'unverified', 'liveQuotes': False,
            'tradeApproved': False, 'realOrders': False}



def summarize_broker_catalog(data):
    """Metadata-only: an instrument catalogue is never a verified Gold KO list."""
    import degiro_catalog
    if not isinstance(data, dict) or not isinstance(data.get('instruments'), list):
        raise ReadError('INVALID_RESPONSE')
    instruments = data['instruments']
    if len(instruments) > 100_000:
        raise ReadError('RESPONSE_TOO_LARGE')
    watched = {isin for isin, _ in degiro_catalog.SEEDS}
    matches = {}
    conflicting = set()
    for instrument in instruments:
        if not isinstance(instrument, dict):
            raise ReadError('INVALID_RESPONSE')
        symbol = instrument.get('symbol')
        if not isinstance(symbol, str) or len(symbol) > 160:
            continue
        candidate = symbol.split('.', 1)[0].upper()
        if candidate not in watched:
            continue
        supported = instrument.get('tradeable')
        value = supported if isinstance(supported, bool) else None
        if candidate in conflicting:
            continue
        if candidate in matches and matches[candidate] != value:
            matches[candidate] = None
            conflicting.add(candidate)
        else:
            matches[candidate] = value
    return {'code': 'CATALOG_EMPTY' if not instruments else 'CATALOG_RETURNED',
            'instrumentCount': len(instruments),
            'historicalWatchCount': len(watched),
            'historicalMatches': [{'isin': isin, 'providerTradeable': matches[isin]}
                                  for isin in sorted(matches)],
            'completeGoldList': False, 'accountTradabilityVerified': False,
            'tradeApproved': False,
            'note': 'Broker-Instrumente sind keine vollständige Gold-KO-Liste, kein Tagesnachweis und kein Originalkurs.'}


def probe_broker_catalog():
    """Explicit, at-most-daily read-only check; never run in the polling loop."""
    global _CATALOG_LAST_ATTEMPT
    if not _CATALOG_LOCK.acquire(blocking=False):
        return status()
    try:
        load_config()
        with _LOCK:
            if not _CONFIG:
                raise ReadError('SETUP_REQUIRED')
            now = time.monotonic()
            since = now - _CATALOG_LAST_ATTEMPT
            if _CATALOG_LAST_ATTEMPT and since < (
                    CATALOG_RECHECK_SECONDS if _CATALOG_STATE.get('code') in
                    ('CATALOG_RETURNED', 'CATALOG_EMPTY') else 3600):
                return status()
            _CATALOG_LAST_ATTEMPT = now
            config, generation = dict(_CONFIG), _GENERATION
        try:
            result = summarize_broker_catalog(api_get('/brokerages/DEGIRO/instruments', config))
        except ReadError as exc:
            result = {'code': exc.code, 'completeGoldList': False,
                      'accountTradabilityVerified': False, 'tradeApproved': False}
        with _LOCK:
            if generation == _GENERATION:
                _CATALOG_STATE.clear()
                _CATALOG_STATE.update(result, checkedAt=utcnow())
        return status()
    finally:
        _CATALOG_LOCK.release()


def load_ledger(config):
    owner = portfolio.identity(config['clientId'])
    if _LEDGER_OWNER == owner:
        return copy.deepcopy(_LEDGER)
    loaded = {}
    sealed = storage('state-read').get('sealed')
    if sealed:
        try:
            raw = zlib.decompressobj().decompress(cipher().decrypt(sealed.encode()), HISTORY_MAX_BYTES + 1)
            if len(raw) > HISTORY_MAX_BYTES: raise ValueError()
            value = json.loads(raw)
            if value.get('owner') == owner: loaded = value
        except Exception:
            raise ReadError('HISTORY_UNREADABLE') from None
    return loaded or {'owner': owner, 'history': [], 'changes': [], 'journal': {}}


def save_ledger():
    raw = json.dumps(_LEDGER, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > HISTORY_MAX_BYTES:
        raise ReadError('HISTORY_FULL')
    sealed = cipher().encrypt(zlib.compress(raw)).decode()
    if len(sealed) > 900_000 or storage('state-save', {'sealed': sealed}).get('saved') is not True:
        raise ReadError('HISTORY_STORE_UNAVAILABLE')


def read_journal(aid, config, previous=None, get=api_get, max_bytes=HISTORY_JOURNAL_BYTES):
    result = copy.deepcopy(previous or {})
    for category in ('orders', 'activities'):
        old = result.get(category) or {}
        # Transactions are daily data; even failures back off for a day.
        due = category == 'orders' or activity_due(old)
        if not due: continue
        try:
            if category == 'orders':
                data = rows(get('/accounts/' + aid + '/orders', config), wrapped=False)
                complete = False  # Endpoint is a recent window, not full order history.
            else:
                data, complete = [], False
                source_total, coverage_reason = None, None
                activity_pages_received = 0
                prior_rows = []
                head_fingerprint = None
                next_offset = 0
                offsets = list(ACTIVITY_OFFSETS)
                for offset in offsets:
                    page = get('/accounts/' + aid + '/activities', config, {'offset': offset, 'limit': 500})
                    if not isinstance(page, dict): raise ReadError('INVALID_RESPONSE')
                    batch = rows(page.get('data'), wrapped=False)
                    if len(batch) > 500: raise ReadError('INVALID_RESPONSE')
                    activity_pages_received += 1
                    pagination = page.get('pagination') or {}
                    if not isinstance(pagination, dict): raise ReadError('INVALID_RESPONSE')
                    total = pagination.get('total')
                    if isinstance(total, int) and not isinstance(total, bool) and 0 <= total <= 10_000_000:
                        if source_total is not None and source_total != total:
                            raise ReadError('INVALID_RESPONSE')
                        source_total = total
                    if offset == 0:
                        head_fingerprint = hashlib.sha256(json.dumps(batch, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                        cursor = old.get('nextOffset')
                        if (old.get('pagingVersion') == HISTORY_PAGING_VERSION
                                and old.get('activityCoverageReason') == 'PAGE_LIMIT'
                                and old.get('headFingerprint') == head_fingerprint
                                and old.get('activitySourceTotal') == source_total
                                and type(cursor) is int and 0 < cursor < HISTORY_MAX_ROWS
                                and cursor % 500 == 0 and not old.get('conflictingActivityIdentifiers')):
                            prior_rows = old.get('rows') or []
                            offsets[1:] = list(range(cursor, min(HISTORY_MAX_ROWS, cursor + (len(ACTIVITY_OFFSETS)-1)*500), 500))
                    data.extend(batch)
                    preview = prior_rows + activity_rows(data)
                    if len(json.dumps(preview).encode())+len(json.dumps(result.get('orders',{})).encode())>max_bytes:
                        if batch: del data[-len(batch):]
                        coverage_reason = 'SIZE_LIMIT'
                        break
                    next_offset = offset + len(batch)
                    if source_total is not None and next_offset >= source_total:
                        complete = True
                        break
                    if len(batch) < 500:
                        if source_total is None:
                            complete = True
                        else:
                            coverage_reason = 'SHORT_PAGE'
                        break
                if not complete and coverage_reason is None:
                    coverage_reason = 'PAGE_LIMIT'
            normalized = prior_rows + activity_rows(data) if category == 'activities' else portfolio.journal_rows(data, category, number, text)
            unique, conflicts = {}, set()
            for row in normalized:
                key = row['key']
                if key in conflicts:
                    continue
                if key in unique and unique[key] != row:
                    # One provider ID with contradictory observations is not
                    # a confirmed event. Keep unrelated records; never choose
                    # a supposedly final fill or activity by guesswork.
                    unique.pop(key, None)
                    conflicts.add(key)
                    continue
                unique[key] = row
            normalized = sorted(unique.values(), key=lambda row: row['date'], reverse=True)
            if category == 'activities' and complete and len(normalized) != (source_total if source_total is not None else next_offset):
                complete = False
                coverage_reason = 'IDENTITY_COUNT_MISMATCH'
            result[category] = dict(rows=normalized, checkedAt=utcnow(), attemptedEpoch=time.time(),
                                    code='READ_OK', complete=complete and not conflicts,
                                    conflictingOrderIdentifiers=len(conflicts) if category == 'orders' else 0,
                                    conflictingActivityIdentifiers=len(conflicts) if category == 'activities' else 0,
                                    activitySourceTotal=source_total if category == 'activities' else None,
                                    activityCoverageReason=coverage_reason if category == 'activities' else None,
                                    activityPagesReceived=activity_pages_received if category == 'activities' else None,
                                    schemaVersion=trades.SCHEMA)
            if category == 'activities':
                result[category].update(pagingVersion=HISTORY_PAGING_VERSION, nextOffset=next_offset, headFingerprint=head_fingerprint)
        except (ReadError, ValueError, TypeError) as exc:
            # Only static categories; never reflect provider errors, credentials or rows.
            allowed = ('AUTH_REQUIRED', 'ACCESS_DENIED', 'RATE_LIMITED', 'PLAN_REQUIRED',
                       'PROVIDER_UNAVAILABLE', 'RESPONSE_TOO_LARGE', 'INVALID_RESPONSE')
            reason = exc.code if isinstance(exc, ReadError) and exc.code in allowed else (
                'INVALID_RESPONSE' if isinstance(exc, (ValueError, TypeError)) else 'PROVIDER_UNAVAILABLE')
            # Keep the last confirmed rows and original checkedAt, but label the
            # failed attempt independently. A subsequent success clears this reason.
            result[category] = dict(old, code='UNAVAILABLE', attemptedEpoch=time.time(),
                                    schemaVersion=trades.SCHEMA, failureCode=reason, failureAt=utcnow())
            if category == 'activities':
                # Provider 429 invalidates neither the previous successful
                # journal nor its original checkedAt. Count only completed
                # pages; the rejected page contains no usable evidence.
                result[category]['activityPagesReceived'] = activity_pages_received
                result[category]['pagingVersion'] = HISTORY_PAGING_VERSION
    return result


def read_trade_coverage(aid, config, previous=None, known_isins=None, get=api_get):
    """One bounded weekly BUY/SELL-only observation, never a FIFO proof.

    It intentionally does not persist individual personal transactions. The
    count is separate from full account activities (fees/transfers/corporate
    actions), and incomplete / duplicate pages do not become 'complete'.
    """
    old = copy.deepcopy(previous or {})
    now = time.time()
    if old.get('schemaVersion') == TRADE_COVERAGE_SCHEMA and now - old.get('attemptedEpoch', 0) < TRADE_COVERAGE_INTERVAL:
        return old
    # Display only checksum-confirmed, currently linked holding ISINs. The
    # complete aggregate match count still considers every confirmed ISIN.
    known_isins = {x for x in (known_isins or ()) if portfolio.isin(x)}
    tracked_isins = sorted(known_isins)[:25]
    by_holding = {isin: {'isin':isin, 'buys':0, 'sells':0,
                         'firstDay':None, 'lastDay':None} for isin in tracked_isins}
    observed_ids, conflicting_ids = {}, set()
    observed_total, page_count = None, 0
    buy_count, sell_count = 0, 0
    matched_count, verified_count = 0, 0
    distinct_isins = set()
    first_day, last_day = None, None
    complete, coverage_reason = False, None
    try:
        for offset in TRADE_COVERAGE_OFFSETS:
            page = get('/accounts/' + aid + '/activities', config,
                       {'offset': offset, 'limit': 1000, 'type': 'BUY,SELL'})
            if not isinstance(page, dict):
                raise ReadError('INVALID_RESPONSE')
            batch = rows(page.get('data'), wrapped=False)
            page_count += 1
            pagination = page.get('pagination') or {}
            if not isinstance(pagination, dict):
                raise ReadError('INVALID_RESPONSE')
            total = pagination.get('total')
            if (isinstance(total, bool) or not isinstance(total, int)
                    or not 0 <= total <= 10_000_000):
                raise ReadError('INVALID_RESPONSE')
            if observed_total is not None and total != observed_total:
                raise ReadError('INVALID_RESPONSE')
            observed_total = total
            for raw in batch:
                if raw.get('type') not in ('BUY', 'SELL'):
                    raise ReadError('INVALID_RESPONSE')
                # Build only the existing normalized view, never expose provider
                # raw IDs. Invalid or conflicting records block completeness.
                row = portfolio.journal_rows([raw], 'activities', number, text)[0]
                k = row['key']
                if k in conflicting_ids:
                    continue
                if k in observed_ids and observed_ids[k] != row:
                    observed_ids.pop(k, None)
                    conflicting_ids.add(k)
                else:
                    observed_ids[k] = row
            if offset + len(batch) >= total:
                complete = True
                break
            if len(batch) < 1000:
                coverage_reason = 'SHORT_PAGE'
                break
        if not complete and coverage_reason is None:
            coverage_reason = 'PAGE_LIMIT'
        for row in observed_ids.values():
            if row['type'] == 'BUY':
                buy_count += 1
            elif row['type'] == 'SELL':
                sell_count += 1
            valid_isin = row.get('isin')
            if valid_isin:
                verified_count += 1
                distinct_isins.add(valid_isin)
                if valid_isin in known_isins:
                    matched_count += 1
            date = row.get('date')
            valid_day = date if isinstance(date, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) else None
            if valid_day:
                first_day = min(first_day, valid_day) if first_day else valid_day
                last_day = max(last_day, valid_day) if last_day else valid_day
            if valid_isin in by_holding:
                item = by_holding[valid_isin]
                item['buys' if row['type'] == 'BUY' else 'sells'] += 1
                if valid_day:
                    item['firstDay'] = min(item['firstDay'], valid_day) if item['firstDay'] else valid_day
                    item['lastDay'] = max(item['lastDay'], valid_day) if item['lastDay'] else valid_day
        if conflicting_ids:
            complete = False
            coverage_reason = 'CONFLICTING_IDS'
        # This optional, fully bounded summary uses rows already fetched by
        # the existing weekly coverage calculation. Never persist raw filtered
        # trades, fees, order IDs or amounts, and never make extra API calls.
        candidate_summary = gold_history.discover([{'journal': {'activities': {
            'rows': list(observed_ids.values()), 'complete': complete,
            'code': 'READ_OK'}}}])
        gold_hints = {'items': candidate_summary.get('items', []),
                      'candidateCount': candidate_summary.get('candidateCount', 0),
                      'scope': 'historical-filtered-buy-sell-not-full-account',
                      'completeFilteredTradeWindow': complete}
        return {'code':'READ_OK', 'schemaVersion':TRADE_COVERAGE_SCHEMA,
                'checkedAt':utcnow(), 'attemptedEpoch':now, 'filter':'BUY,SELL',
                'totalMatching':observed_total, 'observed':len(observed_ids),
                'buyCount':buy_count, 'sellCount':sell_count,
                'validIsinCount':verified_count, 'distinctIsins':len(distinct_isins),
                'currentHoldingsIsinMatches':matched_count,
                'missingOrInvalidIsinCount':len(observed_ids)-verified_count,
                'holdingBreakdown':list(by_holding.values()),
                'holdingBreakdownTruncated':len(known_isins)>len(tracked_isins),
                'earliestTradeDay':first_day, 'latestTradeDay':last_day,
                'pagesReceived':page_count, 'conflictingIdentifiers':len(conflicting_ids),
                'completeFilteredTradeWindow':complete, 'coverageReason':coverage_reason,
                'goldHistoryHints':gold_hints,
                'accountHistoryComplete':False, 'fifoEligible':False}
    except Exception as exc:
        # An isolated optional history-filter parser failure must not bring
        # down the already confirmed holdings reader or reveal private rows.
        allowed = ('AUTH_REQUIRED','ACCESS_DENIED','RATE_LIMITED','PLAN_REQUIRED',
                   'PROVIDER_UNAVAILABLE','RESPONSE_TOO_LARGE','INVALID_RESPONSE')
        reason = exc.code if isinstance(exc, ReadError) and exc.code in allowed else (
            'INVALID_RESPONSE' if isinstance(exc,(ValueError,TypeError)) else 'PROVIDER_UNAVAILABLE')
        # Preserve confirmed summary and time, but make the new failure explicit.
        return {**old, 'code':'UNAVAILABLE', 'schemaVersion':TRADE_COVERAGE_SCHEMA,
                'attemptedEpoch':now, 'failureAt':utcnow(), 'failureCode':reason,
                'pagesReceivedInFailedAttempt':page_count,
                'accountHistoryComplete':False, 'fifoEligible':False}


def update_portfolio(snapshot, config, generation):
    global _LEDGER_OWNER
    ledger = load_ledger(config)
    for a in snapshot['accounts']:
        entry=ledger.get('csv',{}).get(a['accountKey'])
        if entry and entry.get('automatic'):
            ledger['csv'][a['accountKey']]=identity.reconcile(entry,a,entry)
    csv_link.apply(snapshot, ledger.get('csv', {}))
    snapshot['changes'] = portfolio.record(ledger['history'], snapshot)
    ledger['changes'] = (ledger['changes'] + snapshot['changes'])[-300:]
    for a in snapshot['accounts']:
        aid = a.pop('providerAccountId')
        key = a['accountKey']
        prior_journal = ledger['journal'].get(key) or {}
        prior_activities = prior_journal.get('activities') or {}
        # One mode per provider cycle: up to five standard history pages OR
        # three filtered trade pages. Never stack both bursts in one request.
        standard_due = activity_due(prior_activities)
        journal = read_journal(aid, config, prior_journal, api_get, HISTORY_JOURNAL_BYTES//len(snapshot['accounts']))
        trade_due = (time.time() - (journal.get('tradeCoverage') or {}).get('attemptedEpoch', 0)
                     >= TRADE_COVERAGE_INTERVAL
                     or (journal.get('tradeCoverage') or {}).get('schemaVersion') != TRADE_COVERAGE_SCHEMA)
        if (not standard_due and trade_due and journal['activities']['code'] == 'READ_OK'
                and journal['orders']['code'] == 'READ_OK'):
            known_isins = {p['isin'] for p in a['positions']
                           if p.get('csvEvidence') and p.get('isin')}
            journal['tradeCoverage'] = read_trade_coverage(
                aid, config, journal.get('tradeCoverage'), known_isins=known_isins)
        ledger['journal'][key] = journal
        a['journal'] = journal
        a['tradeJournal'] = trades.build(journal)
        a['tradeInsights'] = insights.read_account(a)
        a['evidenceQuality'] = quality.evidence_gaps(a)
        a['profitReadiness'] = quality.profit_review(a)
    # Reuse cached, already normalized activity rows (no additional broker API
    # requests). These are research hints only, never current DEGIRO listing
    # evidence, Top-3 entries, or permissions for orders.
    snapshot['historicalGoldResearch'] = gold_history.discover(snapshot['accounts'])
    # Keep the encrypted total bounded without dropping transaction evidence.
    # Snapshot history already has bounded retention; shorten it first when
    # the expanded journal needs more of the existing four-megabyte budget.
    while len(ledger['history'])>1 and len(json.dumps(ledger,separators=(',',':')).encode())>HISTORY_MAX_BYTES-100_000:
        del ledger['history'][:max(1,len(ledger['history'])//4)]
    snapshot['changes'] = ledger['changes']
    snapshot['history'] = [{'at': p['at'], 'complete':p['complete'], 'accounts':[
        {'accountKey':a['accountKey'], 'netValue':a['netValue']} for a in p['accounts']]} for p in ledger['history']]
    with _LOCK:
        if generation != _GENERATION: return
        _LEDGER.clear(); _LEDGER.update(ledger)
        _LEDGER_OWNER = ledger['owner']
        try:
            save_ledger()
            snapshot['historyPersistence'] = 'SAVED'
        except ReadError:
            snapshot['historyPersistence'] = 'UNAVAILABLE'


def import_csv(payload, clear=False, automatic=False):
    # This explicit app action shares normalized export rows with the encrypted
    # store. Existing local CSVs are never uploaded by polling or app startup.
    with _LOCK:
        if not _CONFIG or _STATE.get('code') != 'READ_OK' or not _STATE.get('snapshot'):
            raise ReadError('CSV_CONNECTION_REQUIRED')
        generation, config = _GENERATION, dict(_CONFIG)
        snapshot = copy.deepcopy(_STATE['snapshot'])
    if clear:
        if not isinstance(payload,dict) or set(payload) != {'accountKey'} or not any(a['accountKey']==payload['accountKey'] for a in snapshot['accounts']):
            raise ValueError('Invalid CSV account')
        entry = None
    else:
        if automatic and (not isinstance(payload,dict) or payload.get('links')!=[]):
            raise ValueError('Automatic links must be proven by the server')
        entry = csv_link.prepare(payload, snapshot, number, text, source_time, allow_empty=automatic)
    ledger = load_ledger(config)
    ledger.setdefault('csv', {})
    if clear: ledger['csv'].pop(payload['accountKey'],None)
    else:
        if automatic:
            account=next(a for a in snapshot['accounts'] if a['accountKey']==payload['accountKey'])
            entry=identity.reconcile(entry,account,ledger['csv'].get(payload['accountKey']))
        ledger['csv'][payload['accountKey']] = entry
    csv_link.apply(snapshot, ledger['csv'])
    for account in snapshot['accounts']:
        account['tradeInsights'] = insights.read_account(account)
    with _LOCK:
        if generation != _GENERATION:
            raise ReadError('CSV_CONNECTION_REQUIRED')
        # A refresh may have replaced holdings while the store was being read.
        if _STATE['snapshot']['observedAt'] != snapshot['observedAt']:
            raise ReadError('CSV_RETRY_REQUIRED')
        previous = copy.deepcopy(_LEDGER)
        _LEDGER.clear(); _LEDGER.update(ledger)
        try:
            save_ledger()
        except ReadError:
            _LEDGER.clear(); _LEDGER.update(previous)
            raise
        _STATE['snapshot'] = snapshot
    return status()


def quote_tick(fetch=None):
    """Existing issuer readers, exact ISIN and currency only. No broker quotes."""
    global _QUOTE_CURSOR
    if fetch is None:
        from product_quotes import get_quote
        fetch = get_quote
    with _LOCK:
        generation = _GENERATION
        snap = copy.deepcopy(_STATE.get('snapshot'))
    if not snap: return
    candidates = []
    seen = set()
    for a in snap['accounts']:
        for p in a['positions']:
            if p.get('isin') and p['isin'] not in seen:
                candidates.append(p); seen.add(p['isin'])
    if not candidates: return
    start = _QUOTE_CURSOR % len(candidates)
    selected = (candidates[start:] + candidates[:start])[:3]
    _QUOTE_CURSOR = (start + len(selected)) % len(candidates)
    quotes, attempted = {}, set()
    for p in selected:
        candidate = p.get('isin')
        if not candidate or candidate in attempted or len(attempted) >= 3: continue
        attempted.add(candidate)
        try:
            q = fetch(candidate)
            meta = q.get('metadata') or {}
            # Only original, verified issuer bid/ask. Never an estimated analysisQuote.
            currency = q.get('currency') or meta.get('currency')
            bid, ask = number(q.get('bid')), number(q.get('ask'))
            at, ask_at = source_time(q.get('bidAt')), source_time(q.get('askAt'))
            valid = (q.get('isin') == candidate and q.get('productVerified') is True
                     and q.get('fresh') is True and q.get('found') is True
                     and not q.get('sourceFailure') and q.get('dataOrigin') != 'calculated'
                     and q.get('priceKind') not in ('calculated', 'calculated-turbo', 'estimated')
                     and not q.get('currencyConversion') and currency == p['currency']
                     and bid is not None and ask is not None and at and ask_at
                     and 0 < Decimal(bid) <= Decimal(ask)
                     and all(0 <= time.time()-datetime.fromisoformat(t).timestamp() <= 90 for t in (at, ask_at)))
            if valid: quotes[candidate] = dict(bid=bid, ask=ask, bidAt=at, askAt=ask_at,
                                               currency=currency, source=text(q.get('source')))
        except Exception:
            continue
    with _LOCK:
        if generation != _GENERATION or not _STATE.get('snapshot'): return
        for a in _STATE['snapshot']['accounts']:
            for p in a['positions']:
                if p.get('isin') in attempted:
                    p['issuerQuote'] = quotes.get(p.get('isin'))


def observation_tick(observe=None):
    """Bounded parallel issuer observations; no account calls or approvals."""
    observe = observe or holding_quotes.get_observation
    with _LOCK:
        generation = _GENERATION
        snapshot = copy.deepcopy(_STATE.get('snapshot'))
    if not snapshot:
        return
    candidates = {}
    for a in snapshot['accounts']:
        for p in a['positions']:
            if p.get('isin'):
                candidates.setdefault((p['isin'],p['currency']),p)
    # Up to three accounts; only a bounded rotating group of known holdings.
    keys = sorted(candidates)
    start = int(time.monotonic()//30)*10 % len(keys) if keys else 0
    keys = (keys[start:]+keys[:start])[:10]
    def read(key):
        try:
            value = observe(candidates[key])
            if value.get('isin') != key[0] or value.get('currency') != key[1]:
                raise ValueError()
            return key, holding_quotes.freshness(value)
        except Exception:
            return key, dict(isin=key[0],currency=key[1],code='SOURCE_UNAVAILABLE',current=False,
                             identityVerified=False,observedAt=utcnow())
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix='bob-holding-quote') as pool:
        observations = dict(pool.map(read,keys))
    with _LOCK:
        if generation != _GENERATION or not _STATE.get('snapshot'):
            return
        for a in _STATE['snapshot']['accounts']:
            for p in a['positions']:
                q = observations.get((p.get('isin'),p.get('currency')))
                if q is not None:
                    p['issuerObservation'] = q


def _quote_loop():
    while True:
        began = time.monotonic()
        try: observation_tick()
        except Exception: pass
        time.sleep(max(1, 30 - (time.monotonic() - began)))


def mark_interactive():
    """Read-only provider refresh; no faster than every 10 minutes in active UI."""
    global _NEXT, _INTERACTIVE_UNTIL
    with _LOCK:
        now = time.monotonic()
        _INTERACTIVE_UNTIL = now + 120
        if _CONFIG:
            _NEXT = min(_NEXT, max(now, _LAST_ATTEMPT + INTERVAL))
    _WAKE.set()


def refresh():
    global _NEXT, _LAST_ATTEMPT, _SYMBOL_ACCOUNT_ID
    if not _FETCH_LOCK.acquire(blocking=False):
        return status()
    try:
        load_config()
        with _LOCK:
            if not _CONFIG:
                return status()
            if time.monotonic() < _NEXT:
                return status()
            config, generation = dict(_CONFIG), _GENERATION
            now = time.monotonic()
            _LAST_ATTEMPT = now
            _NEXT = now + (INTERVAL if now < _INTERACTIVE_UNTIL else BACKGROUND_INTERVAL)
            _STATE['code'] = 'CHECKING'
        try:
            snapshot = read_snapshot(config)
            # Capture only one internally verified provider account identifier
            # before the normalizer deletes it. Never place it in a status or log.
            account_ids = [a.get('providerAccountId') for a in snapshot.get('accounts', [])]
            symbol_account = (account_ids[0] if len(account_ids) == 1
                              and isinstance(account_ids[0], str)
                              and re.fullmatch(ID, account_ids[0]) else None)
            try:
                update_portfolio(snapshot, config, generation)
            except ReadError:
                snapshot['historyPersistence'] = 'UNAVAILABLE'
            with _LOCK:
                if generation == _GENERATION:
                    previous = {(a['accountKey'],p['positionKey']):p for a in (_STATE.get('snapshot') or {}).get('accounts',[]) for p in a['positions']}
                    for a in snapshot['accounts']:
                        for p in a['positions']:
                            old=previous.get((a['accountKey'],p['positionKey']))
                            if old and old.get('isin')==p.get('isin') and old['currency']==p['currency'] and old.get('issuerObservation'):
                                p['issuerObservation']=copy.deepcopy(old['issuerObservation'])
                    for a in snapshot['accounts']: a.pop('providerAccountId', None)
                    if snapshot.get('historyPersistence') == 'SAVED' and len(snapshot['accounts']) == 1:
                        history = snapshot['accounts'][0].get('journal', {}).get('activities', {})
                        if history.get('code') == 'READ_OK' and history.get('activityCoverageReason') == 'PAGE_LIMIT' and type(history.get('nextOffset')) is int and history['nextOffset'] < HISTORY_MAX_ROWS:
                            _NEXT = min(_NEXT, time.monotonic() + INTERVAL)
                    _STATE.update(code='READ_OK', snapshot=snapshot, checkedAt=utcnow())
                    _SYMBOL_ACCOUNT_ID = symbol_account
        except ReadError as exc:
            with _LOCK:
                if generation == _GENERATION:
                    _NEXT = max(_NEXT, time.monotonic() + exc.retry_after)
                    _STATE.update(code=exc.code, checkedAt=utcnow())
    except ReadError as exc:
        with _LOCK:
            _STATE['code'] = exc.code
    except Exception:
        with _LOCK:
            _STATE['code'] = 'INVALID_RESPONSE'
    finally:
        _FETCH_LOCK.release()
    return status()


def status():
    with _LOCK:
        result = copy.deepcopy(_STATE)
        result.update(configured=bool(_CONFIG), running=bool(_THREAD and _THREAD.is_alive()),
                      intervalSeconds=INTERVAL if time.monotonic() < _INTERACTIVE_UNTIL else BACKGROUND_INTERVAL,
                      nextCheckSeconds=max(0, math.ceil(_NEXT - time.monotonic())),
                      interactive=time.monotonic() < _INTERACTIVE_UNTIL,
                      readOnly=True, realOrders=False, liveQuotes=False,
                      provider='SnapTrade Personal', coverageVerified=False,
                      catalogProbe=copy.deepcopy(_CATALOG_STATE),
                      accountSymbolProbe=copy.deepcopy(_SYMBOL_STATE))
        # A successful HTTP request alone does not prove current provider data.
        snapshot = result.get('snapshot')
        for a in (snapshot or {}).get('accounts', []):
            for p in a['positions']:
                observation = p.get('issuerObservation')
                if observation:
                    p['issuerObservation'] = observation = holding_quotes.freshness(observation)
                    p['observedPositionValue'] = p['observedUnrealizedPnl'] = None
                    if observation.get('current') and p.get('marketValue') is not None and p.get('units') is not None:
                        units, bid = Decimal(p['units']),Decimal(observation['bid'])
                        if units>=0:
                            p['observedPositionValue']=str(units*bid)
                            if p.get('costBasis') is not None:
                                p['observedUnrealizedPnl']=str(units*(bid-Decimal(p['costBasis'])))
                q = p.get('issuerQuote')
                if q and any(not source_time(q.get(k)) or time.time()-datetime.fromisoformat(q[k]).timestamp()>90 for k in ('bidAt','askAt')):
                    p['issuerQuote'] = None
        result['fresh'] = bool(result['code'] == 'READ_OK' and snapshot and snapshot['completeConnections'] and all(
            a['freshnessMode'] == 'realtime' and all(t and 0 <= time.time() - datetime.fromisoformat(t).timestamp() <= INTERVAL + 90
                for t in (a['positionsSourceAt'], a['cashSourceAt'])) for a in snapshot['accounts']))
        result['connectionWatch'] = quality.connection_watch(result)
        return result


def historical_gold_candidates():
    """A separate limited, private research view, not the active product list."""
    with _LOCK:
        snap = _STATE.get('snapshot')
        result = copy.deepcopy((snap or {}).get('historicalGoldResearch'))
    if not isinstance(result, dict):
        return {'code':'NO_HISTORY', 'items':[], 'candidateCount':0,
                'completeDegiroCatalog':False, 'tradeApproved':False}
    return result


def diagnostics():
    value = status()
    try:
        cipher()
        encryption_ready = True
    except ReadError:
        encryption_ready = False
    return {key: value[key] for key in ('code', 'configured', 'running', 'fresh', 'intervalSeconds', 'readOnly', 'realOrders', 'liveQuotes', 'coverageVerified')} | {
        'checkedAt': value.get('checkedAt'), 'encryptionReady': encryption_ready,
        'connectionWatch': value.get('connectionWatch'),
        'evidenceGaps': [{k: a.get('evidenceQuality',{}).get(k) for k in (
            'orderRows','positiveFills','noPositiveFill','filledQuantityMissing',
            'filledQuantityZero','filledQuantityInvalid','missingExecutionTime',
            'missingVerifiedIsin','missingPrice','activityTrades','activityMissingFees')}
            for a in (value.get('snapshot') or {}).get('accounts',[])],
        'profitReadiness': [{k: a.get('profitReadiness',{}).get(k) for k in (
            'accountHistoryComplete','activityReadable','tradeRows','fifoVerifiedSales',
            'unresolvedLots','strictReviewPairs','unmatchedOrUnverifiedEvidence',
            'netProfitVerified','taxProfitVerified','canChangeTradeRules','readOnly')}
            for a in (value.get('snapshot') or {}).get('accounts',[])],
        'accountsReceived': len((value.get('snapshot') or {}).get('accounts', [])),
        'positionsReceived': sum(len(a['positions']) for a in (value.get('snapshot') or {}).get('accounts', [])),
        'portfolioVersion': 5,
        'issuerObservationsCurrent': sum(bool(p.get('issuerObservation',{}).get('current')) for a in (value.get('snapshot') or {}).get('accounts',[]) for p in a['positions']),
        'issuerObservationStates': [p.get('issuerObservation',{}).get('code','NOT_READ') for a in (value.get('snapshot') or {}).get('accounts',[]) for p in a['positions']],
        'documentedExecutions': sum(len(a.get('tradeJournal',{}).get('events',[])) for a in (value.get('snapshot') or {}).get('accounts',[])),
        'calculatedSales': sum(len(a.get('tradeJournal',{}).get('realized',[])) for a in (value.get('snapshot') or {}).get('accounts',[])),
        'unresolvedTradeCalculations': sum(len(a.get('tradeJournal',{}).get('unresolved',[])) for a in (value.get('snapshot') or {}).get('accounts',[])),
        'tradeCalculationReasons': dict(Counter(r['reason'] for a in (value.get('snapshot') or {}).get('accounts',[]) for r in a.get('tradeJournal',{}).get('unresolved',[]))),
        'acquisitionPricesReceived': sum(p.get('costBasis') is not None for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'positionValuesCalculated': sum(p.get('marketValue') is not None for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'issuerQuoteCandidates': sum(bool(p.get('isin')) for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'issuerQuotesMatched': sum(bool(p.get('issuerQuote')) for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'historyPersistence': (value.get('snapshot') or {}).get('historyPersistence'),
        'figisReceived': sum(bool(identity.FIGI.fullmatch(p.get('figi') or '')) for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'explicitWknReceived': sum((p.get('rawSymbol') or '').upper().startswith('WKN:') for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'csvLinkedPositions': sum(bool(p.get('csvEvidence')) for a in (value.get('snapshot') or {}).get('accounts', []) for p in a['positions']),
        'historyPoints': len((value.get('snapshot') or {}).get('history', [])),
        'detectedExecutions': sum(a.get('tradeInsights', {}).get('executionsCount', 0) for a in (value.get('snapshot') or {}).get('accounts', [])),
        'executionCandidatesForReview': sum(a.get('tradeInsights', {}).get('readyForHistoricalComparison', 0) for a in (value.get('snapshot') or {}).get('accounts', [])),
        # Strictly bounded counters from the existing, authenticated history.
        # No account IDs, ISINs, symbols, amounts, individual fees or trade rows.
        'executionReconciliation': [{
            'status': a.get('tradeInsights', {}).get('reconciliation', {}).get('status', 'not-observed'),
            'candidatePairs': a.get('tradeInsights', {}).get('reconciliation', {}).get('candidatePairs', 0),
            'ambiguousGroups': a.get('tradeInsights', {}).get('reconciliation', {}).get('ambiguousGroups', 0),
            'unmatchedOrderFills': a.get('tradeInsights', {}).get('reconciliation', {}).get('orderFillsWithoutExactActivity', 0),
            'unmatchedActivityTrades': a.get('tradeInsights', {}).get('reconciliation', {}).get('activityTradesWithoutExactOrder', 0),
            'missingOrderEvidence': a.get('tradeInsights', {}).get('reconciliation', {}).get('missingEvidence', 0),
            'accountHistoryComplete': a.get('tradeInsights', {}).get('reconciliation', {}).get('accountHistoryComplete', False),
            'netProfitVerified': False, 'learningEligible': False, 'readOnly': True,
        } for a in (value.get('snapshot') or {}).get('accounts', [])],
        'journalStatus': [{k: a.get('journal', {}).get(k, {}).get('code', 'NOT_READ') for k in ('orders', 'activities')} for a in (value.get('snapshot') or {}).get('accounts', [])],
        'journalFailureCodes': [{k: a.get('journal', {}).get(k, {}).get('failureCode') for k in ('orders', 'activities')}
                                for a in (value.get('snapshot') or {}).get('accounts', [])],
        'journalConflictingOrderIdentifiers': [a.get('journal', {}).get('orders', {}).get('conflictingOrderIdentifiers', 0)
                                               for a in (value.get('snapshot') or {}).get('accounts', [])],
        'filteredTradeCoverage': [
            {k: (a.get('journal', {}).get('tradeCoverage') or {}).get(k)
             for k in ('code','totalMatching','observed','completeFilteredTradeWindow',
                       'coverageReason','pagesReceived','validIsinCount','distinctIsins',
                       'currentHoldingsIsinMatches','failureCode','checkedAt')}
            for a in (value.get('snapshot') or {}).get('accounts', [])],
        'journalActivityCoverage': [{
            'savedRows': len(a.get('journal', {}).get('activities', {}).get('rows', [])),
            'sourceTotal': a.get('journal', {}).get('activities', {}).get('activitySourceTotal'),
            'reason': a.get('journal', {}).get('activities', {}).get('activityCoverageReason'),
            'pagesReceived': a.get('journal', {}).get('activities', {}).get('activityPagesReceived'),
            'conflictingIds': a.get('journal', {}).get('activities', {}).get('conflictingActivityIdentifiers', 0),
            'complete': a.get('journal', {}).get('activities', {}).get('complete') is True,
        } for a in (value.get('snapshot') or {}).get('accounts', [])],
        'issuerMonitorRunning': bool(_QUOTE_THREAD and _QUOTE_THREAD.is_alive()),
        'historicGoldResearch': {
            'code': (value.get('snapshot') or {}).get('historicalGoldResearch', {}).get('code', 'NO_HISTORY'),
            'candidateCount': (value.get('snapshot') or {}).get('historicalGoldResearch', {}).get('candidateCount', 0),
            'historyComplete': (value.get('snapshot') or {}).get('historicalGoldResearch', {}).get('historyComplete', False),
            'excludedFromTop3': True, 'automaticOrders': False},
        # Small, credential-free result for the private read-only ChatGPT diagnostic.
        'catalogProbe': {k: (value.get('catalogProbe') or {}).get(k)
                         for k in ('code', 'checkedAt', 'instrumentCount',
                                   'historicalWatchCount')},
        'catalogHistoricalMatchCount': len((value.get('catalogProbe') or {}).get('historicalMatches') or []),
        'accountSymbolProbe': {k: (value.get('accountSymbolProbe') or {}).get(k)
                               for k in ('code','checkedAt','resultCount',
                                         'exactSymbolCandidates','tradeApproved')},
        'catalogFullGoldListVerified': False,
        'catalogTradeApproved': False}


def auto_probe_catalog():
    """Run one safe broker-catalogue check after a confirmed DEGIRO holdings read.

    A successful broker connection is already configured in Bob. No mobile
    button, additional login, order, or repeated SnapTrade holdings call.
    Only one automatic catalogue attempt per process; manual retry remains
    subject to the catalogue probe's own cooldown.
    """
    with _LOCK:
        ready = (_CONFIG is not None and _STATE.get('code') == 'READ_OK'
                 and _CATALOG_STATE.get('code') == 'NOT_TESTED')
    if not ready:
        return False
    try:
        probe_broker_catalog()
    except ReadError as exc:
        with _LOCK:
            if _CATALOG_STATE.get('code') == 'NOT_TESTED':
                _CATALOG_STATE.update(code=exc.code, checkedAt=utcnow(),
                                      completeGoldList=False, tradeApproved=False)
    with _LOCK:
        summary = {k: _CATALOG_STATE.get(k) for k in
                   ('code', 'instrumentCount', 'historicalMatches')}
    code = summary.get('code') or 'UNKNOWN'
    count = summary.get('instrumentCount')
    matches = len(summary.get('historicalMatches') or [])
    # No symbols, account numbers, tokens, prices, or full provider payload.
    print('BOB_SNAPTRADE_CATALOG auto=true code=' + str(code)
          + ' instruments=' + str(count if isinstance(count, int) else 'unknown')
          + ' historicalMatches=' + str(matches), flush=True)
    return True


def _loop():
    while True:
        refresh()
        auto_probe_catalog()
        auto_probe_account_symbol()
        _WAKE.wait(60)
        _WAKE.clear()


def start():
    global _THREAD, _QUOTE_THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _THREAD = threading.Thread(target=_loop, name='bob-snaptrade-personal', daemon=True)
            _THREAD.start()
        if _QUOTE_THREAD is None or not _QUOTE_THREAD.is_alive():
            _QUOTE_THREAD = threading.Thread(target=_quote_loop, name='bob-holdings-issuer', daemon=True)
            _QUOTE_THREAD.start()


def handle(action, payload):
    if action in ('csv-import','csv-clear','csv-auto'):
        if not _FETCH_LOCK.acquire(blocking=False):
            raise ReadError('CSV_RETRY_REQUIRED')
        try: return import_csv(payload, clear=action=='csv-clear', automatic=action=='csv-auto')
        finally: _FETCH_LOCK.release()
    if action == 'configure':
        return configure(payload)
    if not isinstance(payload, dict) or payload:
        raise ValueError('Ungültige Anfrage.')
    if action == 'disconnect':
        return disconnect()
    if action == 'catalog-probe':
        return probe_broker_catalog()
    if action == 'check':
        start()
        mark_interactive()
        _WAKE.set()
        return status()
    raise ValueError('Unbekannte Aktion.')
