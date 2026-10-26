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
        started = int(time.time()*1000) if policy.get('early_impulse') else START
        starting = dict(version='paper-five-v1' if policy.get('early_impulse') else 'paper-four-v1',
                        startAt=started, enabled=True,
                        status='scheduled', portfolio=profile,
                        initialCapital=seed, cash=seed, equity=seed,
                        dayOpeningEquity=seed, dayProfit=0., totalProfit=0.,
                        realizedProfit=0., currency='EUR',
                        capitalPolicy='separate-whole-units-gross-v1')
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
    result={**market, 'direction':'NEUTRAL', 'plan':None, 'paperEntrySource':None}
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


def run_all(conn, bundle, market, selection, quotes, now, settings, active=None, early_market=None, early_selection=None, input_observations=None):
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


def report(conn, day=None):
    import paper_simulation
    accounts = []
    for profile, policy in POLICIES.items():
        data = paper_simulation.report(Ledger(conn, profile), day)
        # Six synthetic demos are already available under the separate demo tab.
        data.pop('demonstrations', None)
        data.pop('demonstration', None)
        if profile=='balanced':
            import paper_stop_study
            data['stopStudy']=paper_stop_study.report(conn,data['day'])
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
        accounts.append(dict(profile=profile, title=policy['title'],
                             riskPolicy={k: policy[k] for k in ('exposure_fraction',
                                  'daily_loss_fraction','score_long','score_short',
                                  'require_trend')},
                             exitPolicy='bob-stop-reentry-v1' if policy.get('bob_stop_reentry') else 'trend-follow-v1' if policy.get('hold_trend') else 'bob-partial-target-v2',
                             performance=performance_snapshot(data),**data))
    return dict(ok=True, mode='five-independent-paper-accounts',
                simulatedCapitalEur=1200, realOrders=False, startAt=START,
                note='4 × 100 EUR plus 1 × 800 EUR virtuell. Der ursprüngliche manuelle 800-EUR-Test bleibt separat. KO-Schutz verlangt eine bestätigte heutige Spot-Barriere und aktuelle Euro-Kurse; er garantiert keinen rechtzeitigen Ausstieg. Ohne belegten Abrechnungswert bleiben Produktverlust und freies Kapital offen. Neue Einstiege ab 19.10.2026 mit Beispielkosten direkt im Spielgeld; frühere Fälle unverändert. Tatsächliche Brokergebühren unbekannt.',
                accounts=accounts)


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
