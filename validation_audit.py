"""Read-only pairing audit; never imports retrospective rows into validation."""
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import datetime, timezone

LIMIT = 6000


def classify(predictions, truths):
    ordered = sorted(truths, key=lambda t: t['quoteAt'])
    times = [datetime.fromisoformat(t['quoteAt']).timestamp() for t in ordered]
    out = []
    for p in predictions:
        row = dict(p)
        at = datetime.fromisoformat(p['quoteAt']).timestamp()
        candidates = ordered[bisect_left(times, at-5):bisect_right(times, at+5)]
        if p['truthAt']:
            reason = 'paired'
        elif not candidates:
            reason = 'no_truth_within_5_seconds'
        elif not any(datetime.fromisoformat(p['receivedAt']) <= datetime.fromisoformat(t['receivedAt'])
                     for t in candidates):
            reason = 'truth_received_before_prediction'
        else:
            reason = 'candidate_not_paired_check_one_use_rule'
        row['pairingState'] = reason
        out.append(row)
    return out


def read_archive(conn):
    # The caller holds the same advisory transaction lock as archive writers.
    now = conn.execute('SELECT now()').fetchone()[0]
    predictions = conn.execute('''SELECT bucket,quote_at,price,reference_at,received_at,truth_at
        FROM bob_future_predictions WHERE received_at>=now()-interval '48 hours'
        ORDER BY received_at DESC,bucket,quote_at LIMIT %s''', (LIMIT+1,)).fetchall()
    truths = conn.execute('''SELECT quote_at,price,received_at FROM bob_future_truths
        WHERE received_at>=now()-interval '48 hours'
        ORDER BY received_at DESC,quote_at LIMIT %s''', (LIMIT+1,)).fetchall()
    truncated = len(predictions)>LIMIT or len(truths)>LIMIT
    ps = [dict(bucket=b,quoteAt=at.isoformat(),price=price,referenceAt=ref.isoformat(),
               receivedAt=received.isoformat(),truthAt=truth.isoformat() if truth else None)
          for b,at,price,ref,received,truth in predictions[:LIMIT]]
    ts = [dict(quoteAt=at.isoformat(),price=price,receivedAt=received.isoformat())
          for at,price,received in truths[:LIMIT]]
    rows = classify(ps,ts)
    return dict(schemaVersion=1,generatedAt=now.astimezone(timezone.utc).isoformat(),
                retentionHours=48,truncated=truncated,maxRowsPerType=LIMIT,
                predictions=rows,truths=ts,pairingStates=dict(Counter(r['pairingState'] for r in rows)),
                maxMatchSeconds=5,isLiveApproval=False,
                limitations=['Source name and original provider envelope are not stored per event.',
                             'Rejected input events are not stored; pairing states describe retained predictions only.',
                             'If truncated, missing candidates may be outside the exported subset.'])
