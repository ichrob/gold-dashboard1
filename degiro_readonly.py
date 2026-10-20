"""Optional, manually triggered DEGIRO SDK probe. No trading methods or jobs."""
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

SDK_VERSION = '3.0.36'
_LOCK = threading.Lock()
_LAST_ATTEMPT = 0.0
_LAST_RESULT = None
AUTH_REASONS = frozenset({'RATE_LIMITED', 'ACCESS_DENIED', 'SERVICE_UNAVAILABLE',
                         'INVALID_LOGIN_RESPONSE', 'CAPTCHA_REQUIRED',
                         'TOTP_REQUIRED', 'APP_APPROVAL_REQUIRED', 'LOGIN_REJECTED', 'LOGIN_REDIRECT'})


def safe_login_response(value):
    if not isinstance(value, dict):
        return None
    code = value.get('httpStatus')
    kind = value.get('responseFormat')
    if type(code) is not int or not 100 <= code <= 599 or kind not in {'empty', 'html', 'json', 'other'}:
        return None
    result = {'httpStatus': code, 'responseFormat': kind,
              'challengePage': value.get('challengePage') is True}
    if code in (301, 302, 303, 307, 308):
        host = value.get('redirectHost')
        route = value.get('redirectRoute')
        result.update(redirectHost=host if host in {'trader.degiro.nl', 'trader.degiro.com', 'login.degiro.com', 'www.degiro.nl', 'www.degiro.com'} else 'other',
                      redirectRoute=route if route in {'login-page', 'login-api', 'totp-api', 'trader-page', 'captcha', 'challenge', 'maintenance', 'blocked', 'denied', 'error'} else 'other',
                      redirectHttps=value.get('redirectHttps') is True,
                      redirectHasQuery=value.get('redirectHasQuery') is True)
    return result


def status():
    try:
        version = importlib.metadata.version('degiro-connector')
    except importlib.metadata.PackageNotFoundError:
        version = None
    configured = bool(os.environ.get('BOB_DEGIRO_USERNAME') and os.environ.get('BOB_DEGIRO_PASSWORD'))
    return {'mode': 'READ_ONLY', 'sdkVersion': version, 'expectedVersion': SDK_VERSION,
            'sdkReady': version == SDK_VERSION, 'credentialsConfigured': configured,
            'ready': version == SDK_VERSION and configured,
            'brokerConnectionTested': _LAST_RESULT is not None,
            'lastTest': dict(_LAST_RESULT) if _LAST_RESULT else None,
            'liveOrdersEnabled': False}


def probe(otp=''):
    global _LAST_RESULT
    result = _probe(otp)
    if result.get('code') not in {'BUSY', 'COOLDOWN', 'SETUP_REQUIRED'}:
        from datetime import datetime, timezone
        _LAST_RESULT = {'code': result['code'],
                        'checkedAt': datetime.now(timezone.utc).isoformat(),
                        'authReason': result.get('authReason')}
        _LAST_RESULT['loginResponse'] = safe_login_response(result.get('loginResponse'))
    return result


def _probe(otp=''):
    global _LAST_ATTEMPT
    if not isinstance(otp, str) or (otp and not re.fullmatch(r'[0-9]{6}', otp)):
        raise ValueError('Bitte einen sechsstelligen Einmalcode eingeben oder das Feld leer lassen.')
    report = status()
    if not report['ready']:
        return {**report, 'ok': False, 'code': 'SETUP_REQUIRED'}
    if not _LOCK.acquire(blocking=False):
        return {'ok': False, 'code': 'BUSY', 'liveOrdersEnabled': False}
    try:
        now = time.monotonic()
        if _LAST_ATTEMPT and now-_LAST_ATTEMPT < 60:
            return {'ok': False, 'code': 'COOLDOWN', 'liveOrdersEnabled': False}
        _LAST_ATTEMPT = now
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'SYSTEMROOT', 'PYTHONPATH',
               'BOB_DEGIRO_USERNAME', 'BOB_DEGIRO_PASSWORD') if key in os.environ}
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('degiro_readonly_worker.py'))],
                                input=json.dumps({'otp': otp}), capture_output=True,
                                text=True, timeout=45, env=env)
        # Never return SDK output or stderr verbatim: these may contain secrets.
        data = json.loads(result.stdout)
        codes = {'READ_OK', 'AUTH_REQUIRED', 'SDK_ERROR', 'INVALID_RESPONSE'}
        if result.returncode or not isinstance(data, dict) or data.get('code') not in codes:
            raise ValueError('invalid worker result')
        return {'ok': data['code'] == 'READ_OK', 'code': data['code'],
                'authReason': data.get('authReason') if data.get('authReason') in AUTH_REASONS else None,
                'loginResponse': safe_login_response(data.get('loginResponse')),
                'liveOrdersEnabled': False, 'mode': 'READ_ONLY',
                'checkedAt': data.get('checkedAt') if isinstance(data.get('checkedAt'), str) else None,
                'portfolioRead': data['code'] == 'READ_OK',
                'logoutConfirmed': data.get('logoutConfirmed') is True}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'code': 'TIMEOUT', 'liveOrdersEnabled': False}
    except Exception:
        return {'ok': False, 'code': 'SDK_ERROR', 'liveOrdersEnabled': False}
    finally:
        _LOCK.release()

