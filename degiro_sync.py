"""One bounded read-only broker session; secrets stay in an isolated child."""
import atexit
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import degiro_readonly

_LOCK = threading.RLock()
_PROCESS = None
_STATE = {'code': 'NOT_STARTED', 'snapshot': None}
_LAST_START = 0.0
_LAST_MESSAGE = 0.0


def status():
    with _LOCK:
        out = copy.deepcopy(_STATE)
        out['running'] = _PROCESS is not None and _PROCESS.poll() is None
    snapshot = out.get('snapshot')
    age = None
    if snapshot:
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(snapshot['observedAt'])).total_seconds()
    out.update(fresh=out['running'] and out['code'] == 'READ_OK' and age is not None and 0 <= age <= 90,
               ageSeconds=round(age, 1) if age is not None else None,
               intervalSeconds=30, liveOrdersEnabled=False, liveQuotes=False)
    return out


def _watch(process):
    global _LAST_MESSAGE
    try:
        while True:
            line = process.stdout.readline(2_000_001)
            if not line:
                break
            if len(line) > 2_000_000:
                raise ValueError('Oversized worker message')
            data = json.loads(line)
            if not isinstance(data, dict) or data.get('code') not in {'READ_OK','AUTH_REQUIRED','SDK_ERROR','INVALID_RESPONSE','STOPPED'}:
                raise ValueError('Invalid worker message')
            with _LOCK:
                if _PROCESS is not process:
                    break
                _STATE['code'] = data['code']
                _LAST_MESSAGE = time.monotonic()
                snapshot = data.get('snapshot')
                if data['code'] == 'READ_OK' and isinstance(snapshot, dict):
                    # Only normalized worker holdings enter the authenticated endpoint.
                    if snapshot.get('complete') is not True or not isinstance(snapshot.get('holdings'), list):
                        raise ValueError('Incomplete worker snapshot')
                    datetime.fromisoformat(snapshot['observedAt'])
                    _STATE['snapshot'] = snapshot
                if 'logoutConfirmed' in data:
                    _STATE['logoutConfirmed'] = data['logoutConfirmed'] is True
    except Exception:
        with _LOCK:
            if _PROCESS is process:
                _STATE['code'] = 'SDK_ERROR'
        process.terminate()
    finally:
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        with _LOCK:
            if _PROCESS is process and _STATE['code'] in {'READ_OK','STARTING'}:
                _STATE['code'] = 'DISCONNECTED'
        process.stdout.close()


def _deadline(process):
    while process.poll() is None:
        time.sleep(5)
        with _LOCK:
            if _PROCESS is not process:
                return
            if time.monotonic()-_LAST_MESSAGE > 90:
                _STATE['code'] = 'TIMEOUT'
                process.terminate()
                break
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()


def start(otp=''):
    global _PROCESS, _LAST_START, _LAST_MESSAGE
    if not isinstance(otp,str) or (otp and not re.fullmatch(r'[0-9]{6}',otp)):
        raise ValueError('Invalid OTP')
    with _LOCK:
        if _PROCESS is not None and _PROCESS.poll() is None:
            return status()
        if not degiro_readonly.status()['ready']:
            _STATE['code'] = 'SETUP_REQUIRED'
            return status()
        if _LAST_START and time.monotonic()-_LAST_START < 60:
            return {**status(), 'code': 'COOLDOWN'}
        _LAST_START = time.monotonic()
        env = {k:os.environ[k] for k in ('PATH','LANG','SYSTEMROOT','PYTHONPATH','BOB_DEGIRO_USERNAME','BOB_DEGIRO_PASSWORD') if k in os.environ}
        _STATE.update(code='STARTING', logoutConfirmed=False)
        _LAST_MESSAGE = time.monotonic()
        _PROCESS = subprocess.Popen([sys.executable,str(Path(__file__).with_name('degiro_readonly_worker.py'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env)
        _PROCESS.stdin.write(json.dumps({'otp':otp,'continuous':True}))
        _PROCESS.stdin.close()
        threading.Thread(target=_watch,args=(_PROCESS,),daemon=True,name='degiro-read-sync').start()
        threading.Thread(target=_deadline,args=(_PROCESS,),daemon=True,name='degiro-read-deadline').start()
        return status()


def stop():
    with _LOCK:
        process = _PROCESS
        if process is not None and process.poll() is None:
            _STATE['code'] = 'STOPPING'
            process.terminate()
        else:
            _STATE['code'] = 'STOPPED'
    return status()


atexit.register(stop)
