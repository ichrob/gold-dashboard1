"""One explicitly requested broker preview, isolated from the read-only worker."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import degiro_readonly
from snaptrade_portfolio import isin as valid_isin

_LOCK = threading.Lock()
_LAST = 0.0
CODES = {'PRECHECK_RESPONSE', 'BROKER_REJECTED', 'UNVERIFIED_RESPONSE',
         'IDENTITY_UNCONFIRMED', 'AUTH_REQUIRED', 'SDK_ERROR'}


def validate(value):
    if not isinstance(value, dict) or set(value) - {'isin','side','quantity','price','currency','otp'}:
        raise ValueError('Invalid preview')
    if not valid_isin(value.get('isin')) or value.get('side') not in ('BUY','SELL'):
        raise ValueError('Invalid identity or side')
    if value.get('currency') not in ('EUR','CHF'):
        raise ValueError('Invalid currency')
    if type(value.get('quantity')) is not int or not 1 <= value['quantity'] <= 100000:
        raise ValueError('Invalid quantity')
    if type(value.get('price')) not in (int,float) or not math.isfinite(value['price']) or not 0 < value['price'] <= 100000:
        raise ValueError('Invalid price')
    otp = value.get('otp','')
    if not isinstance(otp,str) or otp and not re.fullmatch(r'[0-9]{6}',otp):
        raise ValueError('Invalid OTP')
    return dict(value, otp=otp)


def probe(value):
    global _LAST
    payload = validate(value)
    import degiro_sync
    if degiro_sync.status()['running']:
        return {'code':'BUSY','ordersEnabled':False}
    if not degiro_readonly.status()['ready']:
        return {'code':'SETUP_REQUIRED','ordersEnabled':False}
    # Share login admission with the existing one-off reader.
    if not _LOCK.acquire(False):
        return {'code':'BUSY','ordersEnabled':False}
    if not degiro_readonly._LOCK.acquire(False):
        _LOCK.release()
        return {'code':'BUSY','ordersEnabled':False}
    try:
        now = time.monotonic()
        if now - max(_LAST, degiro_readonly._LAST_ATTEMPT) < 60:
            return {'code':'COOLDOWN','ordersEnabled':False}
        _LAST = degiro_readonly._LAST_ATTEMPT = now
        env = {k:os.environ[k] for k in ('PATH','LANG','SYSTEMROOT','PYTHONPATH',
               'BOB_DEGIRO_USERNAME','BOB_DEGIRO_PASSWORD') if k in os.environ}
        child = subprocess.run([sys.executable,str(Path(__file__).with_name('degiro_preflight_worker.py'))],
            input=json.dumps(payload), capture_output=True, text=True, timeout=45, env=env)
        data = json.loads(child.stdout)
        if child.returncode or not isinstance(data,dict) or data.get('code') not in CODES:
            raise ValueError('Invalid worker response')
        result = {k:payload[k] for k in ('isin','side','quantity','price','currency')}
        result.update(code=data['code'],ordersEnabled=False,tradeApproved=False,
                      logoutConfirmed=data.get('logoutConfirmed') is True)
        if data.get('authReason') in degiro_readonly.AUTH_REASONS:
            result['authReason'] = data['authReason']
        from datetime import datetime,timezone
        result['checkedAt'] = datetime.now(timezone.utc).isoformat()
        return result
    except subprocess.TimeoutExpired:
        return {'code':'TIMEOUT','ordersEnabled':False,'tradeApproved':False}
    except Exception:
        return {'code':'SDK_ERROR','ordersEnabled':False,'tradeApproved':False}
    finally:
        degiro_readonly._LOCK.release()
        _LOCK.release()
