"""Separate durable, paired shadow study. No writes to the active model archive."""
import math
from datetime import datetime, timezone

KEY = 'future:GCZ26:spot-cfd-comparison-v1'


def stamp(raw):
    at = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if at.tzinfo is None:raise ValueError('Quellenzeit ohne Zeitzone')
    return at


def checked(event, now=None):
    from bob_validation_store import bucket
    now = now or datetime.now(timezone.utc)
    kind = event.get('type')
    if kind not in ('prediction', 'truth'):raise ValueError('Ungültiger Vergleichstyp')
    at = stamp(event['at'])
    if not 0 <= (now-at).total_seconds() <= (90 if kind == 'prediction' else 1800):
        raise ValueError('Vergleichszeit nicht aktuell')
    keys = ('spot', 'cfd') if kind == 'prediction' else ('value',)
    for key in keys:
        value = event.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Ungültiger Vergleichskurs')
    ref = stamp(event['referenceAt']) if kind == 'prediction' else None
    horizon = bucket((at-ref).total_seconds()) if ref else None
    return kind, at, ref, horizon


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_comparison_predictions (
        quote_at TIMESTAMPTZ PRIMARY KEY, reference_at TIMESTAMPTZ NOT NULL,
        bucket TEXT NOT NULL, spot DOUBLE PRECISION NOT NULL, cfd DOUBLE PRECISION NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        truth_at TIMESTAMPTZ UNIQUE)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_comparison_truths (
        quote_at TIMESTAMPTZ PRIMARY KEY, price DOUBLE PRECISION NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())''')


def summarize(rows, now=None):
    now = now or datetime.now(timezone.utc)
    def group(items):
        n = len(items)
        out = dict(count=n)
        if not n:return out
        # row: target, reference, horizon bucket, spot, cfd, truth, truth time, receipt
        for index, name in ((3, 'spot'), (4, 'cfd')):
            errors = [abs(r[index]-r[5]) for r in items]
            out[name] = dict(mae=sum(errors)/n, maximum=max(errors))
        span = (max(r[0] for r in items)-min(r[0] for r in items)).total_seconds()
        out.update(spanSeconds=span, days=len({r[0].date() for r in items}),
                   latestAt=max(r[6] for r in items).isoformat())
        recent = (now-max(r[7] for r in items)).total_seconds() <= 1800
        out['preliminaryReady'] = n >= 20 and span >= 600 and recent
        # A summary is evidence, never an instruction to select a source.
        out['lowerMeanError'] = ('spot' if out['spot']['mae'] < out['cfd']['mae'] else
                                 'cfd' if out['cfd']['mae'] < out['spot']['mae'] else 'equal')
        return out
    overall = group(rows)
    overall['horizons'] = [dict(bucket=b, **group([r for r in rows if r[2] == b]))
                           for b in ('0–60s', '61–300s', '301–900s', '901–1800s')]
    return overall


def handle(conn, action, payload):
    conn.execute('SELECT pg_advisory_xact_lock(68431027)')
    if action == 'write':
        events = payload.get('events', [])
        if not isinstance(events, list) or len(events) > 4:raise ValueError('Vergleichspaket zu groß')
        values = [(e, checked(e)) for e in events]
        conn.execute("DELETE FROM bob_comparison_predictions WHERE received_at<now()-interval '7 days'")
        conn.execute("DELETE FROM bob_comparison_truths WHERE received_at<now()-interval '7 days'")
        # Truth first: a calculation submitted together with already-known
        # truth must not be retrospectively accepted as a prediction.
        for e, (kind, at, ref, bucket) in sorted(values, key=lambda v: v[1][0] != 'truth'):
            if kind == 'prediction':
                conn.execute('''INSERT INTO bob_comparison_predictions(quote_at,reference_at,bucket,spot,cfd)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(quote_at) DO NOTHING''',
                    (at, ref, bucket, e['spot'], e['cfd']))
            else:
                conn.execute('''INSERT INTO bob_comparison_truths(quote_at,price) VALUES(%s,%s)
                    ON CONFLICT(quote_at) DO NOTHING''', (at, e['value']))
                actual = conn.execute('SELECT price FROM bob_comparison_truths WHERE quote_at=%s', (at,)).fetchone()
                if actual[0] != e['value']:raise ValueError('Widersprüchliche GCZ26-Referenz')
        for e, (kind, at, _, _) in values:
            if kind != 'truth':continue
            receipt = conn.execute('SELECT received_at FROM bob_comparison_truths WHERE quote_at=%s', (at,)).fetchone()[0]
            if conn.execute('SELECT 1 FROM bob_comparison_predictions WHERE truth_at=%s', (at,)).fetchone():continue
            row = conn.execute('''SELECT quote_at FROM bob_comparison_predictions WHERE truth_at IS NULL
                AND received_at<%s AND quote_at BETWEEN %s-interval '5 seconds' AND %s+interval '5 seconds'
                AND reference_at<%s-interval '5 seconds'
                ORDER BY abs(extract(epoch FROM quote_at-%s)),quote_at LIMIT 1''', (receipt, at, at, at, at)).fetchone()
            if row:conn.execute('UPDATE bob_comparison_predictions SET truth_at=%s WHERE quote_at=%s', (at, row[0]))
    rows = conn.execute('''SELECT p.quote_at,p.reference_at,p.bucket,p.spot,p.cfd,t.price,t.quote_at,t.received_at
        FROM bob_comparison_predictions p JOIN bob_comparison_truths t ON p.truth_at=t.quote_at
        WHERE t.received_at>=now()-interval '7 days' ORDER BY p.quote_at DESC LIMIT 20160''').fetchall()
    counts = conn.execute('''SELECT
        (SELECT count(*) FROM bob_comparison_predictions WHERE received_at>=now()-interval '7 days'),
        (SELECT count(*) FROM bob_comparison_truths WHERE received_at>=now()-interval '7 days')''').fetchone()
    return dict(ok=True, key=KEY, summary=summarize(rows), predictionCount=counts[0], truthCount=counts[1])
