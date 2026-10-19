"""Bounded read-only operational observations; never invoke repair or trading."""
from datetime import datetime, timezone
import math
import time


def fields(value, keys):
    value = value if isinstance(value, dict) else {}
    out = {}
    for key in keys:
        item = value.get(key)
        if item is None or isinstance(item, bool):
            out[key] = item
        elif isinstance(item, str):
            out[key] = item[:300]
        elif type(item) in (int, float) and math.isfinite(item):
            out[key] = item
    return out


def market_snapshot(live, cached_at, now=None):
    now = time.time() if now is None else now
    live = live if isinstance(live, dict) else {}
    age = now - cached_at if cached_at else None
    bars = (live.get('history') or {}).get('bars_by_tf') or {}
    return {'status': 'unavailable' if not live else 'stale' if age is None or not 0 <= age <= 120 else live.get('status', 'unknown'),
            'cacheAgeSeconds': age, 'cachedAt': cached_at or None,
            'source': fields(live.get('spots'), ('spot_price_as_of', 'primary', 'xaus_is_spot', 'is_genuine_xauusd_spot')),
            'candles': {tf: {'count':len(bars.get(tf, [])),
                            'last': fields(bars[tf][-1], ('openTime','source','instrument')) if bars.get(tf) else None}
                        for tf in ('1m','5m','15m','30m','1h')},
            'scope':'cached-input-diagnostics-not-forecast-quality'}


def collect(readers):
    areas = {}
    for name, reader in readers.items():
        try:
            result = reader()
            areas[name] = result if isinstance(result, dict) else {'status':'unavailable'}
        except Exception:
            # Exception messages can contain URLs, credentials or database values.
            areas[name] = {'status':'unavailable'}
    return {'readOnly':True, 'realOrders':False,
            'observedAt':datetime.now(timezone.utc).isoformat(),
            'status':'partial' if any(a.get('status') == 'unavailable' for a in areas.values()) else 'observed',
            'scope':'operational-observations-not-complete-feature-validation', 'areas':areas}


def push_snapshot(conn, evaluator, paper_health, portfolios):
    """Only SELECT statements; fixed profile table names, no subscriptions or trades returned."""
    accounts = []
    for profile in portfolios.POLICIES:
        table = portfolios.names(profile)['bob_paper_control']
        row = conn.execute(f'SELECT payload FROM {table} WHERE id=1').fetchone()
        accounts.append({'profile':profile, **fields(row[0] if row else {},
            ('enabled','status','checkedAt','startAt'))})
    row = conn.execute('SELECT count(*) FROM subscriptions WHERE general_enabled=TRUE OR (trade_enabled=TRUE AND active_trade=TRUE)').fetchone()
    return {'status':'observed', 'paper':paper_health.snapshot(conn), 'accounts':accounts,
            'push': {'activeMonitors':row[0], 'deliveryStatus':'not-verified',
                     'evaluator':fields(evaluator.status(), ('status','ready','running','lastSuccessAt'))}}
