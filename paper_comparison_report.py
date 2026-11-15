"""Read-only, streaming evaluation of stored v1 episodes. Never selects a winner."""
import math
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VERSION = 'entry-exit-v1'
ENTRIES = ('early', 'confirmed', 'pullback')
ARMS = tuple(f'{e}:{x}:{d}' for e in ENTRIES for x in ('fixed', 'trailing') for d in (0, 30, 60))
# Predefined comparisons, not a search for the most profitable combination.
PAIRS = ([(f'{e}:fixed:{d}', f'{e}:trailing:{d}', 'exit') for e in ENTRIES for d in (0, 30, 60)] +
         [(f'{a}:{x}:{d}', f'{b}:{x}:{d}', 'entry') for a, b in (('early', 'confirmed'), ('confirmed', 'pullback')) for x in ('fixed', 'trailing') for d in (0, 30, 60)] +
         [(f'{e}:{x}:0', f'{e}:{x}:{d}', 'delay') for e in ENTRIES for x in ('fixed', 'trailing') for d in (30, 60)])
STATES = ('waiting', 'pending', 'open', 'exit-pending', 'closed', 'inconclusive', 'no-entry', 'invalid')
ZURICH = ZoneInfo('Europe/Zurich')
MAX_EPISODES = 5000


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def day(v):
    if not finite(v) or v <= 0:
        return None
    try:
        return datetime.fromtimestamp(v / 1000, ZURICH).date()
    except (ValueError, OverflowError, OSError):
        return None


def boundary(first):
    """First ten Zurich weekdays from cohort start; never count only profitable days."""
    d = first
    count = 0
    while count < 10:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def metric():
    return dict(n=0, netEur=0., wins=0, losses=0, lossSumEur=0., worstEur=None,
                bestEur=None, sumSquares=0., excursions=0, peakSumEur=0.,
                troughSumEur=0., givebackSumEur=0.)


def add(m, value, arm=None):
    m['n'] += 1
    m['netEur'] += value
    m['wins'] += value > 0
    m['losses'] += value < 0
    m['lossSumEur'] += min(0, value)
    m['sumSquares'] += value * value
    m['worstEur'] = value if m['worstEur'] is None else min(m['worstEur'], value)
    m['bestEur'] = value if m['bestEur'] is None else max(m['bestEur'], value)
    if arm:
        peak, trough = arm.get('observedPeakPnlEur'), arm.get('observedTroughPnlEur')
        if finite(peak) and finite(trough) and peak >= value >= trough:
            m['excursions'] += 1
            m['peakSumEur'] += peak
            m['troughSumEur'] += trough
            m['givebackSumEur'] += peak - value


def finish(m):
    n, ex = m['n'], m['excursions']
    return dict(cases=n, modelNetEur=m['netEur'] if n else None,
                meanEur=m['netEur']/n if n else None,
                wins=m['wins'], losses=m['losses'], flat=n-m['wins']-m['losses'],
                meanLossEur=m['lossSumEur']/m['losses'] if m['losses'] else None,
                worstEur=m['worstEur'], bestEur=m['bestEur'],
                standardDeviationEur=math.sqrt(max(0., (m['sumSquares']-m['netEur']**2/n)/(n-1))) if n > 1 else None,
                excursionCases=ex, meanObservedPeakEur=m['peakSumEur']/ex if ex else None,
                meanObservedTroughEur=m['troughSumEur']/ex if ex else None,
                meanGivebackEur=m['givebackSumEur']/ex if ex else None)


def valid_closed(a):
    return (a.get('status') == 'closed' and finite(a.get('modelNetEur')) and
            all(finite(a.get(k)) and a[k] > 0 for k in ('entryAt', 'exitAt', 'entryQuoteAt', 'exitQuoteAt', 'entryAsk', 'exitBid', 'entryDebit', 'units')) and
            a['exitAt'] >= a['entryAt'] and a['exitQuoteAt'] >= a['entryQuoteAt'] and
            isinstance(a.get('isin'), str) and bool(a['isin']))


def same_entry(a, b):
    return all(a.get(k) == b.get(k) for k in ('isin', 'entryQuoteAt', 'entryAsk', 'units', 'entryDebit', 'entryAt'))


def new_group(rule, phase, trend):
    return dict(ruleVersion=rule, phase=phase, trend=trend, episodes=0,
                variants={k: dict(states={s:0 for s in STATES}, metric=metric()) for k in ARMS},
                pairs={f'{a}|{b}': dict(a=a,b=b,kind=kind,metric=metric(),aMetric=metric(),bMetric=metric(),
                    excluded=0,differentProducts=0,entryMismatch=0) for a,b,kind in PAIRS})


