"""Prospective 3 x 2 entry/exit comparison with 0/30/60s execution delays.

Reuses validated issuer quotes, never broker execution. No live signal changes.
"""
import copy
import json
import math
from datetime import datetime
import paper_shadow_studies as shared

VERSION = 'entry-exit-v1'
ARMS = tuple(f'{entry}:{exit}:{delay}' for entry in ('early','confirmed','pullback')
             for exit in ('fixed','trailing') for delay in (0,30,60))
WINDOW = 3600000
HORIZON = 3 * WINDOW
GAP = 90000


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_entry_exit_comparison
        (id TEXT PRIMARY KEY, complete BOOLEAN NOT NULL, payload JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_entry_exit_input_status
        (singleton BOOLEAN PRIMARY KEY CHECK(singleton), payload JSONB NOT NULL)''')
    conn.execute('''CREATE INDEX IF NOT EXISTS bob_entry_exit_pending
        ON bob_entry_exit_comparison(id) WHERE complete=FALSE''')


def original_input(bundle, market, now):
    # The evaluator's confirmation clock is 5m even when its trend context is 15m.
    timeframe = '5m' if market.get('entryTiming') in (
        'five-minute-confirmation', 'two-minute-follow-through-v1') else '15m'
    quality = shared.original_input(bundle, market, now, timeframe)
    quality['signalTimeframe'] = timeframe
    quality['closedSignalBarMatched'] = quality.pop('closed15mMatched')
    if not quality['verified']:
        quality['reason'] = 'original-spot-or-'+timeframe+'-evidence-unverified'
    return quality


def active_isins(conn):
    rows=conn.execute('SELECT payload FROM bob_entry_exit_comparison WHERE complete=FALSE LIMIT 2').fetchall()
    return list({a['choice']['isin'] for (s,) in rows for a in s['arms'].values()
                 if a.get('choice') and a['status'] in ('pending','open','exit-pending')})


def bars5(bundle, now):
    bars=(((bundle or {}).get('history') or {}).get('bars_by_tf') or {}).get('5m') or []
    valid=sorted([b for b in bars if isinstance(b,dict) and b.get('instrument')=='XAU/USD'
        and b.get('isOpen') is False and b.get('providerIsOpen') is not True
        and b.get('estimated') is not True and shared.number(b.get('openTime'))
        and b['openTime']+300000<=now
        and all(shared.positive(b.get(k)) for k in ('open','high','low','close'))
        and b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']],
        key=lambda b:b['openTime'])[-3:]
    if len(valid)!=3 or any(b['openTime']-a['openTime']!=300000 for a,b in zip(valid,valid[1:])):
        return []
    return valid if 0<=now-(valid[-1]['openTime']+300000)<=300000 else []


def pullback(bundle, direction, now, since):
    b=bars5(bundle,now)
    if not b or b[-1]['openTime']+300000<=since:return False
    if direction=='LONG':
        return b[1]['close']<b[0]['close'] and b[2]['close']>b[1]['high']
    return b[1]['close']>b[0]['close'] and b[2]['close']<b[1]['low']


def seed(market, quality, now, direction):
    return dict(id=f"{VERSION}:{int(quality['analysisBarAt'])}:{direction}",version=VERSION,
        startedAt=now,sourceAt=quality['sourceAt'],barAt=quality['analysisBarAt'],
        direction=direction,regime=__import__('ranking_regimes').classify(market),
        ruleVersion=market.get('ruleVersion'),complete=False,checkedAt=now,
        realOrders=False,brokerExecutionVerified=False,actualNetKnown=False,
        arms={key:dict(status='waiting',reason='entry-trigger-missing') for key in ARMS})


def advance(state,bundle,market,selection,warning_market,warning_selection,quotes,now):
    from paper_simulation import fresh_quote,stamp
    import paper_ko_guard
    s=copy.deepcopy(state)
    # Keep this preregistered study in native EUR. Existing ledgers may accept
    # FX/chart projections, but those must never silently enter this comparison.
    quotes={isin:q for isin,q in quotes.items() if isinstance(q,dict)
            and q.get('currency')=='EUR' and not q.get('paperFxConversion')
            and (q.get('metadata') or {}).get('currency')!='CHF'
            and q.get('priceKind') not in ('calculated','issuer-chart')
            and q.get('estimated') is not True}
    quality=original_input(bundle,market,now)
    sign=1 if s['direction']=='LONG' else -1
    session=datetime.fromtimestamp(now/1000,shared.ZURICH)
    closing=(session.hour,session.minute)>=(21,45)
    for key,a in s['arms'].items():
        entry,exit_mode,delay_text=key.split(':');delay=int(delay_text)*1000
        if a['status'] in ('closed','inconclusive','no-entry'):continue
        if a['status']=='waiting':
            if now-s['startedAt']>=WINDOW or closing:
                a.update(status='no-entry',reason=a.get('reason','entry-window-ended'));continue
            m=warning_market if entry=='early' else market
            choices=warning_selection if entry=='early' else selection
            trigger=(m.get('direction')==s['direction'] and
                (entry!='early' or m.get('paperEntrySource')=='early-warning-paper-v2') and
                (entry!='pullback' or pullback(bundle,s['direction'],now,s['startedAt'])))
            if not quality['verified'] or not trigger:continue
            candidate,reason=shared.chosen_product(choices,quotes,m,now)
            if not candidate:
                a['reason']=reason;continue
            choice,raw,q,ko=candidate
            a.update(status='pending',decisionAt=now,dueAt=now+delay,
                decisionSourceAt=quality['sourceAt'],choice=copy.deepcopy(choice),
                plan=copy.deepcopy(m['plan']),entryKoEvidence=ko,
                triggerBars=bars5(bundle,quality['sourceAt']) if entry=='pullback' else [],
                reason='waiting-for-reaction-delay',signalSource=entry)
        if a['status']=='pending':
            if now>a['dueAt']+GAP or closing:
                a.update(status='no-entry',reason='entry-quote-or-signal-expired');continue
            if now<a['dueAt'] or not quality['verified']:continue
            plan=a['plan'];gold=quality['price']
            m=warning_market if entry=='early' else market
            if m.get('direction')!=s['direction']:
                a.update(status='no-entry',reason='signal-changed-during-delay');continue
            if sign*(gold-plan['stop'])<=0 or sign*(gold-plan['target'])>=0:
                a.update(status='no-entry',reason='frozen-plan-invalid-at-fill');continue
            candidate,reason=shared.chosen_product({'choices':[a['choice']]},quotes,
                {**m,'plan':plan},now)
            if not candidate:
                a['reason']=reason;continue
            choice,raw,q,ko=candidate
            ask_at=stamp(q.get('askAt'))
            if not shared.number(ask_at) or ask_at<a['dueAt']:continue
            units=math.floor((650-shared.PRODUCT_FEE_EUR)/(q['ask']*(1+shared.PRODUCT_SLIPPAGE)))
            if units<=0:
                a.update(status='no-entry',reason='whole-unit-budget');continue
            a.update(status='open',entryAt=now,entryQuoteAt=ask_at,
                entrySourceAt=quality['sourceAt'],entryAsk=q['ask'],entrySpot=gold,
                entryDebit=units*q['ask']*(1+shared.PRODUCT_SLIPPAGE)+shared.PRODUCT_FEE_EUR,
                units=units,stop=plan['stop'],target=plan['target'],entryKoEvidence=ko,
                lastSourceAt=quality['sourceAt'],lastBidAt=stamp(q['bidAt']),
                observedPeakPnlEur=0.,observedTroughPnlEur=0.,
                entryQuote=copy.deepcopy(q),reason='observed-issuer-model-fill')
            # Never execute an exit on the same observation as entry.
            continue
        if a['status'] not in ('open','exit-pending'):continue
        raw=quotes.get(a['choice']['isin']) or {}
        q=fresh_quote(raw,now,a['choice']['isin'])
        guard,blocker=paper_ko_guard.assess(a['choice'],raw,
            {**market,'plan':{'unit':'USD/oz','direction':s['direction']}},now)
        bid_at=stamp((q or {}).get('bidAt'))
        terminal=paper_ko_guard.terminal(raw,a['choice']['isin'])
        if terminal or (guard and guard['crossed']):
            a.update(status='inconclusive',reason='ko-or-settlement-unpriced',modelNetEur=None);continue
        good=(quality['verified'] and q and guard and blocker is None
              and shared.number(bid_at) and bid_at>=a['entryAt'])
        if (now-a['lastSourceAt']>GAP or now-a['lastBidAt']>GAP or
            (good and (quality['sourceAt']-a['lastSourceAt']>GAP or bid_at-a['lastBidAt']>GAP))):
            a.update(status='inconclusive',reason='original-observation-gap',modelNetEur=None);continue
        if not good:continue
        if quality['sourceAt']<=a['lastSourceAt'] or bid_at<a['lastBidAt']:continue
        a.update(lastSourceAt=quality['sourceAt'],lastBidAt=bid_at)
        pnl=a['units']*q['bid']*(1-shared.PRODUCT_SLIPPAGE)-shared.PRODUCT_FEE_EUR-a['entryDebit']
        a['observedPeakPnlEur']=max(a['observedPeakPnlEur'],pnl)
        a['observedTroughPnlEur']=min(a['observedTroughPnlEur'],pnl)
        gold=quality['price']
        reason=('stop' if sign*(gold-a['stop'])<=0 else
                'ko-safety' if guard.get('danger') else
                'target' if exit_mode=='fixed' and sign*(gold-a['target'])>=0 else
                'opposite-signal' if market.get('direction') in ('LONG','SHORT') and market['direction']!=s['direction'] else
                'time-limit' if now-a['entryAt']>=HORIZON or closing else None)
        if a['status']=='open' and reason:
            a.update(status='exit-pending',exitDecisionAt=now,exitDueAt=now+delay,reason=reason)
        if a['status']=='exit-pending' and now>=a['exitDueAt'] and bid_at>=a['exitDueAt']:
            a.update(status='closed',exitAt=now,exitQuoteAt=bid_at,exitSourceAt=quality['sourceAt'],
                exitBid=q['bid'],modelNetEur=pnl,exitQuote=copy.deepcopy(q),
                retainedPeakFraction=pnl/a['observedPeakPnlEur'] if a['observedPeakPnlEur']>0 else None)
        elif a['status']=='open' and exit_mode=='trailing':
            # Confirm middle-bar swing using the later closed bar. Test old stop first.
            b=bars5(bundle,quality['sourceAt'])
            if b and b[1]['openTime']>=a['entryAt']:
                pivot=(b[1]['low'] if s['direction']=='LONG' and b[1]['low']<min(b[0]['low'],b[2]['low']) else
                       b[1]['high'] if s['direction']=='SHORT' and b[1]['high']>max(b[0]['high'],b[2]['high']) else None)
                if pivot and sign*(pivot-a['stop'])>0 and sign*(gold-pivot)>0:
                    a.update(stop=pivot,stopConfirmedAt=b[2]['openTime']+300000)
                    a.setdefault('stopHistory',[]).append(dict(stop=pivot,confirmedAt=b[2]['openTime']+300000,bars=copy.deepcopy(b)))
    s.update(checkedAt=now,complete=all(a['status'] in ('closed','inconclusive','no-entry') for a in s['arms'].values()))
    return s


def tick(conn,bundle,market,selection,warning_market,warning_selection,quotes,now):
    # Two episodes maximum; bounded CPU, shared quotes and original candles.
    rows=conn.execute('SELECT id,payload FROM bob_entry_exit_comparison WHERE complete=FALSE ORDER BY id LIMIT 2 FOR UPDATE').fetchall()
    for key,s in rows:
        s=advance(s,bundle,market,selection,warning_market,warning_selection,quotes,now)
        conn.execute('UPDATE bob_entry_exit_comparison SET complete=%s,payload=%s::jsonb WHERE id=%s',
                     (s['complete'],json.dumps(s,allow_nan=False),key))
    quality=original_input(bundle,market,now)
    direction=warning_market.get('direction') if warning_market.get('paperEntrySource') else market.get('direction')
    reason = ('original-input-unverified' if not quality['verified'] else
              'waiting-for-direction' if direction not in ('LONG','SHORT') else
              'active-episode-limit' if len(rows)>=2 else
              'direction-already-active' if any(s['direction']==direction for _,s in rows) else
              'eligible-episode-input')
    observation = dict(checkedAt=now, inputQuality=quality, reason=reason,
                       direction=direction, realOrders=False)
    conn.execute('''INSERT INTO bob_entry_exit_input_status VALUES(TRUE,%s::jsonb)
        ON CONFLICT(singleton) DO UPDATE SET payload=EXCLUDED.payload''',
        (json.dumps(observation,allow_nan=False),))
    if len(rows)>=2 or not quality['verified'] or direction not in ('LONG','SHORT'):return
    if any(s['direction']==direction for _,s in rows):return
    s=seed(market,quality,now,direction)
    s=advance(s,bundle,market,selection,warning_market,warning_selection,quotes,now)
    conn.execute('INSERT INTO bob_entry_exit_comparison VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                 (s['id'],s['complete'],json.dumps(s,allow_nan=False)))


def report(conn):
    rows=conn.execute('SELECT payload FROM bob_entry_exit_comparison ORDER BY id DESC LIMIT 200').fetchall()
    samples=[s for (s,) in rows]
    counts={key:{status:sum(s['arms'][key]['status']==status for s in samples)
                 for status in ('waiting','pending','open','exit-pending','closed','inconclusive','no-entry')} for key in ARMS}
    for key,c in counts.items():
        profits=[s['arms'][key]['modelNetEur'] for s in samples if s['arms'][key]['status']=='closed']
        c.update(modelNetEur=sum(profits),expectancyEur=sum(profits)/len(profits) if profits else None)
    row=conn.execute('SELECT payload FROM bob_entry_exit_input_status WHERE singleton=TRUE').fetchone()
    observation=row[0] if row else None
    return dict(version=VERSION,status='collecting' if samples else
        'waiting-for-first-episode' if observation else 'awaiting-first-worker-check',
        inputObservation=observation,
        checkedAt=max((s['checkedAt'] for s in samples),default=None),episodesSampled=len(samples),
        truncated=len(samples)==200,variants=counts,realOrders=False,actualNetKnown=False,
        strategyWinnerConfirmed=False,automaticPolicyChanges=False,
        note='18 paper variants; issuer quotes, assumed fees/slippage, no verified broker net profit. Missing cases are not zero returns.')
