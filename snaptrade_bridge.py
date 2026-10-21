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
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ORIGIN = 'https://api.snaptrade.com'
INTERVAL = 600
MAX_BODY = 2_000_000
_LOCK = threading.RLock()
_FETCH_LOCK = threading.Lock()
_CONFIG = None
_GENERATION = 0
_LOADED = False
_THREAD = None
_WAKE = threading.Event()
_NEXT = 0.0
_STATE = {'code': 'SETUP_REQUIRED', 'snapshot': None}
ID = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'


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
            body = response.read(10001)
        if len(body) > 10000:
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
    global _CONFIG, _LOADED, _GENERATION, _NEXT
    config = validate_config(payload)
    sealed = cipher().encrypt(json.dumps(config).encode()).decode()
    with _LOCK:
        if storage('save', {'sealed': sealed}).get('saved') is not True:
            raise ReadError('STORE_UNAVAILABLE')
        _CONFIG, _LOADED = config, True
        _GENERATION += 1
        _NEXT = 0
        _STATE.clear()
        _STATE.update(code='READY', snapshot=None)
    start()
    _WAKE.set()
    return status()


def disconnect():
    global _CONFIG, _LOADED, _GENERATION, _NEXT
    with _LOCK:
        if storage('delete').get('deleted') is not True:
            raise ReadError('STORE_UNAVAILABLE')
        _CONFIG, _LOADED = None, True
        _GENERATION += 1
        _NEXT = 0
        _STATE.clear()
        _STATE.update(code='SETUP_REQUIRED', snapshot=None)
    return status()


def permitted(path):
    return path == '/authorizations' or any(re.fullmatch(pattern, path) for pattern in (
        rf'/connections/{ID}/accounts', rf'/accounts/{ID}/positions/all', rf'/accounts/{ID}/balances/v2'))


def api_get(path, config):
    if not permitted(path):
        raise ReadError('PATH_REJECTED')
    query = urlencode({'clientId': config['clientId'], 'timestamp': int(time.time())})
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
        return str(result) if result.is_finite() else None
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
        result.append({'symbol': text(instrument.get('symbol')), 'name': text(instrument.get('description')),
                       'kind': text(instrument.get('kind'), 32), 'units': number(row.get('units')),
                       'currency': text(row.get('currency'), 3), 'valuationPrice': number(row.get('price')),
                       'isin': None, 'identityVerified': False, 'tradeApproved': False,
                       'missing': ['isin', 'gold-product-evidence', 'original-bid-ask-time']})
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
            accounts.append({'positions': positions['positions'], 'positionsSourceAt': positions['sourceAt'],
                             'cash': cash, 'cashSourceAt': source_time((balances.get('data_freshness') or {}).get('as_of')),
                             'freshnessMode': mode})
    if disabled:
        limitations.append('Eine DEGIRO-Verbindung ist deaktiviert; erneut bei SnapTrade anmelden.')
    if not accounts:
        raise ReadError('AUTH_REQUIRED' if disabled else 'NO_ACCOUNTS')
    return {'observedAt': utcnow(), 'accounts': accounts, 'completeConnections': not disabled,
            'limitations': limitations, 'goldProductCoverage': 'unverified', 'liveQuotes': False,
            'tradeApproved': False, 'realOrders': False}


def refresh():
    global _NEXT
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
            _NEXT = time.monotonic() + INTERVAL
            _STATE['code'] = 'CHECKING'
        try:
            snapshot = read_snapshot(config)
            with _LOCK:
                if generation == _GENERATION:
                    _STATE.update(code='READ_OK', snapshot=snapshot, checkedAt=utcnow())
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
                      intervalSeconds=INTERVAL, nextCheckSeconds=max(0, math.ceil(_NEXT - time.monotonic())),
                      readOnly=True, realOrders=False, liveQuotes=False,
                      provider='SnapTrade Personal', coverageVerified=False)
        # A successful HTTP request alone does not prove current provider data.
        snapshot = result.get('snapshot')
        result['fresh'] = bool(result['code'] == 'READ_OK' and snapshot and snapshot['completeConnections'] and all(
            a['freshnessMode'] == 'realtime' and all(t and 0 <= time.time() - datetime.fromisoformat(t).timestamp() <= INTERVAL + 90
                for t in (a['positionsSourceAt'], a['cashSourceAt'])) for a in snapshot['accounts']))
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
        'accountsReceived': len((value.get('snapshot') or {}).get('accounts', [])),
        'positionsReceived': sum(len(a['positions']) for a in (value.get('snapshot') or {}).get('accounts', []))}


def _loop():
    while True:
        refresh()
        _WAKE.wait(60)
        _WAKE.clear()


def start():
    global _THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _THREAD = threading.Thread(target=_loop, name='bob-snaptrade-personal', daemon=True)
            _THREAD.start()


def handle(action, payload):
    if action == 'configure':
        return configure(payload)
    if not isinstance(payload, dict) or payload:
        raise ValueError('Ungültige Anfrage.')
    if action == 'disconnect':
        return disconnect()
    if action == 'check':
        start()
        _WAKE.set()
        return status()
    raise ValueError('Unbekannte Aktion.')
