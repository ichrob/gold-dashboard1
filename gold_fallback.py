"""Opt-in XAU/USD research archive. Never splices candles into the live feed."""
import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

SOURCE = 'twelvedata'
SYMBOL = 'XAU/USD'
HOUR = 3600000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def hour(value):
    if type(value) is not int or value <= 0 or value % HOUR:
        raise ValueError('Expected UTC hour in milliseconds')
    return value


def normalize(payload, target, now_ms, *, requested_timezone=None):
    """Reject the entire response on ambiguity; timestamps are candle opens."""
    hour(target)
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError('Invalid observation time')
    if target + HOUR > now_ms:
        raise ValueError('Candle not closed')
    meta = payload.get('meta', {}) if isinstance(payload, dict) else {}
    if not isinstance(meta, dict):
        raise ValueError('Invalid metadata')
    zone = meta.get('exchange_timezone')
    # Precious-metal responses omit exchange_timezone. Only the fetch boundary
    # can attest to the UTC request; never assume UTC for arbitrary imports.
    utc_request = (zone is None and 'exchange_timezone' not in meta
                   and requested_timezone == 'UTC'
                   and meta.get('type') == 'Precious Metal'
                   and meta.get('currency_base') == 'Gold Spot'
                   and meta.get('currency_quote') == 'US Dollar')
    if (meta.get('symbol') != SYMBOL or meta.get('interval') != '1h'
            or not (zone == 'UTC' or utc_request)):
        raise ValueError('Unexpected instrument, interval or timezone')
    values = payload.get('values')
    if not isinstance(values, list) or len(values) > 5:
        raise ValueError('Unexpected response size')
    seen = set()
    result = None
    for row in values:
        stamp = datetime.strptime(row['datetime'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        ts = hour(int(stamp.timestamp()*1000))
        if ts in seen:
            raise ValueError('Duplicate candle')
        seen.add(ts)
        prices = []
        for field in ('open', 'high', 'low', 'close'):
            value = row[field]
            if isinstance(value, bool):
                raise ValueError('Invalid price')
            number = float(value)
            if not math.isfinite(number) or number <= 0:
                raise ValueError('Invalid price')
            prices.append(number)
        o, h, low, c = prices
        if low > min(o, c) or h < max(o, c):
            raise ValueError('Invalid OHLC bounds')
        if ts == target:
            result = dict(source=SOURCE, symbol=SYMBOL, interval='1h', openTime=ts,
                          open=o, high=h, low=low, close=c, volume=None,
                          fetchedAt=now_ms, researchOnly=True, isExecutableQuote=False)
    return result


def fetch_hour(target, *, now_ms=None):
    """One manual probe, no retries. Never infer entitlement from an HTTP 200."""
    hour(target)
    now_ms = int(datetime.now(timezone.utc).timestamp()*1000) if now_ms is None else now_ms
    if target + HOUR > now_ms:
        return {'code': 'CANDLE_NOT_CLOSED'}
    if os.getenv('BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED') != '1':
        return {'code': 'FREE_ACCESS_UNCONFIRMED'}
    key = os.getenv('TWELVEDATA_API_KEY', '').strip()
    if not key or key.lower() in ('demo', 'your_api_key', 'ihr_twelvedata_api_key'):
        return {'code': 'KEY_NOT_CONFIGURED'}
    fmt = lambda t: datetime.fromtimestamp(t/1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    params = dict(symbol=SYMBOL, interval='1h', timezone='UTC',
                  start_date=fmt(target), end_date=fmt(target+HOUR), apikey=key)
    try:
        with build_opener(NoRedirect()).open('https://api.twelvedata.com/time_series?'+urlencode(params), timeout=10) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                return {'code': 'RESPONSE_TOO_LARGE'}
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get('status') == 'error':
            return {'code': 'PROVIDER_REJECTED'}
        row = normalize(payload, target, now_ms, requested_timezone=params['timezone'])
        return {'code': 'OBSERVED' if row else 'CANDLE_NOT_RETURNED', 'candle': row}
    except HTTPError as error:
        return {'code': 'HTTP_ERROR', 'httpStatus': error.code}
    except (URLError, TimeoutError, OSError):
        return {'code': 'NETWORK_ERROR'}
    except (ValueError, TypeError, KeyError, OverflowError):
        return {'code': 'INVALID_RESPONSE'}
    # Never log exceptions/URLs: the query contains the API key.


def archive(connection, row):
    """Caller-owned SQLite transaction; immutable revisions, no silent overwrite."""
    if (not isinstance(row, dict) or row.get('source') != SOURCE or row.get('symbol') != SYMBOL
            or row.get('interval') != '1h' or row.get('researchOnly') is not True
            or row.get('isExecutableQuote') is not False):
        raise ValueError('Invalid provenance')
    target = hour(row['openTime'])
    canonical = normalize({'meta': {'symbol': SYMBOL, 'interval': '1h', 'exchange_timezone': 'UTC'},
                          'values': [{**row, 'datetime': datetime.fromtimestamp(target/1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}]}, target, row['fetchedAt'])
    prices = [canonical[k] for k in ('open', 'high', 'low', 'close')]
    digest = hashlib.sha256(json.dumps(prices, separators=(',', ':')).encode()).hexdigest()
    connection.execute('''CREATE TABLE IF NOT EXISTS gold_fallback_observations (
        source TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT NOT NULL,
        open_time INTEGER NOT NULL, revision TEXT NOT NULL,
        open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
        volume REAL, first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL,
        PRIMARY KEY (source, symbol, interval, open_time, revision))''')
    connection.execute('''INSERT INTO gold_fallback_observations VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?)
        ON CONFLICT(source,symbol,interval,open_time,revision)
        DO UPDATE SET last_seen=MAX(last_seen,excluded.last_seen)''',
        (SOURCE, SYMBOL, '1h', target, digest, *prices, row['fetchedAt'], row['fetchedAt']))
    return digest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--utc-hour-ms', type=int, required=True)
    parser.add_argument('--archive', help='Explicit persistent SQLite path; never the live candle store')
    args = parser.parse_args()
    result = fetch_hour(args.utc_hour_ms)
    if result.get('candle') and args.archive:
        with sqlite3.connect(args.archive) as db:
            archive(db, result['candle'])
        result['archived'] = True
    print(json.dumps(result))