def build(rows, starts, deadline=None):
    groups, total, invalid, checked = {}, 0, 0, None
    for s in rows:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError('comparison-report-budget')
        total += 1
        rule = s.get('ruleVersion')
        date = day(s.get('startedAt'))
        first = starts.get(rule)
        if s.get('version') != VERSION or not isinstance(rule, str) or not date or not first or date < first:
            invalid += 1
            continue
        phase = 'exploration' if date < boundary(first) else 'validation'
        trend = s.get('trend') if s.get('trend') in ('strong-trend','sideways','transition') else 'unknown'
        if finite(s.get('checkedAt')):
            checked = max(checked or 0, s['checkedAt'])
        arms = s.get('arms') or {}
        for label in ('all', trend):
            key = (rule, phase, label)
            if key not in groups:
                if len(groups) >= 80:
                    raise ValueError('comparison-cohort-limit')
                groups[key] = new_group(*key)
            g = groups[key]
            g['episodes'] += 1
            for name, v in g['variants'].items():
                arm = arms.get(name) or {}
                state = arm.get('status')
                if state not in STATES or state == 'closed' and not valid_closed(arm):
                    state = 'invalid'
                v['states'][state] += 1
                if state == 'closed':
                    add(v['metric'], arm['modelNetEur'], arm)
            for p in g['pairs'].values():
                a, b = arms.get(p['a']) or {}, arms.get(p['b']) or {}
                if not valid_closed(a) or not valid_closed(b):
                    p['excluded'] += 1
                    continue
                if p['kind'] == 'exit' and not same_entry(a, b):
                    p['excluded'] += 1
                    p['entryMismatch'] += 1
                    continue
                p['differentProducts'] += a['isin'] != b['isin']
                add(p['metric'], b['modelNetEur'] - a['modelNetEur'])
                add(p['aMetric'], a['modelNetEur'], a)
                add(p['bMetric'], b['modelNetEur'], b)
    output = []
    for key in sorted(groups):
        g = groups[key]
        output.append(dict(ruleVersion=g['ruleVersion'],phase=g['phase'],trend=g['trend'],episodes=g['episodes'],
            variants={k:dict(states=v['states'],**finish(v['metric'])) for k,v in g['variants'].items()},
            comparisons=[dict(a=p['a'],b=p['b'],kind=p['kind'],excluded=p['excluded'],entryMismatch=p['entryMismatch'],
                differentProducts=p['differentProducts'],difference=finish(p['metric']),
                baseline=finish(p['aMetric']),candidate=finish(p['bMetric']),
                evidence='insufficient' if p['metric']['n'] < 100 else 'review-required') for p in g['pairs'].values()]))
    return dict(version=1,status='observed' if total else 'awaiting-first-original-input',
        scope='all-retained-episodes-single-database-snapshot',historyComplete=False,
        episodes=total,invalidEpisodes=invalid,checkedAt=checked,groups=output,
        cohorts=[dict(ruleVersion=k,firstDay=v.isoformat(),validationFrom=boundary(v).isoformat()) for k,v in sorted(starts.items())],
        strategyWinnerConfirmed=False,automaticPolicyChanges=False,actualNetKnown=False,
        note='Modellergebnisse mit angenommenen Kosten. Gleicher Einsatz, nicht gleiches Risiko. '
             'Nur gemeinsam geschlossene belegte Fälle; Nichteinstiege/Lücken separat. '
             'Erste zehn Schweizer Wochentage je Regelversion: Erkundung, danach Validierung. '
             '100 Paare sind nur ein Mindestziel, kein statistischer Beweis. '
             'Gespeicherter Bestand vollständig gelesen; externe Archive und Erfassungsvollständigkeit nicht bestätigt. '
             'Zwischengewinne/-verluste nur an beobachteten Kursen; kein Portfolio-Drawdown.')


# Project only fields required for evaluation: no original quotes, stop-history,
# screenshots or account data in the streamed result. Existing originals untouched.
PROJECTION = """SELECT jsonb_build_object(
 'version',payload->'version','ruleVersion',payload->'ruleVersion',
 'startedAt',payload->'startedAt','checkedAt',payload->'checkedAt',
 'trend',payload#>'{regime,trend}',
 'arms',(SELECT jsonb_object_agg(key,jsonb_build_object(
    'status',value->'status','modelNetEur',value->'modelNetEur',
    'entryAt',value->'entryAt','exitAt',value->'exitAt',
    'entryQuoteAt',value->'entryQuoteAt','exitQuoteAt',value->'exitQuoteAt',
    'entryAsk',value->'entryAsk','exitBid',value->'exitBid',
    'entryDebit',value->'entryDebit','units',value->'units',
    'isin',value#>'{choice,isin}',
    'observedPeakPnlEur',value->'observedPeakPnlEur',
    'observedTroughPnlEur',value->'observedTroughPnlEur'))
  FROM jsonb_each(payload->'arms')))
 FROM bob_entry_exit_comparison"""


def report(conn):
    deadline = time.monotonic() + 2
    # Keep one database statement snapshot, but never aggregate or join all
    # projected JSON objects inside PostgreSQL.  The previous anchor CTE made
    # the first FETCH materialize two full-table JSON passes.  Stream four
    # redacted projections at a time, derive the tiny cohort map in the app,
    # and fail closed instead of returning a partial history above the cap.
    rows, starts = [], {}
    with conn.cursor(name='bob_comparison_evaluation') as cursor:
        cursor.itersize = 4
        cursor.execute(PROJECTION)
        for record in cursor:
            if time.monotonic() > deadline:
                raise TimeoutError('comparison-report-budget')
            if (not isinstance(record, (tuple, list)) or len(record) != 1
                    or not isinstance(record[0], dict)):
                raise ValueError('comparison-projection-invalid')
            item = record[0]
            rows.append(item)
            if len(rows) > MAX_EPISODES:
                raise ValueError('comparison-episode-limit')
            rule, first = item.get('ruleVersion'), day(item.get('startedAt'))
            if isinstance(rule, str) and first:
                starts[rule] = min(starts.get(rule, first), first)
    return build(iter(rows), starts, deadline)
