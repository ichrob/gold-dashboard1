"""Durable prospective product calibration, isolated by full model identity/side."""
import hashlib
import json
import re
import threading
import time
import os
from datetime import datetime, timezone

_lock = threading.Lock()
_queue = []
_thread = None
_states = {}


def key(model, side, family='hybrid'):
    import product_estimate
    if side not in ('bid', 'ask') or family not in ('hybrid', 'turbo', 'turbo-forward'):
        raise ValueError('Ungültige Messidentität')
    identity = json.dumps(product_estimate.identity(model), separators=(',', ':'))
    return 'product:' + family + ':' + hashlib.sha256(identity.encode()).hexdigest() + ':' + side


def valid_key(value):
    return isinstance(value, str) and re.fullmatch(r'product:(hybrid|turbo|turbo-forward):[0-9a-f]{64}:(bid|ask)', value) is not None


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_product_predictions (
        key TEXT NOT NULL, bucket TEXT NOT NULL, quote_at TIMESTAMPTZ NOT NULL,
        price DOUBLE PRECISION NOT NULL, reference_at TIMESTAMPTZ NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), truth_at TIMESTAMPTZ,
        PRIMARY KEY(key,bucket,quote_at))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_product_truths (
        key TEXT NOT NULL, quote_at TIMESTAMPTZ NOT NULL, price DOUBLE PRECISION NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(key,quote_at))''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_product_pair_idx ON bob_product_predictions(key,bucket,truth_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_product_prediction_retention ON bob_product_predictions(received_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_product_truth_retention ON bob_product_truths(received_at)')


def checked(e, identity, now=None):
    import bob_validation_store as store
    if not valid_key(identity) or e.get('key') != identity:
        raise ValueError('Produktidentität nicht bestätigt')
    return store.event(dict(e, key=store.KEY), now)


def handle(conn, action, payload):
    identity = payload.get('key')
    if not valid_key(identity) or action not in ('read', 'write'):
        raise ValueError('Ungültiger Produktvergleich')
    if action == 'write':
        events = payload.get('events')
        if not isinstance(events, list) or len(events) > 40:
            raise ValueError('Ungültiges Messpaket')
        values = [checked(e, identity) for e in events]
        # One writer per product/side; no cross-product pairing.
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (identity,))
        # Research evidence has no automatic age-based expiry.
        for kind, at, value, ref, horizon in values:
            if kind == 'prediction':
                conn.execute('''INSERT INTO bob_product_predictions(key,bucket,quote_at,price,reference_at)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''', (identity,horizon,at,value,ref))
            else:
                conn.execute('''INSERT INTO bob_product_truths(key,quote_at,price) VALUES(%s,%s,%s)
                    ON CONFLICT DO NOTHING''', (identity,at,value))
                actual = conn.execute('SELECT price FROM bob_product_truths WHERE key=%s AND quote_at=%s', (identity,at)).fetchone()
                if not actual or actual[0] != value:
                    raise ValueError('Widersprüchlicher Produkt-Zeitstempel')
        for at in sorted({at for kind,at,*_ in values if kind == 'truth'}):
            received = conn.execute('SELECT received_at FROM bob_product_truths WHERE key=%s AND quote_at=%s', (identity,at)).fetchone()[0]
            for horizon in ('0–60s','61–300s','301–900s','901–1800s'):
                if conn.execute('SELECT 1 FROM bob_product_predictions WHERE key=%s AND bucket=%s AND truth_at=%s', (identity,horizon,at)).fetchone():
                    continue
                row = conn.execute('''SELECT quote_at FROM bob_product_predictions
                    WHERE key=%s AND bucket=%s AND truth_at IS NULL AND received_at<%s
                    AND quote_at BETWEEN %s-interval '5 seconds' AND %s+interval '5 seconds'
                    ORDER BY abs(extract(epoch FROM quote_at-%s)),quote_at LIMIT 1''', (identity,horizon,received,at,at,at)).fetchone()
                if row:
                    conn.execute('UPDATE bob_product_predictions SET truth_at=%s WHERE key=%s AND bucket=%s AND quote_at=%s', (at,identity,horizon,row[0]))
    rows = conn.execute('''SELECT p.bucket,p.quote_at,p.price,p.reference_at,p.received_at,t.quote_at,t.price,t.received_at
        FROM bob_product_predictions p JOIN bob_product_truths t ON p.key=t.key AND p.truth_at=t.quote_at
        WHERE p.key=%s AND t.received_at>=now()-interval '7 days'
        ORDER BY t.received_at DESC LIMIT 40320''', (identity,)).fetchall()
    pairs = [dict(bucket=b,predictionAt=a.isoformat(),prediction=v,referenceAt=r.isoformat(),
        predictionReceivedAt=c.isoformat(),truthAt=ta.isoformat(),truth=tv,truthReceivedAt=tr.isoformat())
        for b,a,v,r,c,ta,tv,tr in reversed(rows)]
    return dict(ok=True,key=identity,pairs=pairs)


def status(identity):
    with _lock:
        state = _states.get(identity)
    if not state:
        return 'Dauerhafter Produktvergleich wartet auf erste Messung'
    synced, failed = state
    if failed: return 'Messarchiv vorübergehend nicht erreichbar; lokale Messung läuft'
    if synced and time.monotonic()-synced<=120:
        return 'PostgreSQL-Messarchiv synchronisiert; 7 Tage über Neustarts erhalten'
    return 'Messarchiv zuletzt synchronisiert; aktuelle Synchronisierung ausstehend'


def enqueue(identity, kind, value, at, reference_at=None):
    global _thread
    if not valid_key(identity) or not os.environ.get('PUSH_SERVICE_URL') or not os.environ.get('PUSH_SERVICE_TOKEN'):
        return
    event = dict(key=identity,type=kind,value=value,at=at)
    if reference_at is not None: event['referenceAt'] = reference_at
    with _lock:
        _queue.append(event)
        _queue[:] = _queue[-2000:]
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_sync, name='bob-product-validation', daemon=True)
            _thread.start()


def _sync():
    import bob_validation_store as store
    import estimate_quality
    while True:
        with _lock:
            if not _queue:
                global _thread
                _thread = None
                return
            identity = _queue[0]['key']
            batch = [e for e in _queue if e['key'] == identity][:40]
        usable = []
        for e in batch:
            try: checked(e, identity); usable.append(e)
            except (ValueError, TypeError, KeyError): pass
        try:
            result = store.request('write' if usable else 'read', dict(key=identity,events=usable), key=identity)
            estimate_quality.restore_durable(result['pairs'], key=identity)
            with _lock:
                _states[identity] = (time.monotonic(), False)
                ids = {id(e) for e in batch}
                _queue[:] = [e for e in _queue if id(e) not in ids]
        except (OSError, ValueError, TypeError, KeyError):
            with _lock: _states[identity] = (None, True)
            # Old predictions expire instead of being replayed as fresh evidence.
            threading.Event().wait(15)
