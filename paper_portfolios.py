"""Three isolated, forward-only PAPER accounts. No brokerage endpoints.

All profiles consume the same timestamped observations; their ledger tables,
trade IDs, cash and risk decisions are kept separate in PostgreSQL. The existing
2026-10-08 paper study is retained as an archive and never used as a fourth
active account. Accounts begin at Monday 2026-10-12 08:00 Europe/Zurich.
"""
import copy
import json
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

    SQL substitution is restricted to three private paper-ledger tables.
    The shared, read-only quote universe stays bob_paper_products.
    """
    def __init__(self, conn, profile):
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
        starting = dict(version='paper-three-v1', startAt=START, enabled=True,
                        status='scheduled', portfolio=profile,
                        initialCapital=100., cash=100., equity=100.,
                        dayOpeningEquity=100., dayProfit=0., totalProfit=0.,
                        realizedProfit=0., currency='EUR',
                        capitalPolicy='separate-whole-units-gross-v1')
        conn.execute(f"""INSERT INTO {n['bob_paper_control']} (id,payload)
            VALUES(1,%s::jsonb) ON CONFLICT DO NOTHING""", (json.dumps(starting),))
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {n['bob_paper_cases']} (
            id TEXT PRIMARY KEY, day TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL,
            closed_at TIMESTAMPTZ, payload JSONB NOT NULL)""")
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
    if direction not in ('LONG', 'SHORT') or type(score) not in (int, float):
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


def run_all(conn, bundle, market, selection, quotes, now, settings, active=None):
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
                m = market
                c = active.get(profile)
                if c and c.get('status') == 'open':
                    scoped = {**settings, 'trade': c['engine']['trade']}
                    m = background_push.analyze(bundle, scoped, priority=2)
                paper_simulation.run_once(Ledger(conn, profile), bundle, m, selection,
                                          quotes, now, profile_policy=policy)
            outcomes[profile] = 'checked'
        except Exception as exc:
            outcomes[profile] = 'error:' + type(exc).__name__
            print('BOB_PAPER_PROFILE profile=' + profile +
                  ' error=' + type(exc).__name__, flush=True)
    return outcomes


def report(conn, day=None):
    import paper_simulation
    accounts = []
    for profile, policy in POLICIES.items():
        data = paper_simulation.report(Ledger(conn, profile), day)
        # Six synthetic demos are already available under the separate demo tab.
        data.pop('demonstrations', None)
        data.pop('demonstration', None)
        accounts.append(dict(profile=profile, title=policy['title'],
                             riskPolicy={k: policy[k] for k in ('exposure_fraction',
                                  'daily_loss_fraction','score_long','score_short',
                                  'require_trend')}, **data))
    return dict(ok=True, mode='three-independent-paper-accounts',
                simulatedCapitalEur=300, realOrders=False, startAt=START,
                note='Je Konto 100 EUR virtuell; historische Beobachtung, Bruttomodell ohne vollständige Gebühren, Finanzierung oder Slippage. Nicht als reale Order oder Nettogewinn interpretieren.',
                accounts=accounts)
