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


def status():
    try:
        version = importlib.metadata.version('degiro-connector')
    except importlib.metadata.PackageNotFoundError:
        version = None
    configured = bool(os.environ.get('BOB_DEGIRO_USERNAME') and os.environ.get('BOB_DEGIRO_PASSWORD'))
    return {'mode': 'READ_ONLY', 'sdkVersion': version, 'expectedVersion': SDK_VERSION,
            'sdkReady': version == SDK_VERSION, 'credentialsConfigured': configured,
            'ready': version == SDK_VERSION and configured,
            'brokerConnectionTested': False, 'liveOrdersEnabled': False}


def probe(otp=''):
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
