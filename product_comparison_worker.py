"""Unattended original bid/model comparisons; no orders or stop modifications."""
import json
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import product_trade_history as history

_lock = threading.Lock()
_last = 0
FIELDS = ('isin','currency','direction','ratio','strike','ko','bid','goldReference','fxReference','referenceAt')


def model_key(product):
    return ['model-v2'] + [product.get(k) for k in FIELDS]


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_trade_comparisons (
        trade_id TEXT NOT NULL REFERENCES bob_real_trades(id) ON DELETE CASCADE,
        model_key JSONB NOT NULL, quote_at TIMESTAMPTZ NOT NULL,
        source TEXT NOT NULL, evidence JSONB NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(trade_id,model_key,quote_at,source))''')


def comparison(product, spots, quote, now=None):
    now = now or datetime.now(timezone.utc)
    point = history.calculate(product, spots, now)
    if not point or not isinstance(quote, dict):return None
    if (quote.get('isin') != product['isin'] or quote.get('productVerified') is not True
        or quote.get('found') is not True or quote.get('fresh') is not True
        or quote.get('currency') != product['currency']
        or quote.get('priceKind') in ('issuer-chart','calculated-turbo','calculated')
        or quote.get('currencyConversion') or quote.get('delayed') or quote.get('sourceFailure')
        or not history.pos(quote.get('bid')) or not history.pos(quote.get('ask'))
        or quote['ask'] < quote['bid']):return None
    at = history.clock(quote.get('bidAt'))
    ask_at = history.clock(quote.get('askAt'))
    if not at or not ask_at:return None
    if any(not 0 <= (now-t).total_seconds() <= 90 for t in (at,ask_at)):return None
    if any(abs((at-history.clock(point[k])).total_seconds()) > 30 for k in ('spotAt','fxAt')):return None
    source = str(quote.get('source') or '')[:200]
    if not source:return None
    return dict(at=int(at.timestamp()*1000),quoted=quote['bid'],estimated=point['price'],
                currency=product['currency'],source=source,kind='issuer',side='bid',
                spotAt=point['spotAt'],fxAt=point['fxAt'],gold=point['gold'],koDistancePct=point['koDistancePct'])


def read(conn, trade_id):
    rows = conn.execute('''SELECT model_key,evidence FROM bob_trade_comparisons
        WHERE trade_id=%s AND quote_at>=now()-interval '1 day'
        ORDER BY quote_at DESC LIMIT 3000''',(trade_id,)).fetchall()
    return [dict(row,modelKey=key) for key,row in reversed(rows)]


def tick(db, bundle, quote_fetch=None, now=None):
    from product_quotes import get_quote
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo('Europe/Zurich'))
    if local.weekday() >= 5 or not 8 <= local.hour < 22:return
    with db() as conn:
        trades = conn.execute('SELECT id,settings FROM bob_real_trades WHERE active=TRUE').fetchall()
    import product_list_study
    fetched={}
    def fetch(isin):
        if isin not in fetched:
            fetched[isin]=(quote_fetch or get_quote)(isin)
            try:
                import product_precision, metric_quality
                with db() as conn:
                    product_precision.observe(conn,fetched[isin],bundle.get('spots'),now.timestamp()*1000)
                    metric_quality.product_check(conn,fetched[isin],now.timestamp()*1000)
                    conn.commit()
            except Exception as exc:print('BOB_METRIC_PRODUCT error='+type(exc).__name__,flush=True)
        return fetched[isin]
    try:
        product_list_study.tick(db,bundle,fetch,now)
    except Exception as exc:
        # A list-read failure must not cancel independent active-trade studies.
        print('BOB_LIST_PRICE_STUDY error='+type(exc).__name__,flush=True)
    for tid,settings in trades:
        product = (settings.get('trade') or {}).get('product')
        if not history.calculate(product,bundle.get('spots'),now):continue
        # Provider I/O stays outside transactions and the notification worker.
        try: quote = fetch(product['isin'])
        except Exception:continue
        row = comparison(product,bundle.get('spots'),quote,now)
        if not row:continue
        with db() as conn:
            current = conn.execute('SELECT settings,state FROM bob_real_trades WHERE id=%s AND active=TRUE FOR UPDATE',(tid,)).fetchone()
            if not current or model_key((current[0].get('trade') or {}).get('product') or {}) != model_key(product):continue
            # Research evidence has no automatic age-based expiry.
            conn.execute('''INSERT INTO bob_trade_comparisons(trade_id,model_key,quote_at,source,evidence)
                VALUES(%s,%s::jsonb,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
                (tid,json.dumps(model_key(product)),history.clock(quote['bidAt']),row['source'],json.dumps(row)))
            import precision_learning, metric_quality
            precision_learning.observe(conn,dict(product,_precisionScope=tid+':'+json.dumps(model_key(product))),row)
            metric_quality.pnl_check(conn,tid,product,row,now.timestamp()*1000)
            conn.commit()
        # Research failure cannot roll back the established quote/precision capture.
        try:
            import exit_quality
            trade=dict(current[0].get('trade') or {})
            plan=(current[1] or {}).get('trade') or {}
            if plan.get('tradeId')==trade.get('tradeId'):
                for key in ('stop','target'):
                    if history.pos(plan.get(key)):trade[key]=plan[key]
            with db() as study_conn:
                exit_quality.observe(study_conn,tid,trade,dict(row,askAt=quote.get('askAt')),
                    history.calculate(product,bundle.get('spots'),now) or {},
                    quote.get('ask'),max(int(now.timestamp()*1000),int(time.time()*1000)))
                study_conn.commit()
        except Exception as exc:print('BOB_EXIT_QUALITY error='+type(exc).__name__,flush=True)


def enqueue(db,bundle):
    global _last
    if time.monotonic()-_last<28 or not _lock.acquire(blocking=False):return
    _last=time.monotonic()
    def run():
        try:tick(db,bundle)
        except Exception as exc:print('BOB_PRODUCT_COMPARISON error='+type(exc).__name__,flush=True)
        finally:_lock.release()
    try:
        threading.Thread(target=run,name='bob-product-comparison',daemon=True).start()
    except Exception as exc:
        # No thread exists to execute finally: release admission for the next bundle.
        _last=0
        _lock.release()
        print('BOB_PRODUCT_COMPARISON start_error='+type(exc).__name__,flush=True)
