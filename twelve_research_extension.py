"""Research-only Twelve Data expansion: no UI, trading, paid upgrades or live feed.

The existing gold_fallback.py remains the verified single-hour probe.
Additional scopes are disabled until individually licensed and confirmed.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta, time as clock_time
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

INTERVAL_MS = {'1min': 60000, '5min': 300000, '15min': 900000,
               '30min': 1800000, '1h': 3600000, '4h': 14400000,
               '8h': 28800000, '1day': 86400000}
# 13 Nov 2026: provider confirmed direct cross FX and 4h/8h XAU/USD
# for occasional, manual, private non-display Basic evaluation only.
SYMBOLS = frozenset(('XAU/USD', 'EUR/USD', 'USD/CHF', 'EUR/CHF', 'CHF/EUR'))
CONFIRMED_GOLD_INTERVALS = frozenset(INTERVAL_MS)
# FX interval entitlements remain individually opt-in and source-time validated;
# XAU/USD daily Sydney time must not be assumed for any FX instrument.
POTENTIAL_FX_INTERVALS = frozenset(('1min', '5min', '15min', '30min', '1h', '4h', '8h'))
SYDNEY = ZoneInfo('Australia/Sydney')
MAX_BARS = 500
MAX_RESPONSE_BYTES = 512000
MINUTE_BUDGET = 7  # reserve one credit below the published 8
DAY_BUDGET = 700  # 100-credit margin below the published 800


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def scope_allowed(symbol, interval, env=None):
    """One-shot internal research only; no scheduled, display or broker use."""
    env = os.environ if env is None else env
    if env.get('BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED') != '1':
        return False
    # Written Twelve Data support confirmations, 12–13 Nov 2026:
    # all XAU/USD intervals below including 4h/8h and Sydney-calendar daily.
    if symbol == 'XAU/USD' and interval in CONFIRMED_GOLD_INTERVALS:
        return True
    # Direct FX pairs confirmed on Basic 13 Nov. Keep per-pair/per-interval
    # opt-in AND independently verified UTC source metadata. FX daily bars
    # remain blocked until their own daily-calendar timezone is established.
    if symbol in ('EUR/USD', 'USD/CHF', 'EUR/CHF', 'CHF/EUR') and interval in POTENTIAL_FX_INTERVALS:
        key = 'BOB_TWELVEDATA_SCOPE_' + symbol.replace('/', '_') + '_' + interval.upper()
        return env.get(key) == '1'
    return False


def _sydney_midnight_ms(day):
    """Actual UTC instant of a Sydney calendar day, including DST shifts."""
    return int(datetime.combine(day, clock_time.min, tzinfo=SYDNEY).timestamp() * 1000)


def _sydney_day(ms):
    return datetime.fromtimestamp(ms / 1000, SYDNEY).date()


def _daily_start_aligned(ms):
    return type(ms) is int and ms == _sydney_midnight_ms(_sydney_day(ms))


def _next_daily_start(ms):
    return _sydney_midnight_ms(_sydney_day(ms) + timedelta(days=1))


def _previous_daily_start(ms):
    return _sydney_midnight_ms(_sydney_day(ms) - timedelta(days=1))


def valid_window(symbol, interval, start_ms, end_ms, now_ms):
    """UTC instants; 1day boundaries MUST be Sydney calendar midnights."""
    if not all(type(v) is int for v in (start_ms, end_ms, now_ms)):
        return False
    if not (start_ms > 0 and start_ms < end_ms <= now_ms):
        return False
    if interval == '1day':
        return (symbol == 'XAU/USD' and _daily_start_aligned(start_ms)
                and _daily_start_aligned(end_ms)
                and 1 <= (_sydney_day(end_ms) - _sydney_day(start_ms)).days <= MAX_BARS)
    step = INTERVAL_MS.get(interval)
    return bool(step and start_ms % step == 0 and end_ms % step == 0
                and 1 <= (end_ms - start_ms) // step <= MAX_BARS)


def valid_key(value):
    return bool(value and value.strip() and value.strip().lower()
                not in ('demo', 'your_api_key', 'ihr_twelvedata_api_key'))


def validate_rows(payload, symbol, interval, start_ms, end_ms, now_ms):
    """Only complete UTC bars from the exact requested source; refuse metadata ambiguity."""
    if symbol not in SYMBOLS or interval not in INTERVAL_MS:
        raise ValueError('scope')
    step = INTERVAL_MS[interval]
    if not all(type(v) is int for v in (start_ms, end_ms, now_ms)):
        raise ValueError('clock')
    if not valid_window(symbol, interval, start_ms, end_ms, now_ms):
        raise ValueError('bounds')
    if not isinstance(payload, dict):
        raise ValueError('payload')
    meta = payload.get('meta')
    if not isinstance(meta, dict) or meta.get('symbol') != symbol or meta.get('interval') != interval:
        raise ValueError('identity')
    zone = meta.get('exchange_timezone')
    metal = (symbol == 'XAU/USD'
             and meta.get('type') == 'Precious Metal'
             and meta.get('currency_base') == 'Gold Spot'
             and meta.get('currency_quote') == 'US Dollar')
    if interval == '1day':
        # Support explicitly confirmed Sydney-labelled XAU/USD daily bars
        # on 13 Nov. Timezone=UTC request is ignored for daily bars.
        if not metal or (zone is not None and zone != 'Australia/Sydney'):
            raise ValueError('daily-timezone')
    elif zone != 'UTC':
        # Confirmed precious-metal intraday payload may omit the timezone,
        # but no FX payload receives that exception.
        if not (metal and 'exchange_timezone' not in meta):
            raise ValueError('timezone')
    values = payload.get('values')
    if not isinstance(values, list) or len(values) > MAX_BARS:
        raise ValueError('bars')
    rows, seen = [], set()
    for bar in values:
        if not isinstance(bar, dict):
            raise ValueError('bar')
        if interval == '1day':
            label = bar['datetime']
            if not isinstance(label, str) or not re.fullmatch(
                    r'\\d{4}-\\d{2}-\\d{2}(?: 00:00:00)?', label):
                raise ValueError('daily-label')
            day = datetime.strptime(label[:10], '%Y-%m-%d').date()
            opened = _sydney_midnight_ms(day)
            next_open = _next_daily_start(opened)
        else:
            dt = datetime.strptime(bar['datetime'], '%Y-%m-%d %H:%M:%S')
            opened = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if opened % step:
                raise ValueError('alignment')
            next_open = opened + step
        if opened in seen:
            raise ValueError('duplicate-or-alignment')
        seen.add(opened)
        if not start_ms <= opened < end_ms:
            raise ValueError('unexpected-time')
        if next_open > now_ms:
            raise ValueError('unclosed')
        prices = {}
        for field in ('open', 'high', 'low', 'close'):
            v = bar[field]
            if isinstance(v, bool):
                raise ValueError('boolean-price')
            v = float(v)
            if not math.isfinite(v) or v <= 0:
                raise ValueError('price')
            prices[field] = v
        if prices['low'] > min(prices['open'], prices['close']) or prices['high'] < max(prices['open'], prices['close']):
            raise ValueError('ohlc')
        rows.append(dict(source='twelvedata', symbol=symbol, interval=interval,
                         openTime=opened, fetchedAt=now_ms, researchOnly=True,
                         isExecutableQuote=False, **prices))
    return sorted(rows, key=lambda r: r['openTime'])


def reserve_credit(db, now_ms):
    """Atomic locally durable reservation; never share across replicas without coordination."""
    db.execute('CREATE TABLE IF NOT EXISTS td_credit_ledger (id INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL)')
    db.execute('DELETE FROM td_credit_ledger WHERE at_ms < ?', (now_ms - 86400000,))
    per_min = db.execute('SELECT COUNT(*) FROM td_credit_ledger WHERE at_ms > ?', (now_ms - 60000,)).fetchone()[0]
    per_day = db.execute('SELECT COUNT(*) FROM td_credit_ledger').fetchone()[0]
    if per_min >= MINUTE_BUDGET or per_day >= DAY_BUDGET:
        return False
    db.execute('INSERT INTO td_credit_ledger(at_ms) VALUES (?)', (now_ms,))
    return True


def init_archive(db):
    db.execute('''CREATE TABLE IF NOT EXISTS td_research_bars (
       source TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT NOT NULL,
       open_ms INTEGER NOT NULL, revision TEXT NOT NULL,
       open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
       first_seen_ms INTEGER NOT NULL, last_seen_ms INTEGER NOT NULL,
       PRIMARY KEY (source,symbol,interval,open_ms,revision))''')


def store_rows(db, rows):
    init_archive(db)
    for row in rows:
        if (row.get('source') != 'twelvedata' or row.get('researchOnly') is not True
                or row.get('isExecutableQuote') is not False):
            raise ValueError('research-only provenance')
        digest = hashlib.sha256(json.dumps([row[k] for k in ('open','high','low','close')],
                                           separators=(',', ':')).encode()).hexdigest()
        db.execute('''INSERT INTO td_research_bars VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source,symbol,interval,open_ms,revision)
            DO UPDATE SET last_seen_ms=MAX(last_seen_ms,excluded.last_seen_ms)''',
            ('twelvedata', row['symbol'], row['interval'], row['openTime'], digest,
             row['open'], row['high'], row['low'], row['close'], row['fetchedAt'], row['fetchedAt']))


def gaps(rows, interval, *, start_ms=None, end_ms=None):
    """Detect missing intervals including requested start/end, not proven outages."""
    step = INTERVAL_MS[interval]
    ordered = sorted(rows, key=lambda r: r['openTime'])
    successor = _next_daily_start if interval == '1day' else lambda t: t + step
    predecessor = _previous_daily_start if interval == '1day' else lambda t: t - step
    ranges = []
    if not ordered:
        if start_ms is not None and end_ms is not None and end_ms > start_ms:
            ranges.append((start_ms, predecessor(end_ms)))
    else:
        if start_ms is not None and ordered[0]['openTime'] > start_ms:
            ranges.append((start_ms, predecessor(ordered[0]['openTime'])))
        for left, right in zip(ordered, ordered[1:]):
            following = successor(left['openTime'])
            if right['openTime'] > following:
                ranges.append((following, predecessor(right['openTime'])))
        if end_ms is not None and successor(ordered[-1]['openTime']) < end_ms:
            ranges.append((successor(ordered[-1]['openTime']), predecessor(end_ms)))
    return [{'startMs': start, 'endMs': end, 'sessionStatus': 'unverified',
             'automaticBackfillAllowed': False} for start, end in ranges]


def research_ema(rows, period=20):
    """Local internal-only derived research; never serve in a dashboard/API."""
    if period < 2:
        return None
    ordered = _contiguous_closes(rows, period)
    if ordered is None:
        return None
    closes = [r['close'] for r in ordered]
    current = sum(closes[:period]) / period
    alpha = 2 / (period+1)
    for close in closes[period:]:
        current += alpha * (close-current)
    return current



def _contiguous_closes(rows, minimum):
    if len(rows) < minimum:
        return None
    ordered = sorted(rows, key=lambda x: x['openTime'])
    if not ordered or any(
            r.get('source') != 'twelvedata'
            or r.get('researchOnly') is not True
            or r.get('isExecutableQuote') is not False
            or not isinstance(r.get('close'), (int, float))
            or isinstance(r.get('close'), bool)
            or not math.isfinite(r['close'])
            or r['close'] <= 0 for r in ordered):
        return None
    step = INTERVAL_MS.get(ordered[0]['interval'])
    if not step or any(r['symbol'] != ordered[0]['symbol'] or
                       r['interval'] != ordered[0]['interval'] for r in ordered):
        return None
    successor = _next_daily_start if ordered[0]['interval'] == '1day' else lambda t: t + step
    if any(b['openTime'] != successor(a['openTime']) for a,b in zip(ordered,ordered[1:])):
        return None
    return ordered


def research_macd(rows, fast=12, slow=26, signal=9):
    """Internally compare EMA12/26 and MACD signal; never publish derived values."""
    if not (2 <= fast < slow and signal >= 2):
        raise ValueError('periods')
    ordered=_contiguous_closes(rows, slow+signal-1)
    if ordered is None:
        return None
    prices=[r['close'] for r in ordered]
    def ema(values, period):
        result=[None]*(period-1)
        current=sum(values[:period])/period
        result.append(current)
        alpha=2/(period+1)
        for v in values[period:]:
            current+=alpha*(v-current)
            result.append(current)
        return result
    fast_values=ema(prices,fast)
    slow_values=ema(prices,slow)
    macd=[f-s for f,s in zip(fast_values,slow_values) if f is not None and s is not None]
    signal_value=ema(macd,signal)[-1]
    return {'macd':macd[-1],'signal':signal_value,'histogram':macd[-1]-signal_value}


def research_rsi(rows, period=14):
    if period < 2:
        raise ValueError('period')
    ordered=_contiguous_closes(rows,period+1)
    if ordered is None:
        return None
    prices=[r['close'] for r in ordered]
    deltas=[b-a for a,b in zip(prices,prices[1:])]
    gains=[max(d,0) for d in deltas]
    losses=[max(-d,0) for d in deltas]
    ag=sum(gains[:period])/period
    al=sum(losses[:period])/period
    for gain,loss in zip(gains[period:],losses[period:]):
        ag=(ag*(period-1)+gain)/period
        al=(al*(period-1)+loss)/period
    return 100.0 if al==0 else 100-100/(1+ag/al)


def research_atr(rows, period=14):
    if period < 2:
        raise ValueError('period')
    ordered=_contiguous_closes(rows,period+1)
    if ordered is None:
        return None
    ranges=[]
    for before,bar in zip(ordered,ordered[1:]):
        ranges.append(max(bar['high']-bar['low'],
                          abs(bar['high']-before['close']),
                          abs(bar['low']-before['close'])))
    atr=sum(ranges[:period])/period
    for true_range in ranges[period:]:
        atr=(atr*(period-1)+true_range)/period
    return atr


def research_chf_cross(eur_usd_rows, usd_chf_rows):
    """Same-timestamp, same-vendor EUR/CHF and CHF/EUR internal research only.

    No executable broker FX, product valuation, or application/API display.
    Missing/misaligned, unlicensed, or mixed-source observations fail closed.
    """
    left = _contiguous_closes(eur_usd_rows, 1)
    right = _contiguous_closes(usd_chf_rows, 1)
    if not left or not right:
        return {'code': 'NO_MATCHING_FX_ORIGINALS'}
    if (left[0]['symbol'] != 'EUR/USD' or right[0]['symbol'] != 'USD/CHF'
            or left[0]['interval'] != right[0]['interval']
            or [r['openTime'] for r in left] != [r['openTime'] for r in right]
            or any(r.get('source') != 'twelvedata' for r in left + right)):
        return {'code': 'NO_MATCHING_FX_ORIGINALS'}
    eur_usd = left[-1]['close']
    usd_chf = right[-1]['close']
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v) and v > 0 for v in (eur_usd, usd_chf))):
        return {'code': 'INVALID_FX_ORIGINAL'}
    eur_chf = eur_usd * usd_chf
    return {'code': 'INTERNAL_FX_CROSS_RESEARCH_ONLY',
            'EUR_CHF': eur_chf, 'CHF_EUR': 1 / eur_chf,
            'atMs': left[-1]['openTime'], 'interval': left[-1]['interval'],
            'researchOnly': True, 'isExecutableQuote': False}


def compare_entry_shadow(rows, *, direction='LONG', hold_bars=3):
    """Gross spot-reference comparison only, not an executable product or realized P/L."""
    if direction not in ('LONG','SHORT') or hold_bars < 1:
        raise ValueError('parameters')
    ordered=_contiguous_closes(rows,hold_bars+1)
    if ordered is None:
        return {'code':'INSUFFICIENT_CONTIGUOUS_RESEARCH'}
    entry=ordered[-1-hold_bars]['close']
    exit_price=ordered[-1]['close']
    move=(exit_price/entry-1)*(1 if direction=='LONG' else -1)
    return {'code':'RESEARCH_SPOT_REFERENCE_ONLY','grossMoveFraction':move,
            'barsHeld':hold_bars,'executableProductPnL':False,
            'researchOnly':True}

def fetch_research(db, symbol, interval, start_ms, end_ms, *, now_ms=None, opener=None):
    """Manual, one-request, opt-in probe; no scheduler, retries or redirects."""
    if symbol not in SYMBOLS or interval not in INTERVAL_MS:
        return {'code':'UNSUPPORTED_SCOPE'}
    if not scope_allowed(symbol, interval):
        return {'code':'SCOPE_NOT_AUTHORIZED'}
    key = os.environ.get('TWELVEDATA_API_KEY', '').strip()
    if not valid_key(key):
        return {'code':'KEY_NOT_CONFIGURED'}
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    step = INTERVAL_MS[interval]
    if not valid_window(symbol, interval, start_ms, end_ms, now_ms):
        return {'code':'INVALID_RANGE'}
    if os.environ.get('BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED') != '1':
        return {'code':'WORKER_COORDINATION_UNCONFIRMED'}
    # BEGIN IMMEDIATE prevents two callers on the same SQLite file from passing quota together.
    # Deployment must use one persistent shared ledger and one worker.
    with db:
        db.execute('BEGIN IMMEDIATE')
        if not reserve_credit(db, now_ms):
            return {'code':'CREDIT_BUDGET_EXHAUSTED'}
    if interval == '1day':
        # /time_series ignores timezone for daily XAU/USD. Use Sydney
        # calendar labels; no 24h UTC arithmetic across DST.
        dates = {'start_date': _sydney_day(start_ms).isoformat(),
                 'end_date': _sydney_day(_previous_daily_start(end_ms)).isoformat()}
        params = urlencode(dict(symbol=symbol, interval=interval, **dates))
    else:
        stamp = lambda ms: datetime.fromtimestamp(
            ms/1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        params = urlencode(dict(symbol=symbol, interval=interval, timezone='UTC',
                                start_date=stamp(start_ms),
                                end_date=stamp(end_ms-step)))
    try:
        client = opener or build_opener(NoRedirect())
        request = Request('https://api.twelvedata.com/time_series?' + params,
                          headers={'Authorization': 'apikey ' + key, 'Accept': 'application/json'})
        with client.open(request, timeout=10) as response:
            raw = response.read(MAX_RESPONSE_BYTES+1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return {'code':'RESPONSE_TOO_LARGE'}
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get('status') == 'error':
            return {'code':'PROVIDER_REJECTED'}
        rows = validate_rows(payload, symbol, interval, start_ms, end_ms, now_ms)
        if not rows:
            return {'code': 'NO_BARS', 'missingRanges': len(gaps(
                rows, interval, start_ms=start_ms, end_ms=end_ms)),
                'researchOnly': True}
        with db:
            store_rows(db, rows)
        return {'code':'OBSERVED','stored':len(rows),
                'missingRanges':len(gaps(rows,interval,
                                        start_ms=start_ms,end_ms=end_ms)),
                'researchOnly':True}
    except HTTPError as exc:
        return {'code':'HTTP_ERROR','httpStatus':exc.code}
    except (URLError, TimeoutError, OSError):
        return {'code':'NETWORK_ERROR'}
    except (KeyError,TypeError,ValueError,OverflowError):
        return {'code':'INVALID_RESPONSE'}
    # Do not log request headers or exceptions: authorization is secret.



def fetch_earliest_timestamp(db, symbol, interval, *, now_ms=None, opener=None):
    """Manual, one-request historical-depth probe. Return status only, not data."""
    if symbol not in SYMBOLS or interval not in INTERVAL_MS:
        return {'code': 'UNSUPPORTED_SCOPE'}
    if not scope_allowed(symbol, interval):
        return {'code': 'SCOPE_NOT_AUTHORIZED'}
    key = os.environ.get('TWELVEDATA_API_KEY', '').strip()
    if not valid_key(key):
        return {'code': 'KEY_NOT_CONFIGURED'}
    if os.environ.get('BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED') != '1':
        return {'code': 'WORKER_COORDINATION_UNCONFIRMED'}
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if type(now_ms) is not int or now_ms <= 0:
        return {'code': 'INVALID_RANGE'}
    with db:
        db.execute('BEGIN IMMEDIATE')
        if not reserve_credit(db, now_ms):
            return {'code': 'CREDIT_BUDGET_EXHAUSTED'}
    params = urlencode({'symbol': symbol, 'interval': interval,
                        'timezone': 'UTC'})
    try:
        client = opener or build_opener(NoRedirect())
        request = Request('https://api.twelvedata.com/earliest_timestamp?' + params,
                          headers={'Authorization': 'apikey ' + key, 'Accept': 'application/json'})
        with client.open(request, timeout=10) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return {'code': 'RESPONSE_TOO_LARGE'}
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get('status') == 'error':
            return {'code': 'PROVIDER_REJECTED'}
        unix_time, label = payload.get('unix_time'), payload.get('datetime')
        if (type(unix_time) is not int or unix_time <= 0
                or unix_time * 1000 > now_ms
                or not isinstance(label, str) or not 10 <= len(label) <= 25):
            return {'code': 'INVALID_RESPONSE'}
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS td_research_depth (
              symbol TEXT NOT NULL, interval TEXT NOT NULL,
              earliest_unix INTEGER NOT NULL, earliest_label TEXT NOT NULL,
              checked_ms INTEGER NOT NULL,
              PRIMARY KEY(symbol, interval))""")
            db.execute("""INSERT INTO td_research_depth
                (symbol,interval,earliest_unix,earliest_label,checked_ms)
                VALUES (?,?,?,?,?)
                ON CONFLICT(symbol,interval) DO UPDATE SET
                    earliest_unix=excluded.earliest_unix,
                    earliest_label=excluded.earliest_label,
                    checked_ms=excluded.checked_ms""",
                       (symbol, interval, unix_time, label, now_ms))
        return {'code': 'OBSERVED_EARLIEST', 'stored': True,
                'researchOnly': True}
    except HTTPError as exc:
        return {'code': 'HTTP_ERROR', 'httpStatus': exc.code}
    except (URLError, TimeoutError, OSError):
        return {'code': 'NETWORK_ERROR'}
    except (ValueError, TypeError, OverflowError, sqlite3.Error):
        return {'code': 'INVALID_RESPONSE'}
    # Never log authorization headers, request objects or exceptions.


def main():
    parser = argparse.ArgumentParser(description='Isolated Twelve Data research, no live/GUI output')
    parser.add_argument('--symbol', required=True, choices=sorted(SYMBOLS))
    parser.add_argument('--interval', required=True, choices=sorted(INTERVAL_MS))
    parser.add_argument('--earliest-only', action='store_true',
                        help='one manual historical-depth query; no price output')
    parser.add_argument('--start-utc', help='YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--end-utc', help='YYYY-MM-DD HH:MM:SS (exclusive)')
    parser.add_argument('--archive', required=True, help='persistent private SQLite, not Render ephemeral disk')
    args = parser.parse_args()
    parse = lambda v: int(datetime.strptime(v,'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
    if not args.earliest_only and not (args.start_utc and args.end_utc):
        parser.error('--start-utc and --end-utc are required unless --earliest-only')
    with sqlite3.connect(args.archive,timeout=10,isolation_level=None) as db:
        if args.earliest_only:
            result = fetch_earliest_timestamp(db,args.symbol,args.interval)
        else:
            result = fetch_research(db,args.symbol,args.interval,
                                    parse(args.start_utc),parse(args.end_utc))
    print(json.dumps(result))  # statuses only, no licensed dates or prices


if __name__ == '__main__':
    main()
