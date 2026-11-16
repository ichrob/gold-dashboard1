"""Bounded prospective paired spot study; no quote fetching or account writes.

One shared opportunity, six fixed rules, 180-minute maximum holding period.
Stops/targets settle only at the next observed spot; gaps are inconclusive.
Recent evidence is bounded; cumulative counters retain losses and missing cases.
"""
import copy
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = 'entry-opportunities-v1'
ARMS = ('reference', 'distance25', 'age20', 'combined', 'minute', 'zones')
MINUTE = 60000
COST = .0016


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


def source(bundle, now):
    """Require a genuine, timezone-aware, fresh source quote for shadow study.

    A missing/malformed timestamp must not raise in the paper worker or be
    interpreted in the host machine's local timezone. No clock is re-dated.
    """
    if not isinstance(bundle, dict) or not number(now) or now <= 0:
        return None
    s = bundle.get('spots')
    if not isinstance(s, dict):
        return None
    clock = s.get('spot_price_as_of')
    if not isinstance(clock, str):
        return None
    try:
        parsed = datetime.fromisoformat(clock.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        at = parsed.timestamp() * 1000
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    p = s.get('xaus')
    if (s.get('is_genuine_xauusd_spot') is True and not s.get('spot_error')
            and number(p) and p > 0 and number(at) and 0 <= now-at <= MINUTE):
        return p, at
    return None


def seed(now):
    return dict(version=VERSION, startedAt=now, checkedAt=None, cycles=0, episodes=0,
        completedPairs=0, inconclusivePairs=0, active=None, recent=[], lastKey=None,
        arms={key:dict(started=0, closed=0, skipped=0, inconclusive=0,
            pairedNetR=0., pairedModelReturnPct=0., pairedWins=0, pairedLosses=0,
            worstPairedNetR=None, maxObservedAdverseR=0., maxObservedFavorableR=0.,
            additionalEntries=0, avoidedLosses=0, missedWins=0) for key in ARMS})


def valid_trial(trial, market, price, at, now):
    if not isinstance(trial, dict):
        return False
    if (trial.get('version') != VERSION or trial.get('comparisonOnly') is not True
            or trial.get('status') != 'observed' or market.get('ready') is not True
            or market.get('priceFresh') is not True
            or (market.get('session') or {}).get('entryAllowed') is not True
            or trial.get('direction') not in ('LONG', 'SHORT')
            or market.get('direction') != trial.get('direction')
            or not number(trial.get('checkedAt')) or not 0 <= now-trial['checkedAt'] <= MINUTE
            or trial.get('sourceAt') != at or market.get('dataAt') != at
            or market.get('price') != price or not number(trial.get('barAt'))
            or not 0 <= now-trial['barAt']-5*MINUTE <= 5*MINUTE):
        return False
    arms = trial.get('arms')
    if not isinstance(arms, dict) or set(arms) != set(ARMS):
        return False
    sign = 1 if trial['direction'] == 'LONG' else -1
    for row in arms.values():
        if not isinstance(row, dict) or type(row.get('allowed')) is not bool:
            return False
        if row['allowed']:
            p = row.get('plan') or {}
            if (p.get('direction') != trial['direction'] or p.get('entry') != price
                    or not all(number(p.get(k)) and p[k] > 0 for k in ('entry','stop','target'))
                    or sign*(price-p['stop']) <= 0
                    or sign*(p['target']-price) < 2*abs(price-p['stop'])):
                return False
    return True


def advance(old, bundle, market, now):
    s = copy.deepcopy(old)
    if not number(now) or s['checkedAt'] is not None and now <= s['checkedAt']:
        return s
    s['checkedAt'] = now
    s['cycles'] += 1
    clock = datetime.fromtimestamp(now/1000, ZoneInfo('Europe/Zurich'))
    closing = clock.weekday() >= 5 or (clock.hour, clock.minute) >= (21,45) or clock.hour < 8
    quote = source(bundle, now)
    episode = s['active']
    if episode:
        for key, p in episode['arms'].items():
            if p['status'] != 'open':
                continue
            if now-p['lastObservedAt'] > 90000:
                p.update(status='inconclusive', exitReason='observation-gap', netR=None)
                s['arms'][key]['inconclusive'] += 1
                continue
            if not quote or quote[1] <= p['lastSourceAt']:
                continue
            price, at = quote
            sign = 1 if p['direction'] == 'LONG' else -1
            gross_r = sign*(price-p['entry'])/p['risk']
            p['maxAdverseR'] = max(p['maxAdverseR'], -gross_r)
            p['maxFavorableR'] = max(p['maxFavorableR'], gross_r)
            p.update(lastSourceAt=at, lastObservedAt=now)
            why = ('stop' if sign*(price-p['stop']) <= 0 else
                   'target' if sign*(price-p['target']) >= 0 else
                   'session-close' if closing else
                   'horizon' if at-episode['sourceAt'] >= 180*MINUTE else None)
            if why:
                net = gross_r - p['entry']*COST/p['risk']
                p.update(status='closed', exitReason=why, exitPrice=price,
                         exitSourceAt=at, netR=net,
                         modelReturnPct=net*min(1.,65*p['risk']/p['entry']))
                s['arms'][key]['closed'] += 1
        if all(p['status'] != 'open' for p in episode['arms'].values()):
            comparable = all(p['status'] in ('closed','skipped') for p in episode['arms'].values())
            s['completedPairs' if comparable else 'inconclusivePairs'] += 1
            episode['comparable'] = comparable
            if comparable:
                ref = episode['arms']['reference']
                for key, p in episode['arms'].items():
                    a = s['arms'][key]
                    if p['status'] == 'closed':
                        a['pairedNetR'] += p['netR']
                        a['pairedModelReturnPct'] += p['modelReturnPct']
                        a['pairedWins'] += p['netR'] > 0
                        a['pairedLosses'] += p['netR'] < 0
                        a['worstPairedNetR'] = min(a['worstPairedNetR'],p['netR']) if a['worstPairedNetR'] is not None else p['netR']
                        a['maxObservedAdverseR'] = max(a['maxObservedAdverseR'],p['maxAdverseR'])
                        a['maxObservedFavorableR'] = max(a['maxObservedFavorableR'],p['maxFavorableR'])
                        a['additionalEntries'] += ref['status'] == 'skipped'
                    else:
                        a['avoidedLosses'] += ref.get('netR',0) < 0
                        a['missedWins'] += ref.get('netR',0) > 0
            s['recent'] = (s['recent'] + [episode])[-20:]
            s['active'] = None
        return s  # never close and re-enter on the same observation
    trial = market.get('entryOpportunityStudy')
    s['inputStatus'] = 'night-pause' if closing else 'unverified-or-no-direction'
    if closing or not quote or not valid_trial(trial,market,*quote,now):
        return s
    key = str(trial['barAt'])+':'+trial['direction']
    s['inputStatus'] = 'observed'
    s['lastDecision'] = {k:dict(allowed=v['allowed'],reason=str(v.get('reason',''))[:200],
        gate=v.get('gate'),zone=v.get('zone')) for k,v in trial['arms'].items()}
    if key == s['lastKey'] or not any(r['allowed'] for r in trial['arms'].values()):
        return s
    s['lastKey'] = key
    s['episodes'] += 1
    price, at = quote
    episode = dict(key=key, startedAt=now, sourceAt=at, arms={},decision=s['lastDecision'])
    for key, r in trial['arms'].items():
        if not r['allowed']:
            episode['arms'][key] = dict(status='skipped',netR=0.)
            s['arms'][key]['skipped'] += 1
        else:
            p = r['plan']
            episode['arms'][key] = dict(p,status='open',risk=abs(price-p['stop']),
                lastObservedAt=now,lastSourceAt=at,maxAdverseR=0.,maxFavorableR=0.)
            s['arms'][key]['started'] += 1
    s['active'] = episode
    return s


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_entry_opportunity_state
        (id TEXT PRIMARY KEY, payload JSONB NOT NULL)''')


def tick(conn, bundle, market, now):
    row = conn.execute('SELECT payload FROM bob_entry_opportunity_state WHERE id=%s FOR UPDATE',(VERSION,)).fetchone()
    s = advance(row[0] if row else seed(now),bundle,market,now)
    conn.execute('''INSERT INTO bob_entry_opportunity_state VALUES(%s,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload''',(VERSION,json.dumps(s,allow_nan=False)))


def brief(s):
    if not s:
        return dict(version=VERSION,status='awaiting-first-worker-check',realOrders=False)
    return dict(version=VERSION,status='collecting',checkedAt=s.get('checkedAt'),
        startedAt=s.get('startedAt'),inputStatus=s.get('inputStatus'),episodes=s.get('episodes'),
        completedPairs=s.get('completedPairs'),inconclusivePairs=s.get('inconclusivePairs'),
        active=bool(s.get('active')),variants=s.get('arms'),lastDecision=s.get('lastDecision'),
        strategyWinnerConfirmed=False,productReturnVerified=False,realOrders=False,
        liveRulesChanged=False,horizonMinutes=180,assumedRoundTripCostPct=.16,
        riskBudgetPct=1,maximumExposurePct=65,
        note='Paired prospective spot models; no broker fills. Missing cases excluded jointly. '
             'Returns are sums at fixed reference capital, not compounded account balances. '
             'Adverse/favorable excursions are sampled, not complete intrabar drawdown. '
             'Last 20 episode details retained, cumulative counters preserved.')


def report(conn):
    row = conn.execute('SELECT payload FROM bob_entry_opportunity_state WHERE id=%s',(VERSION,)).fetchone()
    return brief(row[0] if row else None)
