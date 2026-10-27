"""Read-only, source-timestamped product MODEL curve for active real trades.

A background Gold/FX model is NOT a DEGIRO quote or executable price.
Never interpolate missing observations and never turn model values into trade approval.
"""
from datetime import datetime, timezone, timedelta
import json
import math
import re


def pos(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0


def clock(raw):
    if not isinstance(raw, str):
        return None
    try:
        t = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except ValueError:
        return None


def calculate(product, spots, now=None):
    """Mirror BobTradeProduct.price without accepting an unverified Gold or FX pair."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(product, dict) or not isinstance(spots, dict):
        return None
    if product.get('simpleSpotTurbo') is not True or product.get('referenceConfirmed') is not True:
        return None
    currency = product.get('currency', 'EUR')
    if currency not in ('EUR', 'CHF') or product.get('direction') not in ('LONG', 'SHORT'):
        return None
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', str(product.get('isin', ''))):
        return None
    fields = ('bid', 'goldReference', 'fxReference', 'ratio', 'strike', 'ko')
    if not all(pos(product.get(k)) for k in fields):
        return None
    spot_time = clock(spots.get('spot_price_as_of'))
    fx = spots.get('usd_chf_meta' if currency == 'CHF' else 'usd_eur_meta') or {}
    fx_time = clock(fx.get('fetchedAt'))
    gold = spots.get('xaus')
    if not (spots.get('is_genuine_xauusd_spot') is True
            and not spots.get('spot_error') and pos(gold)
            and pos(fx.get('rate')) and not fx.get('error')
            and spot_time and fx_time):
        return None
    age_spot = (now-spot_time).total_seconds()
    age_fx = (now-fx_time).total_seconds()
    if not (0 <= age_spot <= 60 and 0 <= age_fx <= 90
            and abs((spot_time-fx_time).total_seconds()) <= 60):
        return None
    d = 1 if product['direction'] == 'LONG' else -1
    if d*(gold-product['ko']) <= 0:
        return None
    rate = fx['rate']
    estimate = product['bid']+d*product['ratio']*(
        (gold-product['strike'])*rate
        -(product['goldReference']-product['strike'])*product['fxReference'])
    if not pos(estimate):
        return None
    return dict(price=round(estimate, 6), currency=currency,
                calculatedAt=now.isoformat(),referenceAt=product.get('referenceAt'),
                method='anchored-gold-fx-turbo',
                basis={k:product.get(k) for k in ('bid','goldReference','fxReference','ratio','strike','ko','direction')},
                calculatedLeverage=round(gold*rate*product['ratio']/estimate,6),
                uncertaintyBound=None,uncertainty='Requires matched original-quote comparisons',
                spotAt=spot_time.isoformat(), fxAt=fx_time.isoformat(),
                gold=gold, fxRate=rate, kind='model',
                source='Bob · Gold/FX-Produktmodell (Hintergrund)',
                provenance='estimated-not-executable',
                koDistancePct=round(abs(gold-product['ko'])/gold*100, 3))


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_real_trade_price_curve (
        trade_id TEXT NOT NULL REFERENCES bob_real_trades(id) ON DELETE CASCADE,
        spot_at TIMESTAMPTZ NOT NULL, fx_at TIMESTAMPTZ NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        price DOUBLE PRECISION NOT NULL, currency TEXT NOT NULL,
        evidence JSONB NOT NULL,
        PRIMARY KEY (trade_id, spot_at, fx_at))''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_trade_curve_time ON bob_real_trade_price_curve(trade_id,spot_at DESC)')


def append(conn, trade_id, product, spots, now=None):
    point = calculate(product, spots, now)
    if not point:
        return False
    # Preserve the evidence behind historical model comparisons.
    conn.execute('''INSERT INTO bob_real_trade_price_curve
        (trade_id,spot_at,fx_at,price,currency,evidence)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT DO NOTHING''',
        (trade_id, point['spotAt'], point['fxAt'], point['price'],
         point['currency'], json.dumps(point)))
    return True


def read(conn, trade_id, limit=400):
    if not isinstance(trade_id, str) or not 1 <= len(trade_id) <= 100:
        raise ValueError('Trade-ID fehlt')
    # No trade in this private account -> no curve. Never reveal other records.
    allowed = conn.execute('SELECT 1 FROM bob_real_trades WHERE id=%s', (trade_id,)).fetchone()
    if not allowed:
        return {'tradeId': trade_id, 'rows': [], 'recording': 'not-found'}
    rows = conn.execute('''SELECT spot_at,recorded_at,price,currency,evidence
        FROM bob_real_trade_price_curve
        WHERE trade_id=%s AND spot_at>=now()-interval '7 days'
        ORDER BY spot_at DESC LIMIT %s''', (trade_id, min(400,max(1,limit)))).fetchall()
    import product_comparison_worker
    import precision_learning
    settings=conn.execute('SELECT settings FROM bob_real_trades WHERE id=%s',(trade_id,)).fetchone()
    product=((settings[0].get('trade') or {}).get('product') or {}) if settings and isinstance(settings[0],dict) else {}
    correction=precision_learning.for_product(conn,dict(product,_precisionScope=trade_id+':'+json.dumps(product_comparison_worker.model_key(product))),datetime.now(timezone.utc).timestamp()*1000)
    correction['modelKey']=product_comparison_worker.model_key(product)
    return {'tradeId':trade_id,
            'automaticCorrection':correction,
            'comparisons':product_comparison_worker.read(conn,trade_id),
            'rows':[dict(at=int(recorded.timestamp()*1000),
                         sourceAt=int(spot.timestamp()*1000),
                         price=price,kind='model',currency=currency,
                         source=(details or {}).get('source','Bob · Gold/FX'),
                         gold=(details or {}).get('gold'),
                         fxAt=(details or {}).get('fxAt'),
                         koDistancePct=(details or {}).get('koDistancePct'),
                         basis=(details or {}).get('basis'),referenceAt=(details or {}).get('referenceAt'),
                         calculatedAt=(details or {}).get('calculatedAt'),method=(details or {}).get('method'),
                         calculatedLeverage=(details or {}).get('calculatedLeverage'),
                         uncertainty=(details or {}).get('uncertainty'),uncertaintyBound=None)
                    for spot,recorded,price,currency,details in reversed(rows)],
            'recording':'server-model-only',
            'note':'Gold/FX-Rechenwerte, keine DEGIRO-Geldkurse oder Ausführungen.'}
