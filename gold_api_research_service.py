"""Opt-in daily Gold-API context, isolated from live bars and trading decisions.

Only the push service owns the provider key. PostgreSQL reservations are committed
before HTTP; replicas share the same allowance and cannot repeat a daily job.
"""
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from gold_api_history_research import build_request, request_json, validate

MODES = ('history-day', 'ohlc-range')
LOCK = 736981143
_lock = threading.Lock()
_thread = None


def configuration(env=None):
    env = os.environ if env is None else env
    if env.get('BOB_GOLD_API_DAILY_ENABLED') != '1':
        return 'disabled'
    if env.get('BOB_GOLD_API_COLLECTOR') != 'render-exclusive':
        return 'collector-unconfirmed'
    if not env.get('GOLD_API_KEY'):
        return 'key-not-configured'
    try:
        if int(env.get('BOB_GOLD_API_SERVER_NOT_BEFORE', '0')) <= 0:
            return 'handoff-unconfirmed'
    except ValueError:
        return 'handoff-unconfirmed'
    return 'configured'


def target_day(now):
    # Allow two hours for the final UTC day to settle. Never invent weekend rows.
    day = (datetime.fromtimestamp(now, timezone.utc) - timedelta(hours=2)).date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def interval(day):
    start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    return start, start + 86400


def init(conn):
    conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_gold_daily_context (
        day DATE NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('history-day','ohlc-range')),
        attempted_at BIGINT NOT NULL, completed_at BIGINT,
        status TEXT NOT NULL CHECK(status IN ('attempted','stored','failed')),
        original JSONB, digest TEXT,
        PRIMARY KEY(day,mode))''')
    conn.execute('''CREATE INDEX IF NOT EXISTS bob_gold_daily_attempt_time
        ON bob_gold_daily_context(attempted_at)''')


def claim(conn, day, mode, now):
    if mode not in MODES:
        raise ValueError('Unsupported daily mode')
    conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
    # Future reservations also count when a clock moves backwards.
    count = conn.execute('SELECT count(*) FROM bob_gold_daily_context WHERE attempted_at>%s',
                         (now - 3600,)).fetchone()[0]
    if count >= 8:
        return False
    return conn.execute('''INSERT INTO bob_gold_daily_context(day,mode,attempted_at,status)
        VALUES(%s,%s,%s,'attempted') ON CONFLICT(day,mode) DO NOTHING RETURNING day''',
        (day, mode, now)).fetchone() is not None


def run_once(factory, *, env=None, now=None, requester=request_json):
    env = os.environ if env is None else env
    state = configuration(env)
    if state != 'configured':
        return {'status': state, 'researchOnly': True}
    now = int(time.time()) if now is None else now
    if now < int(env['BOB_GOLD_API_SERVER_NOT_BEFORE']):
        return {'status': 'handoff-cooldown', 'researchOnly': True}
    day = target_day(now)
    start, end = interval(day)
    results = []
    with factory() as conn:
        init(conn)
    for mode in MODES:
        # The context must commit and release the connection before provider I/O.
        with factory() as conn:
            reserved = claim(conn, day, mode, now)
        if not reserved:
            results.append('already-attempted-or-budget-limited')
            continue
        try:
            data = requester(build_request(mode, start, end, now), env['GOLD_API_KEY'])
            validate(mode, data, start, end)
            raw = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
            digest = hashlib.sha256((mode + ':' + str(start) + ':' + str(end) + ':' + raw).encode()).hexdigest()
        except Exception:
            with factory() as conn:
                conn.execute("UPDATE bob_gold_daily_context SET status='failed',completed_at=%s WHERE day=%s AND mode=%s AND status='attempted'",
                             (int(time.time()), day, mode))
            results.append('provider-or-validation-failed')
            continue
        with factory() as conn:
            conn.execute("""UPDATE bob_gold_daily_context SET status='stored',completed_at=%s,
                original=%s::jsonb,digest=%s WHERE day=%s AND mode=%s AND status='attempted'""",
                (int(time.time()), raw, digest, day, mode))
        results.append('stored')
    return {'status': 'checked', 'day': day.isoformat(), 'results': results, 'researchOnly': True}


def summary(conn, *, env=None, now=None):
    env = os.environ if env is None else env
    now = int(time.time()) if now is None else now
    state = configuration(env)
    base = {'researchOnly': True, 'affectsLiveSignals': False,
            'usableAsExecutableQuote': False, 'source': 'Gold-API XAU/USD',
            'kind': 'daily-context-not-intraday-bars', 'status': state}
    if state != 'configured':
        return base
    not_before = int(env['BOB_GOLD_API_SERVER_NOT_BEFORE'])
    if now < not_before:
        return dict(base, status='handoff-cooldown', notBefore=not_before)
    try:
        # Savepoint prevents a missing table during rolling deployment from
        # invalidating the existing research report transaction.
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout='1500ms'")
            rows = conn.execute('''SELECT day,mode,attempted_at,status,original
                FROM bob_gold_daily_context WHERE day=(SELECT max(day) FROM bob_gold_daily_context)
                ORDER BY mode LIMIT 2''').fetchall()
        if not rows:
            return dict(base, status='awaiting-first-collection')
        day = rows[0][0]
        start, end = interval(day)
        items = {}
        for _, mode, at, status, original in rows:
            item = {'status': status, 'attemptedAt': at}
            if status == 'stored':
                validate(mode, original, start, end)
                if mode == 'history-day':
                    item['averageUsd'] = float(original[0]['avg_price'])
                else:
                    item.update({k: float(original[k]) for k in ('open','high','low','close')})
                    item['openCloseChangePct'] = 100 * (item['close']/item['open'] - 1)
                    item['rangePctOfOpen'] = 100 * (item['high'] - item['low']) / item['open']
            items[mode] = item
        expected = target_day(int(time.time()) if now is None else now)
        complete = len(items) == 2 and all(i['status'] == 'stored' for i in items.values())
        return dict(base, day=day.isoformat(), expectedDay=expected.isoformat(), items=items,
                    status='stored' if complete and day == expected else 'stale' if day < expected else 'incomplete')
    except Exception:
        return dict(base, status='unavailable')


def next_delay(*, env=None, now=None):
    """Wake at the handoff boundary, never before it or in a retry spin."""
    env = os.environ if env is None else env
    now = int(time.time()) if now is None else now
    if configuration(env) == 'configured':
        remaining = int(env['BOB_GOLD_API_SERVER_NOT_BEFORE']) - now
        if remaining > 0:
            return min(3600, max(1, remaining))
    return 3600


def start(factory):
    global _thread
    if configuration() != 'configured':
        return False
    with _lock:
        if _thread and _thread.is_alive():
            return True
        def loop():
            # Small delayed daily work; no provider network calls in web reads.
            time.sleep(180)
            while True:
                try:
                    result = run_once(factory)
                    if 'provider-or-validation-failed' in result.get('results', []):
                        print('BOB_GOLD_DAILY status=provider-or-validation-failed', flush=True)
                except Exception:
                    # Fixed, redacted operational evidence; no standalone push.
                    print('BOB_GOLD_DAILY status=unavailable', flush=True)
                time.sleep(next_delay())
        _thread = threading.Thread(target=loop, name='bob-gold-daily', daemon=True)
        _thread.start()
    return True
