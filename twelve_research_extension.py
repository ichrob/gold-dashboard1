"""Research-only Twelve Data expansion: no UI, trading, paid upgrades or live feed.

The existing gold_fallback.py remains the verified single-hour probe.
Additional scopes are disabled until individually licensed and confirmed.
"""
import argparse
import hashlib
import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener

INTERVAL_MS = {'1min': 60000, '5min': 300000, '15min': 900000,
               '30min': 1800000, '1h': 3600000, '1day': 86400000}
SYMBOLS = frozenset(('XAU/USD', 'CHF/EUR', 'EUR/CHF', 'USD/CHF'))
MAX_BARS = 500
MAX_RESPONSE_BYTES = 512000
MINUTE_BUDGET = 7  # reserve one credit below the published 8
DAY_BUDGET = 700  # 100-credit margin below the published 800


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def scope_allowed(symbol, interval, env=None):
    """Explicit authorization per symbol+interval; exact confirmed hour only by default."""
    env = os.environ if env is None else env
    if env.get('BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED') != '1':
        return False
    if symbol == 'XAU/USD' and interval == '1h':
        return True
    # Tokens are uppercase alphanumerics, never interpolated into shell commands.
    key = 'BOB_TWELVEDATA_SCOPE_' + symbol.replace('/', '_') + '_' + interval.upper()
    return env.get(key) == '1'


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
    if not (start_ms > 0 and start_ms % step == 0 and
            start_ms < end_ms <= now_ms and end_ms % step == 0 and
            0 < (end_ms - start_ms) // step <= MAX_BARS):
        raise ValueError('bounds')
    if not isinstance(payload, dict):
        raise ValueError('payload')
    meta = payload.get('meta')
    if not isinstance(meta, dict) or meta.get('symbol') != symbol or meta.get('interval') != interval:
        raise ValueError('identity')
    zone = meta.get('exchange_timezone')
    if zone != 'UTC':
        # The confirmed precious-metal response omits timezone. This exception
        # requires exact precious-metal identity AND explicit UTC request context.
        metal = (symbol == 'XAU/USD' and 'exchange_timezone' not in meta
                 and meta.get('type') == 'Precious Metal'
                 and meta.get('currency_base') == 'Gold Spot'
                 and meta.get('currency_quote') == 'US Dollar')
        if not metal:
            raise ValueError('timezone')
    values = payload.get('values')
    if not isinstance(values, list) or len(values) > MAX_BARS:
        raise ValueError('bars')
    rows, seen = [], set()
    for bar in values:
        if not isinstance(bar, dict):
            raise ValueError('bar')
        dt = datetime.strptime(bar['datetime'], '%Y-%m-%d %H:%M:%S')
        opened = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        if opened % step or opened in seen:
            raise ValueError('duplicate-or-alignment')
        seen.add(opened)
        if not start_ms <= opened < end_ms:
            raise ValueError('unexpected-time')
        if opened + step > now_ms:
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


def gaps(rows, interval):
    step = INTERVAL_MS[interval]
    out = []
    for left, right in zip(rows, rows[1:]):
        if right['openTime'] - left['openTime'] > step:
            out.append({'startMs':left['openTime'] + step,
                        'endMs':right['openTime'] - step,
                        'sessionStatus':'unverified',
                        'automaticBackfillAllowed':False})
    return out


def research_ema(rows, period=20):
    """Local internal-only derived research; never serve in a dashboard/API."""
    if period < 2 or len(rows) < period:
        return None
    ordered = sorted(rows, key=lambda x: x['openTime'])
    step = INTERVAL_MS[ordered[0]['interval']]
    if any(a['symbol'] != ordered[0]['symbol'] or a['interval'] != ordered[0]['interval']
           or b['openTime'] - a['openTime'] != step for a,b in zip(ordered, ordered[1:])):
        return None
    if any(r.get('researchOnly') is not True for r in ordered):
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
    if not ordered or any(r.get('researchOnly') is not True or
                          r.get('isExecutableQuote') is not False for r in ordered):
        return None
    step = INTERVAL_MS.get(ordered[0]['interval'])
    if not step or any(r['symbol'] != ordered[0]['symbol'] or
                       r['interval'] != ordered[0]['interval'] for r in ordered):
        return None
    if any(b['openTime']-a['openTime'] != step for a,b in zip(ordered,ordered[1:])):
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
    if (not all(type(v) is int for v in (start_ms,end_ms,now_ms))
            or start_ms <= 0 or start_ms % step or end_ms % step
            or end_ms > now_ms or end_ms <= start_ms or (end_ms-start_ms)//step > MAX_BARS):
        return {'code':'INVALID_RANGE'}
    if os.environ.get('BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED') != '1':
        return {'code':'WORKER_COORDINATION_UNCONFIRMED'}
    # BEGIN IMMEDIATE prevents two callers on the same SQLite file from passing quota together.
    # Deployment must use one persistent shared ledger and one worker.
    with db:
        db.execute('BEGIN IMMEDIATE')
        if not reserve_credit(db, now_ms):
            return {'code':'CREDIT_BUDGET_EXHAUSTED'}
    stamp = lambda ms: datetime.fromtimestamp(ms/1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    params = urlencode(dict(symbol=symbol,interval=interval,timezone='UTC',
                            start_date=stamp(start_ms),end_date=stamp(end_ms-step),
                            outputsize=MAX_BARS,apikey=key))
    try:
        client = opener or build_opener(NoRedirect())
        with client.open('https://api.twelvedata.com/time_series?' + params, timeout=10) as response:
            raw = response.read(MAX_RESPONSE_BYTES+1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return {'code':'RESPONSE_TOO_LARGE'}
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get('status') == 'error':
            return {'code':'PROVIDER_REJECTED'}
        rows = validate_rows(payload, symbol, interval, start_ms, end_ms, now_ms)
        with db:
            store_rows(db, rows)
        return {'code':'OBSERVED','stored':len(rows),'missing':len(gaps(rows,interval)),
                'researchOnly':True}
    except HTTPError as exc:
        return {'code':'HTTP_ERROR','httpStatus':exc.code}
    except (URLError, TimeoutError, OSError):
        return {'code':'NETWORK_ERROR'}
    except (KeyError,TypeError,ValueError,OverflowError):
        return {'code':'INVALID_RESPONSE'}
    # Do not log URLs or exceptions: request query contains the secret.


def main():
    parser = argparse.ArgumentParser(description='Isolated Twelve Data research, no live/GUI output')
    parser.add_argument('--symbol', required=True, choices=sorted(SYMBOLS))
    parser.add_argument('--interval', required=True, choices=sorted(INTERVAL_MS))
    parser.add_argument('--start-utc', required=True, help='YYYY-MM-DD HH:MM:SS')
    parser.add_argument('--end-utc', required=True, help='YYYY-MM-DD HH:MM:SS (exclusive)')
    parser.add_argument('--archive', required=True, help='persistent private SQLite, not Render ephemeral disk')
    args = parser.parse_args()
    parse = lambda v: int(datetime.strptime(v,'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()*1000)
    with sqlite3.connect(args.archive,timeout=10,isolation_level=None) as db:
        result = fetch_research(db,args.symbol,args.interval,parse(args.start_utc),parse(args.end_utc))
    print(json.dumps(result))  # statuses only, no proprietary prices


if __name__ == '__main__':
    main()
