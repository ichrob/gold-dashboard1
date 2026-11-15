"""Five isolated, forward-only PAPER accounts. No brokerage endpoints.

All profiles consume the same timestamped observations; their ledger tables,
trade IDs, cash and risk decisions are kept separate in PostgreSQL. The existing
2026-10-08 paper study is retained as an archive and never used as a fourth
active account. Accounts begin at Monday 2026-10-12 08:00 Europe/Zurich.
"""
import copy
import json
import math
import time
import stop_target_audit
from datetime import datetime
from zoneinfo import ZoneInfo

START = int(datetime(2026, 10, 12, 8, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
POLICIES = {
    'conservative': dict(id='conservative', title='Konservativ', exposure_fraction=.35,
                         daily_loss_fraction=.01, score_long=80, score_short=20,
                         require_trend=True),
    'balanced': dict(id='balanced', title='Ausgewogen', exposure_fraction=.65,
                     daily_loss_fraction=.03, score_long=70, score_short=30,
                     require_trend=False),
    'offensive': dict(id='offensive', title='Offensiv', exposure_fraction=.95,
                      daily_loss_fraction=.05, score_long=65, score_short=35,
                      require_trend=False),
    'early100': dict(id='early100', title='Frühimpuls 100 € · LONG/SHORT (Test)',
                     initial_capital_eur=100., exposure_fraction=.65,
                     daily_loss_fraction=.03, score_long=70, score_short=30,
                     require_trend=False, early_impulse=True),
    'trend800': dict(id='trend800', title='800 € · Bob-Stopp & Wiedereinstieg',
                     initial_capital_eur=800.,
                     exposure_fraction=.65, daily_loss_fraction=.03,
                     score_long=70, score_short=30, require_trend=True,
                     hold_trend=False, bob_stop_reentry=True),
}

CAMPAIGN_END = int(datetime(2026, 11, 6, 16, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
for _name, _early in (('early1000oct', True), ('normal1000oct', False)):
    POLICIES[_name] = dict(id=_name, title=('Frühwarnung' if _early else 'Hauptsignal')+' · 1.000 € · bis Fr 16 Uhr',
        initial_capital_eur=1000., exposure_fraction=.65, daily_loss_fraction=.03,
        score_long=70, score_short=30, require_trend=False, early_warning=_early,
        campaign_end=CAMPAIGN_END, campaign=True)

# New, independent 20-trading-day prospective comparison. These are separate
# ledgers: old completed October accounts and the manual 800 EUR test stay intact.
# Neither account may enter before Monday's 08:00 Swiss entry window.
RELAUNCH_START = int(datetime(2026, 11, 9, 8, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
RELAUNCH_END = int(datetime(2026, 12, 4, 16, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
RELAUNCH_ID = 'trend-vs-main-20261109'
POLICIES['trend800nov'] = dict(POLICIES['trend800'],
    id='trend800nov', title='Neu: 800 € · Trend/Stopp/Wiedereinstieg · 09.11.–04.12.',
    campaign=True, relaunch=True, campaign_id=RELAUNCH_ID,
    start_at=RELAUNCH_START, campaign_end=RELAUNCH_END,
    max_holding_minutes=300, paper_campaign_entry=True)
POLICIES['normal1000nov'] = dict(POLICIES['normal1000oct'],
    id='normal1000nov', title='Neu: 1.000 € · bestätigtes Hauptsignal · 09.11.–04.12.',
    campaign=True, relaunch=True, campaign_id=RELAUNCH_ID,
    start_at=RELAUNCH_START, campaign_end=RELAUNCH_END,
    max_holding_minutes=300, paper_campaign_entry=True)

# Owner-requested isolated 3,000 EUR account, starting at first initialization.
POLICIES['ema3000nov'] = dict(POLICIES['normal1000oct'],
    id='ema3000nov', title='3.000 € · EMA-Abstand bis 2,5 ATR · Test',
    initial_capital_eur=3000., campaign=True, campaign_id='ema25-3000-20261111',
    campaign_end=RELAUNCH_END, relaxed_ema=True, max_holding_minutes=300)

# Forward-only user-requested EMA-distance experiment; no inherited start date.
POLICIES['noema5000nov'] = dict(POLICIES['normal1000nov'],
    id='noema5000nov', title='5.000 € · EMA-Abstandssperre aus (Test)',
    initial_capital_eur=5000., relaunch=False,
    campaign_id='no-ema-distance-20261111', disable_ema_distance=True,
    paper_campaign_entry=False)

_PAPER_CAMPAIGN_GATES = {
    'trend800nov': ('campaign-800-entry-v1', 1.0),
    'normal1000nov': ('campaign-1000-entry-v1', 1.2),
}

_TABLES = ('bob_paper_control', 'bob_paper_cases', 'bob_paper_days')


def names(profile):
    if profile not in POLICIES:
        raise ValueError('Unbekanntes Testkonto')
    # Table names are always derived from a static code-owned allowlist.
    return {name: 'bob_paper_' + profile + '_' + name.removeprefix('bob_paper_')
            for name in _TABLES}


class Ledger:
    """Use the validated legacy paper lifecycle against a separate table set.

    SQL substitution is restricted to three types of private paper-ledger tables.
    The shared, read-only quote universe stays bob_paper_products.
    """
    def __init__(self, conn, profile):
        self.profile = profile
        self.conn = conn
        self.tables = names(profile)

    def execute(self, sql, params=()):
        for old, new in self.tables.items():
            sql = sql.replace(old, new)
        return self.conn.execute(sql, params)


def init(conn):
    for profile in POLICIES:
        n = names(profile)
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {n['bob_paper_control']} (
            id INTEGER PRIMARY KEY CHECK(id=1), payload JSONB NOT NULL)""")
        seed=float(POLICIES[profile].get('initial_capital_eur',100.))
        # The experimental account starts with the first real deployment/initialization.
        # Existing live accounts retain their original Monday starting timestamps.
        policy=POLICIES[profile]
        started = (policy['start_at'] if policy.get('relaunch') else
                   int(time.time()*1000) if policy.get('early_impulse') or policy.get('campaign')
                   else START)
        starting = dict(version='paper-five-v1' if policy.get('early_impulse') else 'paper-four-v1',
                        startAt=started, enabled=True,
                        status='scheduled', portfolio=profile,
                        initialCapital=seed, cash=seed, equity=seed,
                        dayOpeningEquity=seed, dayProfit=0., totalProfit=0.,
                        realizedProfit=0., currency='EUR',
                        capitalPolicy='separate-whole-units-gross-v1')
        if policy.get('campaign'):
            starting.update(endAt=policy['campaign_end'], campaign=policy.get('campaign_id', 'signal-comparison-20261027'),
                            signalSource='ema25-paper-v1' if policy.get('relaxed_ema') else 'early-warning-v2' if policy.get('early_warning') else 'confirmed-main')
        conn.execute(f"""INSERT INTO {n['bob_paper_control']} (id,payload)
            VALUES(1,%s::jsonb) ON CONFLICT DO NOTHING""", (json.dumps(starting),))
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {n['bob_paper_cases']} (
            id TEXT PRIMARY KEY, day TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL,
            closed_at TIMESTAMPTZ, payload JSONB NOT NULL)""")
        conn.execute(f'CREATE INDEX IF NOT EXISTS bob_paper_{profile}_recent_idx ON {n["bob_paper_cases"]} (started_at DESC)')
        conn.execute(f"""CREATE INDEX IF NOT EXISTS bob_paper_{profile}_day_idx
            ON {n['bob_paper_cases']} (day,started_at)""")
        conn.execute(f"""CREATE INDEX IF NOT EXISTS bob_paper_{profile}_open_idx
            ON {n['bob_paper_cases']} (started_at) WHERE closed_at IS NULL""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {n['bob_paper_days']} (
            day TEXT PRIMARY KEY, payload JSONB NOT NULL)""")


def active_cases(conn):
    result = {}
    for profile in POLICIES:
        n = names(profile)
        row = conn.execute(f"""SELECT payload FROM {n['bob_paper_cases']}
                WHERE closed_at IS NULL ORDER BY started_at LIMIT 1""").fetchone()
        if row:
            result[profile] = row[0]
    return result


def entry_block_reason(policy, market):
    direction = market.get('direction')
    score = market.get('score')
    if policy.get('early_warning'):
        return None if market.get('paperEntrySource') == 'early-warning-paper-v2' and direction in ('LONG','SHORT') else 'Keine gültige aktuelle Frühwarnung'
    if policy.get('early_impulse'):
        if market.get('paperEntrySource')!='early-impulse-paper-v1':
            return 'Frühimpuls nicht auswertbar oder noch nicht bestätigt'
        return None if direction in ('LONG','SHORT') else 'Kein gültiges Frühimpuls-Signal'
    if direction not in ('LONG', 'SHORT') or type(score) not in (int, float) or not math.isfinite(score):
        return 'ABWARTEN: keine bestätigte Richtung'
    if direction == 'LONG' and score < policy['score_long']:
        return 'Kollektivrichtungswert für dieses Testkonto zu schwach'
    if direction == 'SHORT' and score > policy['score_short']:
        return 'Kollektivrichtungswert für dieses Testkonto zu schwach'
    if policy['require_trend']:
        trend = market.get('trendContext') or {}
        if (trend.get('available') is not True or trend.get('intact') is not True
                or trend.get('direction') != direction):
            return 'Konservativ: Haupttrend nicht bestätigt'
    return None


def early_paper_market(market, now):
    """Isolate early research hypothesis; do not alter confirmed market decisions.

    A signal alone never grants a product purchase. The gold stop/target must be
    created using actual checked bars by the shared background evaluator.
    """
    result={**market, 'direction':'NEUTRAL', 'plan':None, 'paperEntrySource':None,
            'warningPaperBlockReason':'Keine aktuelle gültige Frühwarnung oder zu stark ausgedehnte Bewegung'}
    impulse=market.get('earlyImpulse') or {}
    plan=market.get('earlyPaperPlan')
    valid=(market.get('ruleVersion')=='intraday-trend-follow-v7'
        and market.get('ready') is True and market.get('priceFresh') is True
        and type(market.get('dataAt')) in (int,float)
        and 0<=now-market['dataAt']<=60000
        and impulse.get('version')=='early-impulse-v1'
        and impulse.get('available') is True
        and impulse.get('comparisonOnly') is True
        and impulse.get('affectsApproval') is False
        and impulse.get('direction') in ('LONG','SHORT')
        and impulse.get('extensionRisk') is not True
        and type(impulse.get('barAt')) in (int,float)
        and 300000<=now-impulse['barAt']<=600000)
    if not valid:
        result['earlyPaperBlockReason']='Kein aktueller bestätigter Frühimpuls oder zu stark ausgedehnte Bewegung'
        return result
    if (not stop_target_audit.valid_plan(plan)
        or plan.get('kind')!='candidate'
        or plan.get('direction')!=impulse['direction']
        or plan.get('unit')!='USD/oz'
        or abs(plan['entry']-market.get('price',0))>0.01):
        result['earlyPaperBlockReason']=('Frühimpuls: '+market['earlyPaperPlanReason']
            if isinstance(market.get('earlyPaperPlanReason'),str) and market['earlyPaperPlanReason']
            else 'Frühimpuls vorhanden, aber kein gültiger unabhängiger Gold-Stop/Ziel-Plan')
        return result
    result.update(direction=impulse['direction'],plan=plan,
                  paperEntrySource='early-impulse-paper-v1',
                  decisionReason='Nur experimentelle '+impulse['direction']+'-Frühwarnung aus geschlossenen 5m/15m-Kerzen',
                  earlyPaperBlockReason=None)
    return result


def warning_paper_market(market, now):
    """Use exactly the displayed warning, retaining original signal clocks."""
    result={**market, 'direction':'NEUTRAL', 'plan':None, 'paperEntrySource':None}
    warning=market.get('earlyWarning') or {}
    plan=market.get('warningPaperPlan')
    valid=(market.get('ready') is True and market.get('priceFresh') is True
        and type(market.get('dataAt')) in (int,float) and 0<=now-market['dataAt']<=60000
        and warning.get('version')=='early-warning-v2' and warning.get('available') is True
        and warning.get('state') in ('active','watch') and warning.get('comparisonOnly') is True
        and warning.get('affectsApproval') is False and warning.get('extensionRisk') is not True
        and warning.get('direction') in ('LONG','SHORT')
        and type(warning.get('signalBarAt')) in (int,float)
        and type(warning.get('expiresAt')) in (int,float)
        and warning['signalBarAt']<=now<warning['expiresAt'])
    if not valid:
        return result
    result['warningPaperBlockReason']=(market.get('warningPaperPlanReason') or
        'Frühwarnung vorhanden, aber kein gültiger unabhängiger Gold-Stopp-/Zielplan')
    if stop_target_audit.valid_plan(plan) and plan.get('kind')=='candidate' and plan.get('unit')=='USD/oz' and plan['direction']==warning['direction'] and abs(plan['entry']-market.get('price',0))<=.01:
        result.update(direction=warning['direction'], plan=plan,
                      paperEntrySource='early-warning-paper-v2', analysisBarAt=warning['signalBarAt'],
                      warningPaperBlockReason=None)
    return result


def relaxed_paper_market(market):
    """Consume only the separately computed paper plan; never rewrite live input."""
    trial = market.get('relaxedPaper') or {}
    gate = trial.get('gate') or {}
    plan = trial.get('plan')
    valid = (trial.get('version') == 'ema25-paper-v1' and trial.get('paperOnly') is True
        and gate.get('paperOnly') is True and gate.get('maxDeviationAtr') == 2.5
        and gate.get('allowed') is True and stop_target_audit.valid_plan(plan)
        and plan.get('source') == 'ema25-paper-v1' and plan.get('experimental') is True
        and plan.get('direction') == market.get('direction')
        and plan.get('entry') == market.get('price'))
    return {**market, 'plan':copy.deepcopy(plan) if valid else None,
        'entryTimingGate':copy.deepcopy(gate), 'paperEntrySource':'ema25-paper-v1',
        'entryPlanState':{'state':'ready' if valid else 'waiting',
            'reason':trial.get('reason') or 'Getrennter EMA-Testplan noch nicht verfügbar'}}


def campaign_paper_market(market, profile):
    """Strict, scoped use of paper-only entry gates; never fabricate a fill.

    Older deployments without a campaign plan continue using their original
    market decision, rather than failing all simulations on a rollout.
    """
    source, distance = _PAPER_CAMPAIGN_GATES[profile]
    trial = (market.get('paperCampaignEntries') or {}).get(profile)
    if not isinstance(trial, dict) or trial.get('version') != 'campaign-entry-v1':
        return market
    gate = trial.get('gate') or {}
    plan = trial.get('plan')
    valid = (trial.get('paperOnly') is True
        and trial.get('profile') == profile and trial.get('source') == source
        and gate.get('paperOnly') is True and gate.get('paperProfile') == profile
        and gate.get('spotDistance') == distance and gate.get('maxSignalMinutes') == 20
        and gate.get('maxDeviationAtr') == 1.5 and gate.get('allowed') is True
        and market.get('ready') is True and market.get('priceFresh') is True
        and stop_target_audit.valid_plan(plan)
        and plan.get('kind') == 'candidate' and plan.get('experimental') is True
        and plan.get('source') == source and plan.get('direction') == market.get('direction')
        and plan.get('entry') == market.get('price')
        and plan.get('unit') == 'USD/oz' and plan.get('entrySuitable') is not False
        and abs(plan['target']-plan['entry']) >= 2*abs(plan['entry']-plan['stop'])-1e-7)
    state = trial.get('entryPlanState') or {}
    reason = (state.get('reason') if isinstance(state, dict) else None) or gate.get('reason')
    reason = reason or 'Separater Papier-Einstiegsplan noch nicht vollständig bestätigt'
    return {**market, 'plan': copy.deepcopy(plan) if valid else None,
        'entryTimingGate': copy.deepcopy(gate), 'paperEntrySource': source,
        'paperCampaignPreparation': copy.deepcopy(trial.get('preparation')),
        'entryPlanState': {'state': 'ready' if valid else 'waiting',
            'code': 'PAPER_PLAN_READY' if valid else 'PAPER_PLAN_NOT_READY',
            'reason': 'Separater Papierplan geprüft; Produktschutz bleibt Pflicht' if valid else reason}}


def run_all(conn, bundle, market, selection, quotes, now, settings, active=None, early_market=None, early_selection=None, input_observations=None, warning_market=None, warning_selection=None):
    """One savepoint per account: a failure does not consume another account's run.

    Feed/selection are observational inputs, never broker orders.
    """
    import background_push
    import paper_simulation
    active = active if active is not None else active_cases(conn)
    outcomes = {}
    for profile, policy in POLICIES.items():
        try:
            with conn.transaction():
                m = (early_market or early_paper_market(market,now)) if policy.get('early_impulse') else market
                chosen = (early_selection or {'choices':[], 'reasons':['Keine freigegebenen Frühimpuls-Produkte']}) if policy.get('early_impulse') else selection
                if policy.get('early_warning'):
                    m = warning_paper_market(market,now)
                    chosen = warning_selection or {'choices':[], 'reasons':['Keine freigegebenen Frühwarnprodukte']}
                if policy.get('paper_campaign_entry') and profile in _PAPER_CAMPAIGN_GATES:
                    m = campaign_paper_market(market, profile)
                if policy.get('relaxed_ema'):
                    m = relaxed_paper_market(market)
                if policy.get('disable_ema_distance'):
                    variant = market.get('paperNoEmaEntry') or {}
                    m = {**market, 'plan': variant.get('plan'),
                         'entryPlanState': variant.get('entryPlanState') or {'reason': 'EMA-Testanalyse nicht verfügbar'},
                         'entryTimingGate': variant.get('entryTimingGate') or {},
                         'paperEntrySource': 'no-ema-distance-paper-v1'}
                c = active.get(profile)
                if c and c.get('status') == 'open':
                    scoped = {**settings, 'trade': c['engine']['trade']}
                    monitoring = background_push.analyze(bundle, scoped, priority=2)
                    # Entry-only impulse does not overwrite ongoing position/KO protection.
                    m = monitoring
                paper_simulation.run_once(Ledger(conn, profile), bundle, m, chosen,
                                          quotes, now, profile_policy=policy)
            outcomes[profile] = 'checked'
            if input_observations is not None:
                try:
                    from paper_input_evidence import sanitized_profile
                    record = sanitized_profile(profile, m, 'checked')
                    if record is not None: input_observations.append(record)
                except Exception:
                    # The optional observation must not alter a successful ledger.
                    pass
        except Exception as exc:
            outcomes[profile] = 'error:' + type(exc).__name__
            if input_observations is not None:
                try:
                    from paper_input_evidence import sanitized_profile
                    record = sanitized_profile(profile, {}, 'error')
                    if record is not None: input_observations.append(record)
                except Exception:
                    pass
            print('BOB_PAPER_PROFILE profile=' + profile +
                  ' error=' + type(exc).__name__, flush=True)
    return outcomes


def performance_snapshot(data):
    """Compare only settled, quote-supported gross outcomes; never infer net P/L."""
    ctl=data.get('control') or {}
    days=data.get('daily') or []
    valid=all(d.get('performanceCountsValid') is not False and type(d.get('productKnown',0)) is int and type(d.get('productPositive',0)) is int and 0 <= d.get('productPositive',0) <= d.get('productKnown',0) for d in days)
    priced=sum(d.get('productKnown',0) for d in days) if valid else None
    positive=sum(d.get('productPositive',0) for d in days) if valid else None
    return dict(pricedTrades=priced,positivePricedTrades=positive,
        performanceCountsValid=valid,performanceExcluded=sum(d.get("inconclusive",0) for d in days),
        productPositiveRatePct=round(100*positive/priced,2) if priced else None,
        closedTrades=sum(d.get('closed',0) for d in days),
        inconclusiveTrades=sum(d.get('inconclusive',0) for d in days),
        observedMaxDrawdownPct=ctl.get('maxDrawdownPct'),
        currentDrawdownPct=ctl.get('currentDrawdownPct'),
        quoteMissingChecks=ctl.get('quoteMissingChecks',0),
        quoteConfirmedChecks=ctl.get('quoteConfirmedChecks',0),
        quoteStatus=ctl.get('quoteStatus','no-observation'),
        netReturnKnown=False,sampleBased=True)


def campaign_comparison(accounts):
    """Automatic read-time comparison from durable ledgers, not a strategy verdict."""
    rows=[]
    for profile in ('early1000oct','normal1000oct'):
        account=next((a for a in accounts if a.get('profile')==profile),{})
        c=account.get('control') or {}
        perf=account.get('performance') or {}
        rows.append(dict(profile=profile,status=c.get('status','unavailable'),
            startAt=c.get('startAt'),endAt=c.get('endAt'),checkedAt=c.get('checkedAt'),
            initialCapital=c.get('initialCapital'),equity=c.get('equity'),
            profitEur=c.get('totalProfit'),exampleCostsEur=c.get('costsDebitedEur'),
            closedTrades=perf.get('closedTrades'),pricedTrades=perf.get('pricedTrades'),
            inconclusiveTrades=perf.get('inconclusiveTrades'),
            observedMaxDrawdownPct=perf.get('observedMaxDrawdownPct'),
            forwardValidation=copy.deepcopy(c.get('forwardValidation'))))
    complete=all(r['status']=='completed' for r in rows)
    valid=complete and all(type(r['profitEur']) in (int,float) and math.isfinite(r['profitEur'])
        and r['inconclusiveTrades']==0 and type(r['pricedTrades']) is int
        and r['pricedTrades']>0 and r['pricedTrades']==r['closedTrades'] for r in rows)
    state=('completed' if valid else 'completed-insufficient-evidence') if complete else (
        'pending-exit-quotes' if any(r['status']=='ending-pending-quotes' for r in rows) else 'running-or-not-started')
    return dict(id='signal-comparison-20261027',state=state,endAt=CAMPAIGN_END,
        accounts=rows,differenceEarlyMinusMainEur=round(rows[0]['profitEur']-rows[1]['profitEur'],2) if valid else None,
        realOrders=False,strategyWinnerConfirmed=False,
        note='Virtueller Vergleich mit Beispielkosten; kein Nachweis künftiger Gewinne. Ohne vollständig bepreiste Abschlüsse kein Ergebnisvergleich.')


def relaunch_comparison(accounts):
    """Stored model balances only; no historical replay or winner certification."""
    rows = []
    for profile in ('trend800nov', 'normal1000nov'):
        a = next((item for item in accounts if item.get('profile') == profile), {})
        c, perf = a.get('control') or {}, a.get('performance') or {}
        start, equity = c.get('initialCapital'), c.get('equity')
        model_pct = (round(100 * (equity / start - 1), 4)
                     if type(start) in (int, float) and math.isfinite(start) and start > 0
                     and type(equity) in (int, float) and math.isfinite(equity) else None)
        rows.append(dict(profile=profile, status=c.get('status', 'unavailable'),
            startAt=c.get('startAt'), endAt=c.get('endAt'),
            initialCapitalEur=start, equityEur=equity,
            modelProfitEur=c.get('totalProfit'), modelReturnPct=model_pct,
            exampleCostsEur=c.get('costsDebitedEur'),
            closedTrades=perf.get('closedTrades'), pricedTrades=perf.get('pricedTrades'),
            inconclusiveTrades=perf.get('inconclusiveTrades'),
            maxDrawdownPct=perf.get('observedMaxDrawdownPct')))
    ended = all(r['status'] == 'completed' for r in rows)
    complete = (ended and all(r['modelReturnPct'] is not None
        and type(r['closedTrades']) is int and r['closedTrades'] > 0
        and r['closedTrades'] == r['pricedTrades'] and r['inconclusiveTrades'] == 0
        for r in rows))
    return dict(id=RELAUNCH_ID, readOnly=True, realOrders=False,
        startAt=RELAUNCH_START, endAt=RELAUNCH_END,
        status='completed-model-comparison-only' if complete else
               'completed-insufficient-evidence' if ended else
               'scheduled' if all(r['status']=='scheduled' for r in rows) else 'running-or-paused',
        accounts=rows, modelReturnDifferenceTrendMinusMainPctPoints=(
            round(rows[0]['modelReturnPct'] - rows[1]['modelReturnPct'], 4)
            if complete else None),
        comparableModelClosures=complete, strategyWinnerConfirmed=False,
        brokerNetVerified=False, noUnverifiedBackfill=True,
        note='Gleicher Beobachtungszeitraum, aber 800 EUR und 1.000 EUR Startkapital; '
             'primär prozentual vergleichen. Nur beobachtete Originalkurse für '
             'virtuelle Käufe/Verkäufe; angenommene Kosten, keine Broker-Fills. '
             'Fehlende Produktkurse und unvollständige Abschlüsse bleiben unbekannt. '
             'Kein Strategietestsieger oder Echtgeldauftrag.')


def report(conn, day=None):
    import paper_simulation
    accounts = []
    for profile, policy in POLICIES.items():
        data = paper_simulation.report(Ledger(conn, profile), day)
        # Six synthetic demos are already available under the separate demo tab.
        data.pop('demonstrations', None)
        data.pop('demonstration', None)
        import paper_stop_study
        if profile in paper_stop_study.PROFILES:
            data['stopStudy']=paper_stop_study.report(conn,data['day'],profile)
        if policy.get('early_impulse'):
            data['note']=('Viertes 100-EUR-Testkonto: früher LONG/SHORT-Impuls 5m/15m als eigenständiger virtueller '
                          'Einstiegsversuch, ohne Freigabe des Haupttrends. Dieselben echten Produktnachweise, '
                          'aktuelle Euro-Geld-/Briefkurse, gültige heutige Spot-KO-Barriere und Stop/Ziel-Prüfungen '
                          'sind Pflicht. Fehlende Voraussetzungen ergeben einen begründeten Nicht-Einstieg. '
                          'Historie erst ab Kontoaktivierung, keine rückdatierten Trades. Kein Echtgeld.')
        if policy.get('hold_trend'):
            data['note']=('Trendfolge über maximal acht Stunden bis 21:45 Zürich, '
                          'kein automatischer Teilverkauf am ersten Ziel, '
                          'nachgezogener Goldpreis-Stop und bestätigter Richtungswechsel; '
                          'EUR-Geldkurse dienen der virtuellen Produktbewertung. '
                          'KO-Sicherheitsausstieg nur bei verifizierter heutiger Barriere und frischem Euro-Geldkurs. '
                          'Kein garantierter Stop oder echter Orderfill.')
        if policy.get('bob_stop_reentry'):
            data['note']=('800-EUR-Test mit derselben Bob-Stopp-/Zielverwaltung wie die Haupt-Testkonten. '
                          'Bobs vorgeschlagener Stopp wird übernommen und niemals gelockert. '
                          'Nach einem Stopp: neuer bestätigter Signal-Kerzenschluss, vollständige '
                          'Produktfreigabe und frischer Geld-/Briefkurs vor dem Wiedereinstieg. '
                          'Fehlt der Verkaufskurs, bleibt das Kapital bis zur beobachteten Bewertung gebunden. '
                          'Nur virtuelle Trades, keine DEGIRO-Orders.')
        if policy.get('relaunch'):
            data['note']=('Neue getrennte Simulation von 09.11.2026 08:00 bis 04.12.2026 '
                '16:00 Europe/Zurich. Startgeld: '+str(int(policy['initial_capital_eur']))+
                ' EUR. Altkonto bleibt unverändert. Bestätigte Originalkurse, identische '
                'Produkt- und KO-Prüfungen, max. 65 % Exposure, Tagesgrenze 3 %, '
                'Beispielkosten und keine Echtgeldorders. Prozentuale Rendite und '
                'vollständig bepreiste Abschlüsse zuerst, unklare Ausstiege separat.')
        elif policy.get('campaign'):
            data['note']='1.000 EUR virtuell; '+('angezeigte Frühwarnung LONG/SHORT' if policy.get('early_warning') else 'bestätigtes Hauptsignal LONG/SHORT')+'; gleiche Rangliste, Kosten und Schutzregeln. Verlängert bis 06.11.2026 16:00 Europe/Zurich mit bestehendem Kapital und Historie. Fehlende Ausstiegskurse bleiben offen, keine rückdatierten Verkäufe.'
        if policy.get('relaxed_ema'):
            data['note']=('3.000 EUR virtuell ab erster Aktivierung bis 04.12.2026 16:00 Zürich. '
                'Nur EMA-Abstand auf 2,5 ATR gelockert; Signalalter, Impuls-, Quellen-, '
                'Produkt-, KO- und Stop/Ziel-Prüfungen bleiben erhalten. Maximal 65 % Exposure, '
                '3 % Tagesverlustgrenze und fünf Stunden Haltedauer. Beispielkosten; keine Broker-Fills, '
                'keine rückdatierten Einstiege. Eigenes Konto, keine Änderung der Hauptsignale.')
        if policy.get('disable_ema_distance'):
            data['note']='5.000 EUR virtuell ab Aktivierung bis 04.12.2026 16:00 Zürich. Nur die direkte EMA20-Abstandssperre ist aus. Signalalter, Impulsgrenze, Goldplan, Produkt-/KO-Schutz, Kosten und Tagesrisiko bleiben aktiv. Keine rückwirkenden Trades.'
        accounts.append(dict(profile=profile, title=policy['title'],
                             riskPolicy={k: policy[k] for k in ('exposure_fraction',
                                  'daily_loss_fraction','score_long','score_short',
                                  'require_trend')},
                             exitPolicy='bob-stop-reentry-v1' if policy.get('bob_stop_reentry') else 'trend-follow-v1' if policy.get('hold_trend') else 'bob-partial-target-v2',
                             performance=performance_snapshot(data),**data))
    return dict(ok=True, mode='independent-prospective-paper-accounts',
                simulatedCapitalEur=sum(p.get('initial_capital_eur',100.) for p in POLICIES.values()), realOrders=False, startAt=START,
                note='4 × 100 EUR, 2 × 800 EUR, 3 × 1.000 EUR, 1 × 3.000 EUR und 1 × 5.000 EUR virtuell. Alte Konten bleiben getrennt und unverändert. Neue 800/1.000 EUR Kohorte: gleicher 20-Handelstage-Zeitraum ab 09.11.2026. Kein Echtgeld und keine rückdatierten Einstiege. Ohne belegten Abrechnungswert bleiben Produktverlust und freies Kapital unbekannt. Tatsächliche Brokergebühren nicht bestätigt.',
                accounts=accounts,campaignComparison=campaign_comparison(accounts),
                relaunchComparison=relaunch_comparison(accounts))


def diagram_report(conn):
    """Bounded chart-only reads; never load case histories or run simulations."""
    accounts=[]
    fields=('capital','initialCapital','valuationKnown','observedMaxDrawdownPct','capitalAt')
    for profile,policy in POLICIES.items():
        ledger=Ledger(conn,profile)
        control=ledger.execute('SELECT payload FROM bob_paper_control WHERE id=1').fetchone()
        days=ledger.execute('SELECT day,payload FROM bob_paper_days ORDER BY day DESC LIMIT 366').fetchall()
        accounts.append(dict(profile=profile,title=policy['title'],
            control=dict(initialCapital=control[0].get('initialCapital')) if control else {},
            daily=[dict(day=day,**{k:data.get(k) for k in fields}) for day,data in days]))
    return dict(realOrders=False,accounts=accounts,daysLimit=366)
