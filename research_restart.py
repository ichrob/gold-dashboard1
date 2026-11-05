"""Bounded forward comparisons. Original observations only; never live rules.

One shared input per worker cycle, compact counters and one record per case.
All returns are fixed-horizon spot benchmarks, NOT executable KO returns.
"""
import copy
import hashlib
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = 'quality-restart-20261105-v1'
HORIZON = 3600000
GRACE = 60000
MAX_DAYS = 20
MAX_CASES = 200
STUDIES = ('warning-confirmed', 'entry-delay', 'sideways-filter')
LABELS = {'reaction': 'Reagiert Bob zuverlässig?',
          'warning-confirmed': 'Frühwarnung gegen Bestätigung',
          'entry-delay': 'Sofort oder 30/60 Sekunden warten',
          'sideways-filter': 'Seitwärtsfilter'}
LESSONS = [
    dict(id='timing', status='hypothesis', text='Früher ist nicht automatisch besser; auf neuen gemeinsamen Fällen prüfen.'),
    dict(id='costs', status='hypothesis', text='Häufige Einstiege und Modellkosten gemeinsam auswerten.'),
    dict(id='risk', status='hypothesis', text='Große Verluste der alten Risikomodelle sind ein Warnhinweis, kein verifizierter Strategieeffekt.'),
    dict(id='gaps', status='quality-rule', text='Fehlende Originaldaten nie als Gewinn oder Verlust werten.'),
]


def dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def seed(now):
    return dict(version=VERSION, startedAt=now, deadlineAt=now+MAX_DAYS*86400000,
                status='collecting', realOrders=False, liveRulesChanged=False,
                lessons=copy.deepcopy(LESSONS), checkedAt=None, lastSourceAt=None,
                quality=dict(cycles=0, original=0, invalid=0, missingIntervals=0,
                             duplicateSource=0, waits=0, signals=0,
                             workerErrors=0, stopObserved=0, targetObserved=0),
                studies={s: dict(started=0, complete=0, inconclusive=0,
                                 lastKey=None, open=[], sums={}, observedWorst={}) for s in STUDIES})


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_quality_campaign (
        id TEXT PRIMARY KEY, payload JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_quality_cases (
        id TEXT PRIMARY KEY, campaign TEXT NOT NULL, payload JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_quality_legacy (
        id TEXT PRIMARY KEY, captured_at TIMESTAMPTZ NOT NULL,
        sha256 TEXT NOT NULL, payload JSONB NOT NULL)''')


def start(conn, now):
    """One transaction under paper worker lock: snapshot BEFORE retirement.

    Keep all original case/event tables. No deletion or historical P/L repair.
    Does not run at deployment startup while another worker might still write.
    """
    if conn.execute('SELECT payload FROM bob_quality_campaign WHERE id=%s', (VERSION,)).fetchone():
        return
    import paper_portfolios
    snapshots = {}
    for profile in paper_portfolios.POLICIES:
        ledger = paper_portfolios.Ledger(conn, profile)
        row = ledger.execute('SELECT payload FROM bob_paper_control WHERE id=1 FOR UPDATE').fetchone()
        if row:
            snapshots['paper-'+profile] = copy.deepcopy(row[0])
            ctl = {**row[0], 'retiredAt': now, 'retirementReason': VERSION}
            ledger.execute('UPDATE bob_paper_control SET payload=%s::jsonb WHERE id=1', (dumps(ctl),))
    for table, key in (('bob_risk_paper', 'risk'),):
        row = conn.execute(f'SELECT payload FROM {table} WHERE id=1 FOR UPDATE').fetchone()
        if row:
            snapshots[key] = copy.deepcopy(row[0])
            conn.execute(f'UPDATE {table} SET payload=%s::jsonb WHERE id=1',
                         (dumps({**row[0], 'retiredAt': now}),))
    for study, ctl in conn.execute('SELECT study,payload FROM bob_shadow_study_control FOR UPDATE').fetchall():
        snapshots['shadow-'+study] = copy.deepcopy(ctl)
        conn.execute('UPDATE bob_shadow_study_control SET payload=%s::jsonb WHERE study=%s',
                     (dumps({**ctl, 'retiredAt': now}), study))
    for key, value in snapshots.items():
        raw = dumps(value)
        conn.execute('''INSERT INTO bob_quality_legacy VALUES(%s,to_timestamp(%s/1000.0),%s,%s::jsonb)
            ON CONFLICT DO NOTHING''', (VERSION+':'+key, now, hashlib.sha256(raw.encode()).hexdigest(), raw))
    state = seed(now)
    state['legacySnapshots'] = len(snapshots)
    state['legacyNote'] = 'Originaltabellen erhalten; Kontoschnappschüsse mit Prüfsumme. Kein vollständiger historischer Renditenachweis.'
    conn.execute('INSERT INTO bob_quality_campaign VALUES(%s,%s::jsonb)', (VERSION, dumps(state)))


def warning_direction(market, now):
    w = market.get('earlyWarning') or {}
    if (w.get('available') is True and w.get('state') in ('active', 'watch')
            and w.get('comparisonOnly') is True and w.get('affectsApproval') is False
            and w.get('extensionRisk') is not True
            and type(w.get('expiresAt')) in (int, float) and now < w['expiresAt']
            and type(w.get('signalBarAt')) in (int, float) and w['signalBarAt'] <= now
            and w.get('direction') in ('LONG', 'SHORT')):
        return w['direction']
    return None


def leg(direction=None, entry=None, wait=False):
    return dict(direction=direction, entry=copy.deepcopy(entry), wait=wait,
                adversePct=0., stopObserved=False, targetObserved=False)


def advance(old, bundle, market, now, worker_outcomes=None):
    """Pure state machine; all variants share a frozen event and common end.

    Gaps >90s exclude a case, even if an end quote later appears. Repeated source
    clocks never simulate another trade. Deadline/max-case are stopping rules,
    not claims of statistical sufficiency. No automatic winner or rule promotion.
    """
    from paper_shadow_studies import original_input, number
    import ranking_regimes
    state = copy.deepcopy(old)
    q = state['quality']
    if state['status'].startswith('completed'):
        return state, []
    timeframe = "5m" if market.get("entryTiming") in ("five-minute-confirmation", "two-minute-follow-through-v1") else "15m"
    quality = original_input(bundle, market, now, timeframe)
    quality["signalTimeframe"] = timeframe
    at = quality.get('sourceAt')
    previous_check = state.get('checkedAt')
    state['checkedAt'] = now
    q['cycles'] += 1
    q['workerErrors'] += sum(str(v).startswith('error') for v in (worker_outcomes or {}).values())
    valid = quality['verified']
    q['original' if valid else 'invalid'] += 1
    fresh = valid and (state['lastSourceAt'] is None or at > state['lastSourceAt'])
    if valid and not fresh:
        q['duplicateSource'] += 1
    # Session breaks are not outages. An open hour-long case crossing them is
    # still excluded, and new cases stop at 20:55 Zurich.
    gap = bool(previous_check and now-previous_check > 90000)
    if gap:
        a = datetime.fromtimestamp(previous_check/1000, ZoneInfo('Europe/Zurich'))
        b = datetime.fromtimestamp(now/1000, ZoneInfo('Europe/Zurich'))
        if a.date() == b.date() and a.weekday() < 5 and 8 <= a.hour < 22 and 8 <= b.hour < 22:
            q['missingIntervals'] += 1
    observation = dict(at=at, price=quality['price']) if fresh else None
    direction = market.get('direction') if market.get('direction') in ('LONG', 'SHORT') else None
    warning = warning_direction(market, now) if fresh else None
    q['signals' if fresh and (direction or warning) else 'waits'] += 1
    state['lastDecision'] = dict(at=now, sourceAt=at,
        category='technical-input-block' if not valid else 'signal-observed' if direction or warning else 'rule-wait',
        reason=quality.get('reason') if not valid else str(market.get('decisionReason') or 'Keine Richtungsfreigabe')[:240])
    closed = []
    for study, ctl in state['studies'].items():
        pending = []
        for case in ctl['open']:
            if not valid or gap:
                case['dataGap'] = True
            if fresh:
                if at-case['lastAt'] > 90000:
                    case['dataGap'] = True
                case['lastAt'] = at
                # Frozen direction; opposite signals do not fill the old intent.
                for name, l in case['legs'].items():
                    if not l['entry'] and not l['wait']:
                        due = case['at'] + l.get('delayMs', 0)
                        if at >= due and at < case['endAt']:
                            approved = direction == case['direction']
                            if study == 'entry-delay':
                                approved = (direction or warning) == case['direction']
                            if approved and (study != 'entry-delay' or at <= due+GRACE):
                                l['entry'] = copy.deepcopy(observation)
                                l['direction'] = case['direction']
                            elif study == 'entry-delay':
                                if (direction or warning) != case['direction']:
                                    l['wait'] = True
                                elif at > due+GRACE:
                                    case['dataGap'] = True
                    if l['entry']:
                        sign = 1 if l['direction'] == 'LONG' else -1
                        move = sign*(quality['price']/l['entry']['price']-1)*100
                        l['adversePct'] = min(l['adversePct'], move)
                        plan = case.get('plan') or {}
                        if plan.get('direction') == l['direction']:
                            for field, key in (('stop', 'stopObserved'), ('target', 'targetObserved')):
                                level = plan.get(field)
                                hit = number(level) and (sign*(quality['price']-level) <= 0 if field == 'stop' else sign*(quality['price']-level) >= 0)
                                if hit and not l[key]:
                                    l[key] = True
                                    q[key] += 1
            due = case['endAt']
            if fresh and due <= at <= due+GRACE:
                case['exit'] = copy.deepcopy(observation)
                case['status'] = 'inconclusive' if case['dataGap'] else 'complete'
            elif now > due+GRACE:
                case['status'] = 'inconclusive'
            else:
                pending.append(case)
                continue
            case['closedAt'] = now
            case['returnsPct'] = {}
            if case['status'] == 'complete':
                for name, l in case['legs'].items():
                    entry = l['entry']
                    value = (100*(1 if l['direction']=='LONG' else -1)*(case['exit']['price']/entry['price']-1)-.16) if entry else 0.
                    case['returnsPct'][name] = value
                    ctl['sums'][name] = ctl['sums'].get(name, 0.)+value
                    ctl['observedWorst'][name] = min(ctl['observedWorst'].get(name, 0.), l['adversePct'])
                ctl['complete'] += 1
            else:
                ctl['inconclusive'] += 1
            closed.append(case)
        ctl['open'] = pending
    if fresh:
        state['lastSourceAt'] = at
    local = datetime.fromtimestamp(now/1000, ZoneInfo('Europe/Zurich'))
    accepting = now < state['deadlineAt'] and local.weekday() < 5 and 8 <= local.hour < 21
    if fresh and accepting:
        regime = ranking_regimes.classify(market)
        for study, ctl in state['studies'].items():
            if ctl['started'] >= MAX_CASES:
                continue
            d = warning if study == 'warning-confirmed' else (direction or warning) if study == 'entry-delay' else direction
            if not d or (study == 'sideways-filter' and regime['trend'] == 'unknown'):
                continue
            key = str(quality['analysisBarAt'])+':'+d
            if ctl['lastKey'] == key:
                continue
            # At most one non-overlapping case per study to limit dependence,
            # storage, and simultaneous hypothetical exposure.
            if ctl['open']:
                continue
            if study == 'warning-confirmed':
                legs = {'early': leg(d, observation), 'confirmed': leg(d, observation if direction==d else None)}
            elif study == 'entry-delay':
                legs = {'0s': leg(d, observation), '30s': {**leg(d), 'delayMs':30000}, '60s': {**leg(d), 'delayMs':60000}}
            else:
                legs = {'baseline': leg(d, observation), 'filter': leg(d, observation if regime['trend']!='sideways' else None, regime['trend']=='sideways')}
            case = dict(id=VERSION+':'+study+':'+str(int(at)), study=study, at=at,
                        endAt=at+HORIZON, lastAt=at, direction=d, legs=legs,
                        dataGap=False, regime=regime, originalInput=quality,
                        plan=copy.deepcopy(market.get('plan')), status='pending',
                        scope='spot-reference-not-product-return', costAssumptionPct=.16)
            ctl['open'].append(case)
            ctl['lastKey'] = key
            ctl['started'] += 1
    if now >= state['deadlineAt'] or all(c['started'] >= MAX_CASES for c in state['studies'].values()):
        state['status'] = 'draining' if any(c['open'] for c in state['studies'].values()) else 'completed-review-required'
    return state, closed


def tick(conn, bundle, market, now, worker_outcomes=None):
    row = conn.execute('SELECT payload FROM bob_quality_campaign WHERE id=%s FOR UPDATE', (VERSION,)).fetchone()
    if not row:
        raise RuntimeError('quality-campaign-not-initialized')
    if row[0]['status'].startswith('completed'):
        return
    state, closed = advance(row[0], bundle, market, now, worker_outcomes)
    for case in closed:
        conn.execute('INSERT INTO bob_quality_cases VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                     (case['id'], VERSION, dumps(case)))
    conn.execute('UPDATE bob_quality_campaign SET payload=%s::jsonb WHERE id=%s', (dumps(state), VERSION))


def report(conn):
    row = conn.execute('SELECT payload FROM bob_quality_campaign WHERE id=%s', (VERSION,)).fetchone()
    if not row:
        return dict(status='not-started', realOrders=False)
    state = row[0]
    studies = [dict(id='reaction', label=LABELS['reaction'], **state['quality'])]
    for name, c in state['studies'].items():
        total = c['complete']+c['inconclusive']
        studies.append(dict(id=name, label=LABELS[name], started=c['started'], complete=c['complete'],
                            inconclusive=c['inconclusive'], open=len(c['open']),
                            qualityPct=round(100*c['complete']/total, 1) if total else None,
                            meanNetReferencePct={k:v/c['complete'] for k,v in c['sums'].items()} if c['complete'] else {},
                            observedWorstPct=c['observedWorst']))
    return dict(version=VERSION, status=state['status'], startedAt=state['startedAt'],
                checkedAt=state['checkedAt'], deadlineAt=state['deadlineAt'], studies=studies,
                lessons=state['lessons'], lastDecision=state.get('lastDecision'), legacySnapshots=state.get('legacySnapshots'),
                realOrders=False, liveRulesChanged=False, winnerVerified=False,
                note='60-Minuten-Spotvergleich mit 0,16 % Modellkosten; keine KO-Produktrendite. Lücken ausgeschlossen. Maximal 20 Kalendertage/200 Fälle je Vergleich, danach gesonderte Prüfung an neuen Daten. Stop/Ziel nur beobachtet, keine Ausführung behauptet.')
