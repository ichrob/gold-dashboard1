"""Bounded public health/release checks independent of GitHub cron delivery.

Runs in the existing push service. No orders, credentials, issue writes or new
infrastructure. Process-local observations are not a durable uptime history.
"""
import copy
import threading
import time
from datetime import datetime, timezone

import bob_issue_watchdog as watchdog
from tools import bob_post_deploy_check as release

INTERVAL = 300
RELEASE_INTERVAL = 1800
_lock = threading.Lock()
_thread = None
_stop = threading.Event()
_report = {}
_release_attempt = None


def check_health(reader=watchdog.decode, now=None):
    now = now or datetime.now(timezone.utc)
    values = []
    for url in (watchdog.APP+'/health', watchdog.APP+'/health/background', watchdog.PUSH+'/health'):
        try:
            values.append(reader(url))
        except Exception:
            values.append(None)
    codes = watchdog.classify(*values, market_open=watchdog.active_session(now))
    # Product proof gaps have their own private audit, not a service outage.
    codes = [code for code in codes if code in watchdog.CODES and code not in watchdog.PRODUCT_CODES]
    observation = dict(state='degraded' if codes else 'ok', codes=codes,
                       checkedAt=now.isoformat())
    return observation, values[0], values[2]


def check_release(scanner, push, now, reader=release.read_ci_evidence):
    try:
        sha, runs = reader()
        result = release.classify(sha, runs, scanner, push, now)
        result['commit'] = sha[:12] if isinstance(sha, str) and release.SHA.fullmatch(sha) else None
    except Exception:
        result = dict(state='unavailable', reason='github-read-unavailable')
    result['checkedAt'] = now.isoformat()
    return result


def tick(now=None, monotonic=None, health_reader=watchdog.decode, ci_reader=release.read_ci_evidence):
    global _release_attempt
    now = now or datetime.now(timezone.utc)
    monotonic = time.monotonic() if monotonic is None else monotonic
    observed, scanner, push = check_health(health_reader, now)
    # Reserve the next attempt even on failure: GitHub errors never cause a
    # tight retry loop or delay the separate five-minute health observation.
    with _lock:
        due = _release_attempt is None or monotonic-_release_attempt >= RELEASE_INTERVAL
        if due:
            _release_attempt = monotonic
    deployment = check_release(scanner, push, now, ci_reader) if due else None
    with _lock:
        _report['health'] = observed
        _report['samples'] = (_report.get('samples', [])+[observed])[-12:]
        if deployment is not None:
            _report['deployment'] = deployment


def snapshot(now=None):
    now = time.time() if now is None else now
    with _lock:
        result = copy.deepcopy(_report)
        running = _thread is not None and _thread.is_alive()
    for key, maximum in (('health', INTERVAL+120), ('deployment', RELEASE_INTERVAL+120)):
        item = result.setdefault(key, dict(state='not-checked'))
        at = release.utc_time(item.get('checkedAt'))
        age = now-at.timestamp() if at else None
        item['fresh'] = age is not None and 0 <= age <= maximum
        if at and not item['fresh']:
            item['observedState'] = item['state']
            item['state'] = 'stale'
    result.update(running=running, intervalSeconds=INTERVAL,
                  deploymentIntervalSeconds=RELEASE_INTERVAL, readOnly=True,
                  scheduler='push-process', independentOfGitHubSchedule=True,
                  scope='process-local-observations; not protection against both services failing')
    return result


def _loop():
    # Let HTTP/database warmup complete; the public health route reads only
    # snapshot() and never recursively invokes this check.
    if _stop.wait(90):
        return
    while not _stop.is_set():
        started = time.monotonic()
        try:
            tick()
        except Exception:
            # Keep the previous clock: a failed attempt is not a fresh success.
            print('BOB_RUNTIME_WATCHDOG check_failed', flush=True)
        if _stop.wait(max(1, INTERVAL-(time.monotonic()-started))):
            return


def start():
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _stop.clear()
            _thread = threading.Thread(target=_loop, name='bob-runtime-watchdog', daemon=True)
            _thread.start()
