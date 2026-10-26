"""Frozen forward observations, never a signal override or broker return.

Only snapshots captured at write time enter the comparison. Historic records
without this protocol are not backfilled. Sampling precedes outcome inspection.
"""
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = 'optimization-forward-v1'
VALIDATION_DAY = '2026-10-26'
HORIZON = 15
STRONG_MOVE_PCT = .15
LABELS = {'baseline': 'Aktuelle Regel', 'cautious': 'Vorsichtige Bestätigung',
          'early': 'Frühimpuls ergänzend', 'regime': 'Trendabhängiger Frühimpuls'}


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def capture(r):
    trend = r.get('trendContext') or {}
    regime = (trend.get('phase') if trend.get('available') is True else None)
    regime = regime if regime in ('CONTINUATION', 'PULLBACK', 'RANGE', 'WEAKENING') else 'UNKNOWN'
    early = r.get('earlyImpulse') or {}
    base = r.get('direction')
    stamp = early.get('barAt')
    valid_early = (early.get('available') is True and number(stamp)
                   and 0 <= r['recordedAt']-stamp <= 600000)
    candidate = base if base in ('LONG', 'SHORT') else early.get('direction') if valid_early else None
    adaptive = (candidate if trend.get('intact') is True and
                trend.get('direction') == candidate and regime in ('CONTINUATION', 'PULLBACK')
                else 'NEUTRAL' if regime != 'UNKNOWN' else None)
    return dict(version=VERSION, validationDay=VALIDATION_DAY, regime=regime,
                variants=dict(baseline=base, cautious=r.get('shadowDirection'),
                              early=candidate, regime=adaptive),
                reason=str(r.get('reason') or 'Kein Entscheidungsgrund gespeichert')[:350],
                blockers=[str(x)[:200] for x in (r.get('gateReasons') or [])[:5]],
                automaticRuleChange=False)


def _stats():
    return dict(cases=0, signals=0, wait=0, wins=0, losses=0, grossSumPct=0.,
                netModelSumPct=0., winSumPct=0., lossSumPct=0., missing=0)


def report(rows, score, now=None):
    now = time.time()*1000 if now is None else now
    ordered = sorted((r for r, _ in rows if r.get('origin') == 'background'),
                     key=lambda r: r['recordedAt'])
    phases = {phase: {key: _stats() for key in LABELS} for phase in ('collection', 'validation')}
    regimes = {}; missed = []; reasons = {}; paired = 0; pending = 0; missing = 0
    sampled = 0; last = None; start = None; end = None
    # 2 bps each side is a disclosed reference-instrument stress assumption,
    # not a product/broker fee. Product costs are evaluated separately.
    cost_pct = .04
    for r, truths in sorted(rows, key=lambda row: row[0]['recordedAt']):
        frozen = r.get('optimization') or {}
        if r.get('origin') != 'background' or frozen.get('version') != VERSION:
            continue
        at = r['recordedAt']
        if last is not None and at-last < HORIZON*60000+60000:
            continue
        last = at; sampled += 1
        start = at if start is None else start; end = at
        phase = ('validation' if datetime.fromtimestamp(at/1000, ZoneInfo('Europe/Zurich')).date().isoformat()
                 >= VALIDATION_DAY else 'collection')
        values = frozen['variants']
        result = score(r, truths[0] if truths else None, HORIZON)
        if result:
            change = result['changePct']
            direction = 'LONG' if change > 0 else 'SHORT'
            if abs(change) >= STRONG_MOVE_PCT and (values['baseline'] != direction or frozen['blockers']):
                # Only describe logged evidence, never infer the true start of a move.
                later = next((x for x in ordered if at < x['recordedAt'] <= at+HORIZON*60000
                              and x.get('marketEvaluable') and x.get('direction') == direction), None)
                reason = '; '.join(frozen['blockers']) or frozen['reason']
                reasons[reason] = reasons.get(reason, 0)+1
                missed.append(dict(at=at, direction=direction, changePct=change, reason=reason,
                    baseline=values['baseline'], regime=frozen['regime'],
                    signalAlreadyPresent=values['baseline'] == direction,
                    laterSignalMinutes=(later['recordedAt']-at)/60000 if later else None))
        # Use a common cohort for every strategy, including unavailable inputs.
        if not result or any(values.get(k) not in ('LONG', 'SHORT', 'NEUTRAL') for k in LABELS):
            if now < at+HORIZON*60000: pending += 1
            else: missing += 1
            for m in phases[phase].values(): m['missing'] += 1
            continue
        paired += 1
        change = result['changePct']
        group = regimes.setdefault((phase, frozen['regime']), dict(cases=0, baselineSumPct=0., regimeSumPct=0.))
        group['cases'] += 1
        for key in LABELS:
            d = values[key]; m = phases[phase][key]; m['cases'] += 1
            gross = change if d == 'LONG' else -change if d == 'SHORT' else 0.
            net = gross-cost_pct if d != 'NEUTRAL' else 0.
            m['grossSumPct'] += gross; m['netModelSumPct'] += net
            if d == 'NEUTRAL': m['wait'] += 1
            else:
                m['signals'] += 1
                m['wins'] += net > 0; m['losses'] += net < 0
                m['winSumPct'] += max(0., net); m['lossSumPct'] += min(0., net)
            if key in ('baseline', 'regime'): group[key+'SumPct'] += net
    for variants in phases.values():
        for m in variants.values():
            m['meanModelPct'] = m['netModelSumPct']/m['cases'] if m['cases'] else None
            m['averageWinPct'] = m['winSumPct']/m['wins'] if m['wins'] else None
            m['averageLossPct'] = m['lossSumPct']/m['losses'] if m['losses'] else None
            m['losingSignalRate'] = m['losses']/m['signals'] if m['signals'] else None
            baseline = variants['baseline']
            m['netModelDeltaVsBaselinePct'] = m['netModelSumPct']-baseline['netModelSumPct'] if m['cases'] else None
    return dict(version=VERSION, labels=LABELS, phases=phases, validationDay=VALIDATION_DAY,
        sampled=sampled, paired=paired, missing=missing, pending=pending, rangeStart=start, rangeEnd=end,
        regimes=[dict(phase=p, regime=g, **m) for (p,g),m in regimes.items()],
        missedCount=len(missed), missed=missed[-15:], blockers=reasons,
        horizonMinutes=HORIZON, strongMovePct=STRONG_MOVE_PCT, referenceRoundTripCostPct=cost_pct,
        automaticRuleChange=False, productNetValidated=False,
        note='Ab Aktivierung eingefrorene Hintergrundentscheidungen; mindestens 16 Minuten Abstand. '
             'Gemeinsamer 15-Minuten-Spotvergleich; Abwarten = 0. Beispielkosten 0,04 % je Richtungstrade, '
             'keine Produkt-/Kontorendite. Starke Bewegung ab 0,15 % nur rückblickend erkannt; '
             'protokollierter Blocker ist kein Beweis für eine falsche Sperre. '
             'Auswertung des angezeigten rollierenden Berichtsfensters, kein vollständiges Langzeitarchiv. '
             'Keine automatische Übernahme oder Gewinnzusage.')
