"""Isolated SDK worker: fixed login/read/logout allowlist; no order endpoint."""
from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
from urllib.parse import urlsplit


def login_diagnostic(response):
    """Fixed reason codes only: never return response text, tokens or headers."""
    if response.status_code == 429:
        return 'RATE_LIMITED'
    if response.status_code in (403, 451):
        return 'ACCESS_DENIED'
    if response.status_code in (405, 502, 503):
        return 'SERVICE_UNAVAILABLE'
    try:
        data = response.json()
    except (ValueError, TypeError):
        return 'INVALID_LOGIN_RESPONSE'
    if not isinstance(data, dict):
        return 'INVALID_LOGIN_RESPONSE'
    if data.get('captchaRequired') is True:
        return 'CAPTCHA_REQUIRED'
    if type(data.get('status')) is int:
        if data['status'] == 6:
            return 'TOTP_REQUIRED'
        if data['status'] == 12:
            return 'APP_APPROVAL_REQUIRED'
    if response.status_code == 200 and isinstance(data.get('sessionId'), str) and data['sessionId']:
        return None
    return 'LOGIN_REJECTED'


def login_response_metadata(response):
    """Coarse response shape; no remote text, URL, cookies or identifiers."""
    body = response.content[:65536].lower()
    if not body.strip():
        kind = 'empty'
    elif b'<html' in body or b'<!doctype html' in body:
        kind = 'html'
    else:
        try:
            response.json()
            kind = 'json'
        except (ValueError, TypeError):
            kind = 'other'
    challenge = any(marker in body for marker in
                    (b'cf-chl-', b'challenge-platform', b'g-recaptcha', b'hcaptcha'))
    return {'httpStatus': response.status_code, 'responseFormat': kind,
            'challengePage': challenge}


def permitted(method, url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'trader.degiro.nl':
        return False
    path = parsed.path
    return ((method == 'POST' and path in ('/login/secure/login', '/login/secure/login/totp'))
            or (method == 'GET' and path == '/pa/secure/client')
            or (method == 'POST' and path == '/product_search/secure/v5/products/info')
            or (method == 'GET' and re.fullmatch(r'/trading/secure/v5/update/[0-9]+;jsessionid=[^/]+', path) is not None)
            or (method == 'PUT' and path.startswith('/trading/secure/logout;jsessionid=')))


def run(otp, emit=None, stop=None):
    # All SDK logs are suppressed in this dedicated process, including errors.
    logging.disable(logging.CRITICAL)
    from requests import Session
    from degiro_connector.trading.api import API
    from degiro_connector.trading.models.credentials import Credentials
    from degiro_connector.trading.models.account import UpdateRequest, UpdateOption
    from degiro_connector.core.models.model_session import ModelSession
    from degiro_connector.core.models.model_connection import ModelConnection

    login_reason = None
    login_metadata = None

    class ReadSession(Session):
        def send(self, request, **kwargs):
            nonlocal login_reason, login_metadata
            if not permitted(request.method, request.url):
                raise ValueError('Request outside read-only allowlist')
            kwargs.update(timeout=(5, 8), allow_redirects=False)
            response = super().send(request, **kwargs)
            if request.method == 'POST' and urlsplit(request.url).path in ('/login/secure/login', '/login/secure/login/totp'):
                login_reason = login_diagnostic(response)
                login_metadata = login_response_metadata(response)
            if response.status_code == 405:
                raise RuntimeError('Maintenance response; no additional requests')
            return response

    credentials = Credentials(username=os.environ['BOB_DEGIRO_USERNAME'],
                              password=os.environ['BOB_DEGIRO_PASSWORD'])
    # SDK declares int but converts to str before serializing. Retain leading
    # zeroes in six-digit OTPs; no persistent TOTP seed is collected.
    if otp:
        credentials.one_time_password = otp
    connection = ModelConnection(timeout=60)
    storage = ModelSession(hooks=connection.build_hooks())
    session = ReadSession()
    connection.setup_hooks(session)
    storage.session = session
    api = API(credentials=credentials, connection_storage=connection,
              session_storage=storage, preload=False)
    result = {'code': 'SDK_ERROR', 'logoutConfirmed': False}
    try:
        api.connect()
        details = api.get_client_details()
        account = details.get('data', {}).get('intAccount') if isinstance(details, dict) else None
        if type(account) is not int or account <= 0:
            result['code'] = 'INVALID_RESPONSE'
        else:
            credentials.int_account = account
            portfolio = api.get_update(request_list=[UpdateRequest(option=UpdateOption.PORTFOLIO, last_updated=0)], raw=True)
            result['code'] = 'READ_OK' if isinstance(portfolio, dict) and isinstance(portfolio.get('portfolio'), dict) and isinstance(portfolio['portfolio'].get('value'), list) else 'INVALID_RESPONSE'
            if emit and result['code'] == 'READ_OK':
                from degiro_sync_data import read_snapshot
                import time
                deadline = time.monotonic() + 8*3600
                while not stop.is_set():
                    snapshot = read_snapshot(api, portfolio)
                    emit({'code': 'READ_OK', 'snapshot': snapshot})
                    if stop.wait(30):
                        break
                    if time.monotonic() >= deadline:
                        result['code'] = 'AUTH_REQUIRED'
                        break
                    portfolio = api.get_update(request_list=[UpdateRequest(option=UpdateOption.PORTFOLIO, last_updated=0)], raw=True)
                if stop.is_set():
                    result['code'] = 'STOPPED'
    except Exception as exc:
        # Only classify authentication failures; never serialize exception text.
        result['code'] = 'AUTH_REQUIRED' if type(exc).__name__ == 'DeGiroConnectionError' else 'SDK_ERROR'
        if login_reason:
            result['authReason'] = login_reason
            result['loginResponse'] = login_metadata
    finally:
        if connection.connected.is_set():
            try:
                result['logoutConfirmed'] = api.logout() is True
            except Exception:
                pass
        session.close()
    result['checkedAt'] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == '__main__':
    try:
        payload = json.loads(sys.stdin.read(128))
        otp = payload.get('otp', '')
        if not isinstance(otp, str) or (otp and not re.fullmatch(r'[0-9]{6}', otp)):
            raise ValueError('invalid OTP')
        if payload.get('continuous') is True:
            import signal
            import threading
            stop = threading.Event()
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            result = run(otp, lambda row: print(json.dumps(row), flush=True), stop)
        else:
            result = run(otp)
    except Exception:
        result = {'code': 'SDK_ERROR', 'logoutConfirmed': False}
    print(json.dumps(result))

