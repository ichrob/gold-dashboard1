"""Isolated SDK worker: fixed login/read/logout allowlist; no order endpoint."""
from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
from urllib.parse import urlsplit


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

    class ReadSession(Session):
        def send(self, request, **kwargs):
            if not permitted(request.method, request.url):
                raise ValueError('Request outside read-only allowlist')
            kwargs.update(timeout=(5, 8), allow_redirects=False)
            response = super().send(request, **kwargs)
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
