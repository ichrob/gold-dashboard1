"""Prospective isolated model-price PAPER trials, never the 800/1000 observed ledgers.

Virtual entry = hypothetical modeled ask from a recent independent original
product anchor. Model exits use original gold/FX observations but calculated
product bid values. Not a broker/issuer quote, fill or verified profit.
"""
import copy
import json
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = 'isolated-model-paper-v1'
PROFILES = {'trend800nov': 800.0, 'normal1000nov': 1000.0}
MAX_SOURCE_AGE_MS = 60000
MAX_ANCHOR_AGE_MS = 300000
MAX_HOLD_MS = 300*60000
ENTRY_EXPOSURE = .65
ENTRY_RISK = .01
DAILY_LOSS_LIMIT = .03
SIDE_SLIPPAGE = .002
FEE_EUR = 1.0


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def positive(v):
    return number(v) and v > 0


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.timestamp()*1000 if dt.tzinfo else None
    except (ValueError, OverflowError):
        return None


def fresh(value, now):
    at = timestamp(value)
    return at is not None and 0 <= now-at <= MAX_SOURCE_AGE_MS


def new_control(profile, now):
    capital = PROFILES[profile]
    return dict(version=VERSION, profile=profile, enabled=True,
        startedAt=now, checkedAt=now, status='collecting',
        initialCapitalEur=capital, cashEur=capital, modelEquityEur=capital,
        realizedModelProfitEur=0.0, completed=0, wins=0, losses=0,
        inconclusive=0, active=None, recent=[], lastSignalKey=None,
        day=None, dayOpeningEquity=capital, dayRealizedEur=0.0,
        originalTradesAltered=False, realOrders=False, brokerFills=0,
        originalNetVerified=False)


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_model_paper_trial (
        profile TEXT PRIMARY KEY, payload JSONB NOT NULL)""")
    now = int(time.time()*1000)
    for profile in PROFILES:
        conn.execute("""INSERT INTO bob_model_paper_trial(profile,payload)
            VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING""",
            (profile, json.dumps(new_control(profile, now))))


def original_spot(bundle, market, now):
    spots = bundle.get('spots') or {}
    at = timestamp(spots.get('spot_price_as_of'))
    price = spots.get('xaus')
    if (market.get('ready') is not True or market.get('priceFresh') is not True
            or spots.get('is_genuine_xauusd_spot') is not True
            or spots.get('spot_error') or not positive(price) or
            at is None or not 0 <= now-at <= MAX_SOURCE_AGE_MS or
            not positive(market.get('price')) or abs(market['price']-price) > .10):
        return None
    return price


def conversion(spots, currency, now):
    eur = (spots.get('usd_eur_meta') or {})
    chf = (spots.get('usd_chf_meta') or {})
    fx = eur if currency=='EUR' else chf if currency=='CHF' else {}
    observed_at = fx.get('fetchedAt') or fx.get('dataAt') or fx.get('at')
    if not positive(fx.get('rate')) or not fresh(observed_at,now):
        return None
    if currency=='EUR':
        return fx['rate'], 1.0
    euro_at = eur.get('fetchedAt') or eur.get('dataAt') or eur.get('at')
    if not positive(eur.get('rate')) or not fresh(euro_at,now):
        return None
    if abs(timestamp(observed_at)-timestamp(euro_at)) > 60000:
        return None
    return fx['rate'], eur['rate']/fx['rate']


def mode_candidate(row, market, spots, profile, now):
    """Return a strictly paper-only modeled entry; never promote the raw quote."""
    if not isinstance(row,dict) or row.get('modelMode')!='anchored-estimate' or (
            row.get('simulationPlanningUsable') is not True or
            row.get('simulationFillAllowed') is not False or
            row.get('available') is True):
        return None
    if row.get('planState')!='model-only-reference':
        return None
    direction = market.get('direction')
    trial = (market.get('paperCampaignEntries') or {}).get(profile) or {}
    plan = trial.get('plan') or {}
    gate = trial.get('gate') or {}
    if (direction not in ('LONG','SHORT') or row.get('direction')!=direction or
            trial.get('paperOnly') is not True or gate.get('allowed') is not True or
            plan.get('kind')!='candidate' or plan.get('direction')!=direction or
            plan.get('entrySuitable') is False or
            (market.get('session') or {}).get('entryAllowed') is not True):
        return None
    if not all(positive(row.get(k)) for k in ('modelEntry','modelStop','modelTarget',
            'modelGoldEntry','modelGoldStop','modelGoldTarget','modelRatio',
            'modelStrike','modelKo','modelFxRate')):
        return None
    if not row['modelStop']<row['modelEntry']<row['modelTarget']:
        return None
    sign = 1 if direction=='LONG' else -1
    gold = row['modelGoldEntry']
    # Model-based entry still needs the full KO protection buffer.
    # A stop infinitesimally above the barrier is not a safe market exit.
    atr = market.get('atr') if positive(market.get('atr')) else 0.0
    ko_distance = sign*(gold-row['modelKo'])
    protective_gap = max(.02*gold,1.5*atr+.005*gold)
    if not (ko_distance>protective_gap and
            sign*(row['modelGoldStop']-row['modelKo'])>.005*gold and
            sign*(gold-row['modelStrike'])>0 and
            sign*(row['modelGoldStop']-row['modelStrike'])>0 and
            sign*(row['modelGoldTarget']-gold)>0 and sign*(gold-row['modelGoldStop'])>0 and
            sign*(row['modelGoldTarget']-gold)>=2*sign*(gold-row['modelGoldStop'])):
        return None
    anchor_at = timestamp(row.get('modelReferenceAt'))
    if (anchor_at is None or not 0<=now-anchor_at<=MAX_ANCHOR_AGE_MS or
            abs(gold-market['price'])>.10 or abs(gold-plan.get('entry',0))>.10 or
            row.get('modelInputAgeSeconds') is None or
            not number(row['modelInputAgeSeconds']) or
            not 0<=row['modelInputAgeSeconds']<=60 or
            not number(row.get('modelAnchorAgeSeconds')) or
            not 0<=row['modelAnchorAgeSeconds']<=300 or
            not fresh(row.get('modelOriginalGoldAt'),now) or
            not fresh(row.get('modelFxAt'),now)):
        return None
    fx = conversion(spots,row.get('modelCurrency'),now)
    if not fx or abs(fx[0]-row['modelFxRate'])>0.0002:
        return None
    if not isinstance(row.get('isin'),str) or len(row['isin'])!=12:
        return None
    # Compare source-linked gold stop against the paper plan, not just a
    # possibly unrelated row with a coincidentally matching direction.
    if (abs(row['modelGoldStop']-plan['stop']) > max(1.,.25*abs(gold-plan['stop'])) or
            abs(row['modelGoldTarget']-plan['target']) > max(2.,.25*abs(gold-plan['target']))):
        return None
    return dict(row, fxCurrency=fx[0], eurPerCurrency=fx[1])


def priced_bid(position, gold, fx_currency):
    sign = 1 if position['direction']=='LONG' else -1
    ratio, strike = position['ratio'], position['strike']
    return max(0.0, position['startingModelBid']+sign*ratio*(
        (gold-strike)*fx_currency-(position['goldEntry']-strike)*position['fxAtEntry']))


def evolve(control, market, bundle, audit, now):
    """Pure, no DB/side effects. Never turns a model observation into a fill."""
    control = copy.deepcopy(control)
    c = control
    c['checkedAt']=now
    profile=c['profile']
    date = datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich')).date().isoformat()
    if c.get('day')!=date:
        c['day']=date
        c['dayOpeningEquity']=c.get('modelEquityEur') if positive(c.get('modelEquityEur')) else c['cashEur']
        c['dayRealizedEur']=0.0
    gold=original_spot(bundle,market,now)
    spots=bundle.get('spots') or {}
    position=c.get('active')
    if position:
        # No original market/FX observation => keep exposure unresolved.
        fx=conversion(spots,position['currency'],now) if gold is not None else None
        if not fx:
            c.update(status='valuation-pending',modelEquityEur=None,
                reason='Originaler Gold-/FX-Kurs fehlt; virtueller Modellausstieg nicht nachträglich erfunden')
            return c
        sign=1 if position['direction']=='LONG' else -1
        bid=priced_bid(position,gold,fx[0])
        conversion_rate=fx[1]
        remaining=max(0.0,bid*(1-SIDE_SLIPPAGE)*conversion_rate)*position['quantity']
        c['modelEquityEur']=round(c['cashEur']+remaining,4)
        hit_ko = sign*(gold-position['ko'])<=0
        hit_stop = sign*(gold-position['goldStop'])<=0
        hit_target = sign*(gold-position['goldTarget'])>=0
        timed_out=now-position['enteredAt']>=MAX_HOLD_MS
        if not (hit_ko or hit_stop or hit_target or timed_out):
            c.update(status='model-position-open',
                     reason='Modellposition offen; Original-Spot/FX frisch, Modellbewertung hypothetisch')
            return c
        # Model-only settlement, from a current original spot/FX *and* frozen
        # entry model. Neither bid nor slippage is a dealer execution price.
        received=0.0 if hit_ko else max(0.0,remaining-FEE_EUR)
        c['cashEur']=round(c['cashEur']+received,4)
        outcome=(received-position['costEur'])
        c['realizedModelProfitEur']=round(c['realizedModelProfitEur']+outcome,4)
        c['dayRealizedEur']=round(c['dayRealizedEur']+outcome,4)
        c['completed']+=1
        c['wins']+=int(outcome>0)
        c['losses']+=int(outcome<=0)
        ending='model-ko' if hit_ko else 'model-stop' if hit_stop else 'model-target' if hit_target else 'model-time-limit'
        record={k:position[k] for k in ('isin','currency','direction','enteredAt',
            'entryModelEur','goldEntry','goldStop','goldTarget','quantity')}
        record.update(status=ending,closedAt=now,modelExitEur=round(received,4),
            modelReturnEur=round(outcome,4),originalSourceAt=spots.get('spot_price_as_of'),
            modelOnly=True,brokerFillVerified=False,productNetVerified=False)
        c['recent']=(c.get('recent') or [])[-19:]+[record]
        c['active']=None
        c['modelEquityEur']=c['cashEur']
        c.update(status='collecting',reason='Rechnerischer Modellausstieg – keine DEGIRO-Ausführung')
        return c
    if gold is None:
        c.update(status='waiting',reason='Originaler Gold-Spot fehlt oder ist veraltet')
        return c
    if market.get('direction') not in ('LONG','SHORT') or market.get('ready') is not True:
        c.update(status='waiting',reason='Keine bestätigte gültige Marktrichtung')
        return c
    if (market.get('entryPlanState') or {}).get('code')=='TARGET_OBSTACLE':
        c.update(status='waiting',reason='Unterstützung/Zielhindernis – Modelltrade nicht freigegeben')
        return c
    trial=(market.get('paperCampaignEntries') or {}).get(profile) or {}
    if not (trial.get('gate') or {}).get('allowed'):
        c.update(status='waiting',reason='PAPER-Einstiegsfilter nicht erfüllt')
        return c
    if not (isinstance(audit,dict) and audit.get('current') is True):
        c.update(status='waiting',reason='Aktueller Modellplan-Nachweis fehlt')
        return c
    day_limit=-DAILY_LOSS_LIMIT*c['dayOpeningEquity']
    if c['dayRealizedEur']<=day_limit:
        c.update(status='waiting',reason='Modell-Tagesverlustgrenze erreicht')
        return c
    signal_key=str((market.get('ruleVersion'),market.get('analysisBarAt'),market['direction']))
    if c.get('lastSignalKey')==signal_key:
        c.update(status='waiting',reason='Diese Bestätigungskerze bereits als Modellfall ausgewertet')
        return c
    candidates=[mode_candidate(x,market,spots,profile,now) for x in audit.get('items',[])[:12]]
    candidates=[x for x in candidates if x]
    if not candidates:
        c.update(status='waiting',reason='Kein aktueller validiert verankerter Produkt-Modellkurs für virtuelle Ausführung')
        return c
    for row in candidates:
        bid=row['modelStop']+(1 if market['direction']=='LONG' else -1)*row['modelRatio']*row['modelFxRate']*(
            gold-row['modelGoldStop'])
        if not 0<bid<row['modelEntry']:
            # Do not force product spreads: a nonpositive anchored bid is a
            # bad model, not a reason to create an imaginary paper purchase.
            continue
        entry_eur=row['modelEntry']*row['eurPerCurrency']
        risk_eur=max(.01,(row['modelEntry']-row['modelStop'])*row['eurPerCurrency'])
        penalty=max(entry_eur*SIDE_SLIPPAGE,.01)
        cost_per=entry_eur*(1+SIDE_SLIPPAGE)
        max_budget=min(c['cashEur'],c['modelEquityEur']*ENTRY_EXPOSURE)
        risk_budget=c['modelEquityEur']*ENTRY_RISK
        qty=min(math.floor((max_budget-FEE_EUR)/cost_per),
                math.floor((risk_budget-2*FEE_EUR)/(risk_eur+2*penalty)))
        if qty<1:
            continue
        cost=round(qty*cost_per+FEE_EUR,4)
        if cost>c['cashEur']:
            continue
        c['cashEur']=round(c['cashEur']-cost,4)
        c['active']=dict(isin=row['isin'],currency=row['modelCurrency'],
            direction=market['direction'],quantity=qty,enteredAt=now,
            entryModelEur=round(entry_eur,4),goldEntry=gold,
            goldStop=row['modelGoldStop'],goldTarget=row['modelGoldTarget'],
            ko=row['modelKo'],strike=row['modelStrike'],ratio=row['modelRatio'],
            fxAtEntry=row['modelFxRate'],startingModelBid=bid,
            modelMode=row['modelMode'],referenceAt=row.get('modelReferenceAt'),
            originalGoldAt=row.get('modelOriginalGoldAt'),
            observedProductFill=False,modelOnly=True,costEur=cost,
            brokerFillVerified=False,productNetVerified=False)
        c['lastSignalKey']=signal_key
        c['modelEquityEur']=round(c['cashEur']+qty*bid*(1-SIDE_SLIPPAGE)*row['eurPerCurrency'],4)
        c.update(status='model-position-open',
            reason='Rechnerischer Modell-Einstieg; Preis nicht als DEGIRO-Ausführung bestätigt')
        return c
    c.update(status='waiting',reason='Modellpreis vorhanden, aber Risikobudget/Stückzahl ungeeignet')
    return c


def tick(conn, market, bundle, evidence, now=None):
    import handset_planning
    now=int(time.time()*1000 if now is None else now)
    plans=handset_planning.read(conn)
    report=plans.get('result') or {}
    current=bool(plans.get('resultFresh') and
        report.get('listUploadedAt')==evidence.get('listUploadedAt') and
        0<=now-report.get('calculatedAt',0)<=90000)
    audit=dict(current=current,items=report.get('items') or [])
    for profile in PROFILES:
        row=conn.execute('SELECT payload FROM bob_model_paper_trial WHERE profile=%s FOR UPDATE',(profile,)).fetchone()
        if not row or not isinstance(row[0],dict):
            continue
        current_control=evolve(row[0],market,bundle,audit,now)
        conn.execute('UPDATE bob_model_paper_trial SET payload=%s::jsonb WHERE profile=%s',
            (json.dumps(current_control,allow_nan=False),profile))


def report(conn):
    rows=conn.execute('SELECT profile,payload FROM bob_model_paper_trial WHERE profile=ANY(%s::text[]) ORDER BY profile',(list(PROFILES),)).fetchall()
    accounts=[]
    for profile,control in rows[:2]:
        accounts.append(dict(profile=profile,initialCapitalEur=PROFILES.get(profile),
            modelCashEur=control.get('cashEur'),modelEquityEur=control.get('modelEquityEur'),
            realizedModelProfitEur=control.get('realizedModelProfitEur'),
            status=control.get('status'),reason=control.get('reason'),
            checkedAt=control.get('checkedAt'),startedAt=control.get('startedAt'),
            completed=control.get('completed'),wins=control.get('wins'),
            losses=control.get('losses'),
            openModeledCase=bool(control.get('active')),
            currentIsin=(control.get('active') or {}).get('isin'),
            originalTradesAltered=False,realOrders=False,
            brokerFills=0,productNetVerified=False))
    return dict(status='observed' if len(accounts)==len(PROFILES) else 'partial',
        version=VERSION,accounts=accounts,readOnly=True,realOrders=False,
        scope='prospective-independent-model-paper-ledgers-unverified-prices',
        note='Hypothetische Ein-/Ausstiege aus Modellwerten. Kein beobachteter Emittentenfill und keine belegte Produkt-Nettorendite.')
