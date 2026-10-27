"""Bounded, read-only comparison evidence; sampled cases are not finished studies."""
import math
import time
from collections import Counter
from decimal import Decimal

LIMIT = 100
# Each query returns only (observation clock in ms, outcome label). No identities,
# prices, private payloads, credentials, or mutable control calls are exported.
QUERIES = {
 'signals': """SELECT extract(epoch FROM recorded_at)*1000,
    CASE WHEN payload->>'marketEvaluable'='true' THEN 'eligible' ELSE 'not-evaluable' END
    FROM bob_decision_audit ORDER BY recorded_at DESC LIMIT 101""",
 'signal-outcomes': """SELECT extract(epoch FROM a.recorded_at)*1000,
    CASE WHEN EXISTS (SELECT 1 FROM bob_decision_outcomes o WHERE o.decision_id=a.id AND o.horizon=60)
    THEN 'outcome-recorded' ELSE 'outcome-not-recorded' END
    FROM bob_decision_audit a ORDER BY a.recorded_at DESC LIMIT 101""",
 'improvement-trials': """SELECT slot, CASE WHEN outcome IS NOT NULL THEN 'outcome-recorded' ELSE 'outcome-not-recorded' END
    FROM bob_improvement_trials WHERE campaign=%s ORDER BY slot DESC LIMIT 101""",
 'list-price-pairs': """SELECT extract(epoch FROM quote_at)*1000,'paired-observation'
    FROM bob_list_price_pairs ORDER BY quote_at DESC LIMIT 101""",
 'three-stop-study': """SELECT NULL, CASE WHEN complete THEN 'terminal-not-necessarily-comparable' ELSE 'pending' END
    FROM bob_paper_stop_studies ORDER BY id LIMIT 101""",
 'stop-target-cases': """SELECT extract(epoch FROM checked_at)*1000,
    CASE WHEN complete THEN 'terminal-not-necessarily-comparable' ELSE 'pending' END
    FROM bob_stop_target_tests ORDER BY started_at DESC LIMIT 101""",
 'legacy-fast-cautious': """SELECT slot, CASE WHEN truth IS NOT NULL THEN 'outcome-recorded' ELSE 'outcome-not-recorded' END
    FROM bob_intraday_comparison WHERE campaign=%s ORDER BY slot DESC LIMIT 101""",
}
LABELS = frozenset(('eligible','not-evaluable','outcome-recorded','outcome-not-recorded',
    'paired-observation','terminal-not-necessarily-comparable','pending','comparable',
    'incomplete','collection','selection','validation','monitoring','cooldown','paused','training'))


def summarize(rows, now):
    counts = Counter()
    clocks = []
    for at, label in rows[:LIMIT]:
        counts[label if label in LABELS else 'unknown'] += 1
        if type(at) in (int, float, Decimal):
            value = float(at)
            if math.isfinite(value) and 0 < value <= now:
                clocks.append(value)
    latest = max(clocks) if clocks else None
    return dict(status='observed' if rows else 'no-records', sampledRecords=min(len(rows),LIMIT),
        truncated=len(rows)>LIMIT, counts=dict(counts), latestSampleAt=latest,
        latestSampleAgeSeconds=round((now-latest)/1000,1) if latest else None,
        continuousExecutionVerified=False, studyCompletedVerified=False)


def report(conn, now=None):
    import improvement_tracker
    import intraday_comparison
    import background_push
    now = time.time()*1000 if now is None else now
    queries = dict(QUERIES)
    for currency in ('EUR','CHF'):
        # Literal allowlist only; never interpolate request input.
        queries['ranking-'+currency] = """SELECT slot, CASE WHEN outcome->>'complete'='true'
            THEN 'comparable' WHEN outcome IS NULL THEN 'pending' ELSE 'incomplete' END
            FROM bob_ranking_samples WHERE currency='"""+currency+"' ORDER BY slot DESC LIMIT 101"
        queries['ranking-exits-'+currency] = """SELECT checked_at, CASE WHEN result->>'complete'='true'
            THEN 'comparable' WHEN complete THEN 'incomplete' ELSE 'pending' END
            FROM bob_ranking_lifecycles WHERE currency='"""+currency+"' ORDER BY slot DESC LIMIT 101"
    queries['entry-filter-state'] = """SELECT NULL,state->>'phase' FROM bob_rule_learning
        WHERE id='entry-filter-v2-guarded' LIMIT 1"""
    queries['price-correction-states'] = """SELECT state->'lastAt',state->>'phase'
        FROM bob_precision_learning ORDER BY id LIMIT 101"""
    items = {}
    for name, query in queries.items():
        params = ((improvement_tracker.VERSION,) if name=='improvement-trials' else
                  (intraday_comparison.ID,) if name=='legacy-fast-cautious' else ())
        try:
            with conn.transaction():
                rows = conn.execute(query, params).fetchall()
            items[name] = summarize(rows, now)
        except Exception:
            # A failed probe must not poison the connection or hide other studies.
            items[name] = dict(status='unavailable', reason='comparison-read-failed',
                               studyCompletedVerified=False)
    items['legacy-fast-cautious']['collectionWindowEnded'] = now >= intraday_comparison.END
    items['legacy-fast-cautious']['newCasesExpected'] = intraday_comparison.active(now)
    evaluations = {}
    try:
        with conn.transaction():
            evaluations['fastCautious'] = intraday_comparison.report(conn, now)
    except Exception:
        evaluations['fastCautious'] = dict(status='unavailable')
    try:
        with conn.transaction():
            rows = conn.execute("""SELECT run_day,calculated_at,status,version,fingerprint
                FROM bob_strategy_lab_revisions ORDER BY run_day DESC,calculated_at DESC
                LIMIT 14""").fetchall()
        evaluations['researchRevisions'] = dict(status='observed' if rows else 'no-records',
            limit=14, items=[dict(day=str(d),calculatedAt=str(at),status=status,
                version=version,fingerprint=fingerprint) for d,at,status,version,fingerprint in rows])
    except Exception:
        evaluations['researchRevisions'] = dict(status='unavailable')
    return dict(storedEvaluations=evaluations, status='partial'  if any(x['status']=='unavailable' for x in items.values()) else 'observed',
        readOnly=True, realOrders=False, observedAt=now, sessionMode=background_push.degiro_session(now),
        sampleLimit=LIMIT, items=items,
        scope='bounded-stored-evidence-not-full-study-completion-or-worker-heartbeat',
        note='Stored outcomes and terminal cases are not verified profitable or completed research studies. '
             'No-records is not success. Latest clocks refer only to the disclosed bounded sample; '
             'three-stop and correction samples are in ID order, not recency order.')
