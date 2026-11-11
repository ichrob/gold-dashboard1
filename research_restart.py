"""Bounded forward comparisons with a separately labelled estimated-input run.

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
                             workerErrors=0, stopObserved=0, targetObserved=0,
                             recentOriginalChecks=[], recentOriginalOutcomes=[],
                             recentOriginalFailureEvidence=[]),
                studies={s: dict(started=0, complete=0, inconclusive=0,
                                 lastKey=None, open=[], sums={}, observedWorst={},
                                 inconclusiveEvidenceReasons={}) for s in STUDIES})


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
    for profile, policy in paper_portfolios.POLICIES.items():
        # The older one-time quality restart must never retire or snapshot the
        # independent future-dated November user-requested paper comparison.
        if policy.get('relaunch'):
            continue
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


# Fixed, bounded evidence categories; none of these can make an input valid.
TERMINAL_EVIDENCE_REASONS = frozenset((
    'original-source-gap-over-90s',
    'worker-observation-gap-over-90s',
    'delayed-entry-original-unobserved',
    'original-path-unverified',
    'terminal-original-exit-unobserved',
    'estimated-path-unverified',
))


def original_failure_evidence(quality, bundle, market, now, timeframe):
    """Preserve a tiny, causal-clock witness without prices, broker data or IDs.

    Read-only explanation of a rejection. Never changes verified, freshness or
    the source/analysis admission policy, and never infers a historical cause.
    """
    from paper_shadow_studies import ORIGINAL_INPUT_REASONS, number
    source = quality.get('sourceAt')
    analysis = quality.get('analysisBarAt')
    data_at = market.get('dataAt')
    spots = (bundle or {}).get('spots') or {}
    code = quality.get('reasonCode')
    if code not in ORIGINAL_INPUT_REASONS:
        code = 'original-evidence-unverified'
    age = round(now - source) if number(source) and number(now) else None
    drift = round(data_at - source) if number(data_at) and number(source) else None
    return dict(
        checkedAt=int(now), sourceAt=int(source) if number(source) else None,
        analysisBarAt=int(analysis) if number(analysis) else None,
        reasonCode=code, timeframe=timeframe,
        sourceAgeMs=age if age is not None and -86400000 <= age <= 86400000 else None,
        dataSourceDeltaMs=drift if drift is not None and abs(drift) <= 86400000 else None,
        identityVerified=(spots.get('is_genuine_xauusd_spot') is True
                          and spots.get('xaus_is_spot') is True),
        closedSignalBarMatched=quality.get('closedSignalBarMatched') is True,
        clockRelation=('missing' if age is None else 'future' if age < 0
                       else 'stale-over-60s' if age > 60000 else 'within-60s'))


def terminal_evidence_reason(case, *, modeled=False):
    """Why a closed *inconclusive* reference case cannot be valued."""
    flags = case.get('evidenceFlags') or {}
    if flags.get('sourceGapOver90s'):
        return 'original-source-gap-over-90s'
    if flags.get('workerGapOver90s'):
        return 'worker-observation-gap-over-90s'
    if flags.get('delayedEntryWindowMissed'):
        return 'delayed-entry-original-unobserved'
    if modeled:
        return 'estimated-path-unverified'
    if case.get('dataGap'):
        return 'original-path-unverified'
    return 'terminal-original-exit-unobserved'


def advance(old, bundle, market, now, worker_outcomes=None, *, modeled=False):
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
    quality["closedSignalBarMatched"] = quality.pop("closed15mMatched")
    if not quality["verified"]:
        quality["reason"] = "original-spot-or-"+timeframe+"-evidence-unverified"
    if modeled:
        from simulation_estimates import input_quality
        quality = input_quality(quality,bundle,market,now,timeframe,state.get('lastOriginalInput'))
        state['simulationOnly'] = True
        state['dataPolicy'] = 'paper-gap-carry-v1'
        if quality['verified']:
            state['lastOriginalInput'] = copy.deepcopy(quality)
        q.setdefault('estimated',0)
        q['estimated'] += int(quality.get('estimated') is True)
    at = quality.get('sourceAt')
    previous_check = state.get('checkedAt')
    state['checkedAt'] = now
    q['cycles'] += 1
    q['workerErrors'] += sum(str(v).startswith('error') for v in (worker_outcomes or {}).values())
    valid = quality.get('simulationUsable',False) if modeled else quality['verified']
    if not modeled:
        # Only prospective, bounded study-health evidence. Cumulative
        # historical invalid counts never trigger a new watchdog incident.
        checks = q.get('recentOriginalChecks')
        checks = checks if isinstance(checks,list) else []
        q['recentOriginalChecks'] = [
            row for row in checks[-63:]
            if isinstance(row,dict) and type(row.get('at')) is int
            and 0 <= now-row['at'] <= 20*60000
            and type(row.get('valid')) is bool
        ] + [dict(at=int(now),valid=bool(quality['verified']))]
        outcomes = q.get('recentOriginalOutcomes')
        outcomes = outcomes if isinstance(outcomes,list) else []
        q['recentOriginalOutcomes'] = [
            row for row in outcomes[-63:]
            if isinstance(row,dict) and type(row.get('at')) is int
            and 0 <= now-row['at'] <= 4*3600000
            and row.get('study') in STUDIES
            and type(row.get('complete')) is bool
        ]
    if quality['verified']:
        q['original'] += 1
    else:
        # Cumulative compact counters are not reconstructed for historic
        # observations. They start at this code revision without rewriting
        # existing original cases or model-only outcomes.
        code = quality.get('reasonCode')
        from paper_shadow_studies import ORIGINAL_INPUT_REASONS
        if code not in ORIGINAL_INPUT_REASONS:
            code = "original-evidence-unverified"
        reasons = q.setdefault('originalBlockReasons', {})
        reasons[code] = reasons.get(code, 0) + 1
        q['lastOriginalBlockAt'] = now
        q['lastOriginalBlockCode'] = code
        if not valid:
            q['invalid'] += 1
        if not modeled:
            witnesses = q.get('recentOriginalFailureEvidence')
            witnesses = witnesses if isinstance(witnesses, list) else []
            # Prospective evidence only. Older 713 invalid results retain their
            # original counts and cannot be retrospectively reconstructed.
            q['recentOriginalFailureEvidence'] = (
                [row for row in witnesses[-15:]
                 if isinstance(row, dict)
                 and type(row.get('checkedAt')) is int
                 and 0 <= now - row['checkedAt'] <= 20 * 60000]
                + [original_failure_evidence(quality, bundle, market, now, timeframe)]
            )[-16:]
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
    if observation and modeled:
        observation.update(dataMode=quality['dataMode'],estimated=quality['estimated'],
            originalSourceAt=quality.get('originalSourceAt',at),calculatedAt=now,
            modelVersion='paper-gap-carry-v1')
    direction = market.get('direction') if market.get('direction') in ('LONG', 'SHORT') else None
    warning = warning_direction(market, now) if fresh else None
    q['signals' if fresh and (direction or warning) else 'waits'] += 1
    state['lastDecision'] = dict(at=now, sourceAt=at,
        category='technical-input-block' if not valid else 'estimated-input' if quality.get('estimated') else 'signal-observed' if direction or warning else 'rule-wait',
        reason=quality.get('reason') if not valid else str(market.get('decisionReason') or 'Keine Richtungsfreigabe')[:240])
    if modeled:
        state['lastInput'] = copy.deepcopy(quality)
    closed = []
    for study, ctl in state['studies'].items():
        pending = []
        for case in ctl['open']:
            from simulation_estimates import MAX_WORKER_GAP, same_session
            bounded_gap = (modeled and gap and now-previous_check <= MAX_WORKER_GAP
                           and same_session(previous_check,now))
            if modeled and (quality.get('estimated') or bounded_gap):
                case['estimatedUsed'] = True
                case['estimatedChecks'] = case.get('estimatedChecks',0)+1
                case['lastEstimate'] = copy.deepcopy(quality) if quality.get('estimated') else dict(
                    method='unobserved-path-between-originals',fromAt=previous_check,toAt=now,
                    calculatedAt=now,simulationOnly=True,extremesKnown=False)
            # A single rejected ORIGINAL tick is not necessarily a >90s
            # observation gap. Never fill it or infer a stop/exit: only allow
            # a later authentic source clock within the already accepted window.
            # Modeled cases deliberately retain their separate gap policy.
            if modeled:
                if not valid or (gap and not bounded_gap):
                    case['dataGap'] = True
            elif not valid:
                case['invalidOriginalChecks'] = case.get('invalidOriginalChecks', 0) + 1
                if number(case.get('lastAt')) and now-case['lastAt'] > 90000:
                    case['dataGap'] = True
            if not modeled and gap:
                case['dataGap'] = True
                case.setdefault('evidenceFlags', {})['workerGapOver90s'] = True
            if fresh:
                if at-case['lastAt'] > 90000:
                    if modeled and at-case['lastAt'] <= MAX_WORKER_GAP and same_session(case['lastAt'],at):
                        case['estimatedUsed'] = True
                        case['unobservedPath'] = True
                    else:
                        case['dataGap'] = True
                        case.setdefault('evidenceFlags', {})['sourceGapOver90s'] = True
                case['lastAt'] = at
                # Frozen direction; opposite signals do not fill the old intent.
                for name, l in case['legs'].items():
                    if not l['entry'] and not l['wait'] and quality.get('newEntryAllowed') is not False:
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
                                    case.setdefault('evidenceFlags', {})['delayedEntryWindowMissed'] = True
                    if l['entry']:
                        sign = 1 if l['direction'] == 'LONG' else -1
                        move = sign*(quality['price']/l['entry']['price']-1)*100
                        l['adversePct'] = min(l['adversePct'], move)
                        plan = case.get('plan') or {}
                        if plan.get('direction') == l['direction']:
                            for field, key in (('stop', 'stopObserved'), ('target', 'targetObserved')):
                                level = plan.get(field)
                                hit = number(level) and (sign*(quality['price']-level) <= 0 if field == 'stop' else sign*(quality['price']-level) >= 0)
                                if hit and not l[key] and quality['verified']:
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
            case['outcomeEvidenceCode'] = (
                'observed-common-horizon' if case['status'] == 'complete'
                else terminal_evidence_reason(case, modeled=modeled))
            case['returnsPct'] = {}
            if case['status'] == 'complete':
                for name, l in case['legs'].items():
                    entry = l['entry']
                    value = (100*(1 if l['direction']=='LONG' else -1)*(case['exit']['price']/entry['price']-1)-.16) if entry else 0.
                    case['returnsPct'][name] = value
                    ctl['sums'][name] = ctl['sums'].get(name, 0.)+value
                    ctl['observedWorst'][name] = min(ctl['observedWorst'].get(name, 0.), l['adversePct'])
                ctl['complete'] += 1
                if modeled and case.get('estimatedUsed'):
                    ctl['estimatedComplete'] = ctl.get('estimatedComplete',0)+1
            else:
                ctl['inconclusive'] += 1
                counts = ctl.setdefault('inconclusiveEvidenceReasons', {})
                reason = case['outcomeEvidenceCode']
                if reason not in TERMINAL_EVIDENCE_REASONS:
                    reason = 'original-path-unverified'
                counts[reason] = counts.get(reason, 0) + 1
            if not modeled and case.get('inputGapPolicy') == 'original-observed-over-90s-v2':
                # Never reclassify historical original cases or model runs.
                rows = q['recentOriginalOutcomes']
                rows.append(dict(at=int(now),study=study,
                                 complete=case['status']=='complete'))
                q['recentOriginalOutcomes'] = rows[-64:]
            closed.append(case)
        ctl['open'] = pending
    if fresh:
        state['lastSourceAt'] = at
    local = datetime.fromtimestamp(now/1000, ZoneInfo('Europe/Zurich'))
    accepting = now < state['deadlineAt'] and local.weekday() < 5 and 8 <= local.hour < 21
    if fresh and accepting and quality.get('newEntryAllowed') is not False:
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
                        inputGapPolicy=('estimated-paper-gap-carry-v1' if modeled
                                        else 'original-observed-over-90s-v2'),
                        plan=copy.deepcopy(market.get('plan')), status='pending',
                        scope='spot-reference-not-product-return', costAssumptionPct=.16)
            if modeled:
                case.update(id=case['id']+':model-v1',simulationOnly=True,
                    dataPolicy='paper-gap-carry-v1',estimatedUsed=quality.get('estimated') is True,
                    originalResultVerified=False)
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
    if row[0]['status'].startswith('completed') and (not row[0].get('modeledSimulation')
            or row[0]['modeledSimulation']['status'].startswith('completed')):
        return
    original = copy.deepcopy(row[0])
    model_state = original.pop('modeledSimulation',None)
    state, closed = advance(original, bundle, market, now, worker_outcomes)
    # A prospective companion starts once, without reclassifying old originals.
    # Same signals and costs; only its bounded data-gap policy differs.
    if model_state is None:
        model_state = seed(now)
        model_state['deadlineAt'] = state['deadlineAt']
    model_state, model_closed = advance(model_state,bundle,market,now,
                                       worker_outcomes,modeled=True)
    state['modeledSimulation'] = model_state
    closed += model_closed
    for case in closed:
        conn.execute('INSERT INTO bob_quality_cases VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                     (case['id'], VERSION, dumps(case)))
    conn.execute('UPDATE bob_quality_campaign SET payload=%s::jsonb WHERE id=%s', (dumps(state), VERSION))


def report(conn):
    row = conn.execute('SELECT payload FROM bob_quality_campaign WHERE id=%s', (VERSION,)).fetchone()
    if not row:
        return dict(status='not-started', realOrders=False)
    state = row[0]
    studies = study_rows(state)
    model = state.get('modeledSimulation')
    modeled = dict(status=model['status'],startedAt=model['startedAt'],checkedAt=model['checkedAt'],
        policy=model.get('dataPolicy'),studies=study_rows(model),lastInput=model.get('lastInput'),
        realOrders=False,originalResultVerified=False,
        note='Simulation einschließlich gekennzeichneter Schätzungen: Kursüberbrückung höchstens 180 Sekunden, höchstens zwei fehlende 5m/15m-Kerzen. Fehlende Hoch-/Tiefverläufe bleiben unbekannt. Gleiche beobachtete Signale und Modellkosten; keine verifizierte Produktrendite.') if model else dict(status='not-started')
    return dict(version=VERSION, status=state['status'], startedAt=state['startedAt'],
                checkedAt=state['checkedAt'], deadlineAt=state['deadlineAt'], studies=studies,
                modeledSimulation=modeled,
                lessons=state['lessons'], lastDecision=state.get('lastDecision'), legacySnapshots=state.get('legacySnapshots'),
                realOrders=False, liveRulesChanged=False, winnerVerified=False,
                note='60-Minuten-Spotvergleich mit 0,16 % Modellkosten; keine KO-Produktrendite. Originalauswertung und Simulation mit Schätzungen separat. Maximal 20 Kalendertage/200 Fälle je Vergleich, danach gesonderte Prüfung an neuen Daten. Stop/Ziel nur beobachtet, keine Ausführung behauptet.')


def study_rows(state):
    quality = state['quality']
    cause_counts = quality.get('originalBlockReasons')
    categorized = (sum(v for k, v in cause_counts.items()
                       if k in __import__('paper_shadow_studies').ORIGINAL_INPUT_REASONS
                       and type(v) is int and v >= 0)
                   if isinstance(cause_counts, dict) else 0)
    reaction = dict(id='reaction', label=LABELS['reaction'], **quality)
    # Historical checks predate reason counters; the remainder is not a
    # newly determined or independently verified cause.
    reaction['originalLegacyUnclassified'] = max(0, quality['invalid'] - categorized)
    studies = [reaction]
    for name, c in state['studies'].items():
        total = c['complete']+c['inconclusive']
        reasons = c.get('inconclusiveEvidenceReasons')
        reasons = ({key: value for key, value in reasons.items()
                    if key in TERMINAL_EVIDENCE_REASONS
                    and type(value) is int and 0 <= value <= c['inconclusive']}
                   if isinstance(reasons, dict) else {})
        categorized = sum(reasons.values())
        studies.append(dict(id=name, label=LABELS[name], started=c['started'], complete=c['complete'],
                            inconclusive=c['inconclusive'], open=len(c['open']),
                            inconclusiveEvidenceReasons=reasons,
                            historicalInconclusiveUnclassified=max(0, c['inconclusive'] - categorized),
                            qualityPct=round(100*c['complete']/total, 1) if total else None,
                            meanNetReferencePct={k:v/c['complete'] for k,v in c['sums'].items()} if c['complete'] else {},
                            estimatedComplete=c.get('estimatedComplete',0),
                            observedWorstPct=c['observedWorst']))
    return studies
