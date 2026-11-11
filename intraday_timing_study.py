"""Frozen prospective intraday hypotheses; reference spot models, never live gates.

One shared minute source, causal closed-bar aggregation, bounded state/case journal.
No extra fetches, fitted parameters, broker actions or automatic rule promotion.
"""
import copy
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from paper_shadow_studies import number, positive

LEGACY_VERSION = 'intraday-timing-20261106-v1'
VERSION = 'intraday-timing-20261106-v2'
EXIT_POLICY = 'confirmed-reversal-exit-v1'
MINUTE = 60000
HORIZONS = (30, 180, 300)
MAX_CASES = 200
DAYS = 20
COST_PCT = .16  # illustrative round trip reference-spot cost, NOT KO/DEGIRO cost
VARIANTS = {
    'base5': dict(minutes=5, label='5m · strenge Bestätigung'),
    'fast3': dict(minutes=3, label='3m · strenge Bestätigung'),
    'control7': dict(minutes=7, label='7m · strenge Bestätigung'),
    'neutral5': dict(minutes=5, neutral=True, label='5m · neutraler Stundentrend erlaubt'),
    'noema5': dict(minutes=5, omit='ema', label='5m · ohne zusätzliche EMA-Bedingung'),
    'nomacd5': dict(minutes=5, omit='macd', label='5m · ohne zusätzliche MACD-Bedingung'),
    'pullback5': dict(minutes=5, pullback=True, label='5m · Rücksetzer nach Ausbruch'),
    'timestop5': dict(minutes=5, time_stop=True, label='5m · Zeitstopp bei fehlendem Fortschritt'),
    # Added prospectively, without resetting the ongoing 48 original study arms.
    # A NEW closed 5m push is evaluated on its own clock, not by refreshing an old 15m signal.
    'follow5': dict(minutes=5, continuation=True,
                    label='5m · frischer Folgeimpuls LONG/SHORT (30–300 Minuten)'),
    # New forward-only arms. Old cases remain immutable and keep their original rule.
    'fast3neutral': dict(minutes=3, neutral=True,
                         label='3m · schneller Einstieg bei neutralem 1h-Kontext'),
    'follow5neutral': dict(minutes=5, continuation=True, neutral=True,
                           label='5m · frischer Folgeimpuls bei neutralem 1h-Kontext'),
    'score65': dict(minutes=5, score_long=65, score_short=35,
                    label='5m · Kollektivrichtungswert 65/35'),
    'score70': dict(minutes=5, score_long=70, score_short=30,
                    label='5m · Kollektivrichtungswert 70/30'),
    'rr20': dict(minutes=5, min_remaining_rr=2.0,
                 label='5m · Mindestzielabstand 2,0R (Vergleich zu 1,5R)'),
    'breakeven5': dict(minutes=5, protective_exit='break-even',
                       label='5m · Einstandsstopp erst nach beobachtetem +1R'),
    'trailatr5': dict(minutes=5, protective_exit='atr-trailing',
                      label='5m · ATR-Gewinnschutz nach beobachtetem +1,5R'),
}
NOTE = ('Vorwärts-Test auf Gold-Spot, keine KO-Produktrendite. 0,16 % Gesamtkosten sind eine Annahme. '
        'Original- und Schätzfälle getrennt; Verluste und Stops nur an beobachteten Kursen. '
        'Keine automatische Übernahme oder bestätigte Überlegenheit. Unterschiedliche Einstiegszeiten, '
        'keine Behauptung gepaarter Trades. 5m ist die Studienreferenz, nicht die vollständige Bob-Hauptlogik. '
        'Folgeimpuls5 läuft erst ab Aktivierung als separate Beobachtungsvariante; kein Live-Einstieg, '
        'keine KO-Produktfreigabe, keine rückwirkend erfundenen Gewinne.')


def session(at):
    d = datetime.fromtimestamp(at/1000, ZoneInfo('Europe/Zurich'))
    return d.weekday() < 5 and 8 <= d.hour < 22


def minute_history(bundle, now, modeled=False):
    """Last 120 closed minutes; max TWO causal missing minutes in modeled stream.

    Fixed UTC epoch bucket origin for all 3/5/7m series (never sliding windows).
    Conflicts/malformed/provider-open data cannot be repaired as missing candles.
    """
    raw = (((bundle or {}).get('history') or {}).get('bars_by_tf') or {}).get('1m') or []
    end = int(now//MINUTE)*MINUTE
    start = end-120*MINUTE
    by_time = {}
    for b in raw:
        if not isinstance(b, dict) or not number(b.get('openTime')):
            continue
        t = b['openTime']
        if not start <= t < end:
            continue
        if (t % MINUTE or t in by_time or b.get('instrument') != 'XAU/USD'
                or b.get('isOpen') is not False or b.get('providerIsOpen') is True
                or b.get('estimated') is True
                or not all(positive(b.get(k)) for k in ('open', 'high', 'low', 'close'))
                or not b['low'] <= min(b['open'], b['close']) <= max(b['open'], b['close']) <= b['high']):
            return [], 'minute-evidence-invalid'
        by_time[t] = b
    rows = []; missing = 0
    sources = {b.get('source') for b in by_time.values()}
    if len(sources) > 1:
        return [], 'mixed-minute-sources'
    for t in range(start, end, MINUTE):
        b = by_time.get(t)
        if b is None:
            missing += 1
            if not modeled or missing > 2 or not rows or not session(t) or not session(t-MINUTE):
                return [], 'minute-history-gap'
            p = rows[-1]['close']
            b = dict(openTime=t, open=p, high=p, low=p, close=p, estimated=True,
                     originalSourceAt=rows[-1].get('originalSourceAt', rows[-1]['openTime']),
                     model='causal-minute-carry-v1')
        rows.append(dict(b))
    return rows, None


def aggregate(rows, minutes, now):
    step = minutes*MINUTE
    buckets = {}
    for b in rows:
        key = int(b['openTime']//step)*step
        buckets.setdefault(key, []).append(b)
    out = []
    for key, bars in sorted(buckets.items()):
        if (key+step > now or len(bars) != minutes or
                any(b['openTime'] != key+i*MINUTE for i,b in enumerate(bars))):
            continue
        out.append(dict(openTime=key, closeTime=key+step, open=bars[0]['open'],
                        close=bars[-1]['close'], high=max(b['high'] for b in bars),
                        low=min(b['low'] for b in bars), estimated=any(b.get('estimated') for b in bars)))
    return out


def ema(values, period):
    out = []; last = values[0]
    for value in values:
        last += 2/(period+1)*(value-last)
        out.append(last)
    return out


def frame_signal(rows, minutes, now, pullback=False):
    bars = aggregate(rows, minutes, now)
    if len(bars) < 3:
        return dict(available=False, reason='closed-bars-missing')
    b = bars[-1]
    anchor = bars[-3] if pullback else b
    prior = [r for r in rows if anchor['openTime']-15*MINUTE <= r['openTime'] < anchor['openTime']]
    past = [r for r in rows if b['closeTime']-105*MINUTE <= r['openTime'] < b['closeTime']]
    if len(prior) != 15 or len(past) != 105:
        return dict(available=False, reason='normalized-lookback-missing')
    hi, lo = max(r['high'] for r in prior), min(r['low'] for r in prior)
    side = 'LONG' if anchor['close'] > hi else 'SHORT' if anchor['close'] < lo else None
    if pullback and side:
        middle = bars[-2]
        valid = (middle['low'] <= hi and middle['close'] < anchor['close'] and b['close'] > middle['high']
                 if side == 'LONG' else middle['high'] >= lo and middle['close'] > anchor['close'] and b['close'] < middle['low'])
        if not valid:
            side = None
    close = [r['close'] for r in past]
    e20, e50 = ema(close,20)[-1], ema(close,50)[-1]
    macd = [a-b for a,b in zip(ema(close,12),ema(close,26))]
    hist = macd[-1]-ema(macd,9)[-1]
    five = aggregate(past,5,b['closeTime'])[-15:]
    if len(five) != 15:
        return dict(available=False, reason='common-atr-missing')
    atr = sum(max(y['high']-y['low'],abs(y['high']-x['close']),abs(y['low']-x['close']))
              for x,y in zip(five,five[1:]))/14
    return dict(available=positive(atr), direction=side, barAt=b['openTime'], closedAt=b['closeTime'],
                ema='LONG' if e20>e50 else 'SHORT' if e20<e50 else 'NEUTRAL',
                macd='LONG' if hist>0 else 'SHORT' if hist<0 else 'NEUTRAL', atr=atr,
                estimated=any(r.get('estimated') for r in past),
                level=hi if side=='LONG' else lo, reason=None if side else 'no-breakout')


def fresh_continuation_signal(rows, now):
    """Independent *prospective* LONG/SHORT re-entry hypothesis, not an approval.

    A genuinely NEW, fully closed five-minute candle can confirm a continuation
    even when the original 15-minute breakout is older. Do not recycle/reset the
    older signal's timestamp. Require two prior closed 5m bars, correct 1m source,
    fresh close and an extension cap; the shared hour/EMA/MACD, reference-price,
    cost and stop gates remain in place in gate()/advance().
    """
    base = frame_signal(rows, 5, now)
    if base.get('available') is not True or not positive(base.get('atr')):
        return base
    bars = aggregate(rows, 5, now)
    if len(bars) < 3:
        return {**base, 'direction':None, 'reason':'continuation-closed-bars-missing'}
    last, previous, older = bars[-1], bars[-2], bars[-3]
    if (last['closeTime'] != base.get('closedAt')
            or not 0 <= now-last['closeTime'] <= 90000):
        return {**base, 'direction':None, 'reason':'continuation-signal-not-fresh'}
    past = [r for r in rows if last['closeTime']-105*MINUTE <= r['openTime'] < last['closeTime']]
    if len(past) != 105:
        return {**base, 'direction':None, 'reason':'continuation-original-lookback-missing'}
    e20 = ema([r['close'] for r in past],20)[-1]
    stretch = abs(last['close']-e20)/base['atr']
    # Still restrict chasing overextended trends even in the experimental arm.
    if stretch > 2.0:
        return {**base, 'direction':None, 'reason':'continuation-overextended-2atr',
                'extensionAtr':round(stretch,4)}
    side = base.get('direction')
    if side in ('LONG','SHORT'):
        setup = 'fresh-breakout'
        level = base.get('level')
    else:
        minimum_body = .2*base['atr']
        growing = (previous['close'] > older['close'] and last['close'] > previous['high']
                   and last['close'] > last['open'] and last['close']-last['open'] >= minimum_body
                   and last['close'] > e20)
        falling = (previous['close'] < older['close'] and last['close'] < previous['low']
                   and last['close'] < last['open'] and last['open']-last['close'] >= minimum_body
                   and last['close'] < e20)
        side = 'LONG' if growing else 'SHORT' if falling else None
        setup = 'closed-5m-follow-through'
        level = previous['high'] if growing else previous['low'] if falling else None
    return {**base, 'direction':side, 'barAt':last['openTime'],
            'closedAt':last['closeTime'], 'level':level,
            'setup':setup if side else None, 'extensionAtr':round(stretch,4),
            'reason':None if side else 'no-fresh-continuation'}


def score_gate(signal, market, config):
    """Apply only optional study score arms; never change the main Bob score gate."""
    if 'score_long' not in config:
        return True, None
    score=market.get('score')
    if not number(score):
        return False, 'collective-score-unavailable'
    side=signal.get('direction')
    if (side=='LONG' and score<config['score_long'] or
        side=='SHORT' and score>config['score_short']):
        return False, 'collective-score-too-weak'
    return True, None


def target_room(target, price, risk, side, config):
    """A future risk-adjusted target, never a presumed product fill."""
    if not positive(target) or not positive(price) or not positive(risk):
        return False
    return (1 if side=='LONG' else -1)*(target-price)/risk >= config.get('min_remaining_rr',1.5)


def gate(signal, trend, config):
    if not signal.get('available'):
        return False, signal.get('reason','signal-input-missing')
    side = signal.get('direction')
    if side not in ('LONG','SHORT'):
        return False, 'no-setup'
    if trend.get('available') is not True or trend.get('direction') not in ('LONG','SHORT','NEUTRAL'):
        return False, 'hour-context-missing'
    hour = trend['direction']
    if hour != side and not (hour == 'NEUTRAL' and config.get('neutral')):
        return False, 'hour-neutral' if hour=='NEUTRAL' else 'hour-opposed'
    for name in ('ema','macd'):
        if config.get('omit') != name and signal.get(name) != side:
            return False, name+'-not-confirmed'
    return True, None


def reversal_evidence(rows, minutes, now, position, market, price):
    """Exit permission is independent of entry gates and hourly alignment.

    Either the existing main signal confirms the opposite direction on this
    source sample, or two consecutive closed local bars agree in EMA/MACD.
    A warning, neutral state, missing context or a single counter-bar is not enough.
    """
    opposite = 'SHORT' if position['direction']=='LONG' else 'LONG'
    if (market.get('ready') is True and market.get('priceFresh') is True
            and market.get('direction')==opposite and number(market.get('dataAt'))
            and abs(market['dataAt']-price['at'])<=2000 and not price['estimated']
            and number(market.get('analysisBarAt'))
            and position['entryObservedAt'] < market['analysisBarAt']+5*MINUTE <= price['at']):
        return dict(policy=EXIT_POLICY,kind='confirmed-main-opposite',direction=opposite,
                    confirmedAt=market['analysisBarAt']+5*MINUTE,sourceAt=price['at'],estimated=False)
    if not rows:
        return None
    current=frame_signal(rows,minutes,now)
    closed=current.get('closedAt')
    if not number(closed) or closed<=position['entryObservedAt'] or price['at']<closed:
        return None
    previous=frame_signal(rows,minutes,closed-minutes*MINUTE)
    if (previous.get('closedAt')!=closed-minutes*MINUTE
            or previous['closedAt']<=position['entryObservedAt']):
        return None
    if all(x.get('available') and x.get('ema')==opposite and x.get('macd')==opposite
           for x in (previous,current)):
        return dict(policy=EXIT_POLICY,kind='two-closed-local-bars',direction=opposite,
                    confirmedAt=closed,sourceAt=price['at'],minutes=minutes,
                    estimated=bool(previous.get('estimated') or current.get('estimated')),
                    bars=[previous,current])
    return None


def source(bundle, now, modeled):
    from paper_simulation import stamp
    s = (bundle or {}).get('spots') or {}
    at = stamp(s.get('spot_price_as_of'))
    valid = (s.get('is_genuine_xauusd_spot') is True and s.get('xaus_is_spot') is True
             and s.get('estimated') is not True and positive(s.get('xaus')) and number(at)
             and 0 <= now-at <= (180000 if modeled else 60000))
    return dict(available=bool(valid), at=at, price=s.get('xaus'),
                estimated=bool(valid and now-at>60000))


def seed(now):
    return dict(version=VERSION, startedAt=now, deadlineAt=now+DAYS*86400000,
                checkedAt=None, status='collecting', exitPolicy=EXIT_POLICY, arms={}, lastDecision=None,
                latency={}, recentLatency=[], cycles=0)


def latency(state, market, selection, quotes, now):
    """Observed clocks only. Never equate worker time with notification delivery."""
    from paper_simulation import fresh_quote, stamp
    w = market.get('earlyWarning') or {}
    side = w.get('direction')
    at = w.get('signalBarAt')
    key = f'{side}:{at}'
    audit = state['latency']
    if (side in ('LONG','SHORT') and number(at) and at <= now and
            w.get('state') in ('active','watch') and positive(w.get('expiresAt')) and now<w['expiresAt']):
        if audit.get('key') != key:
            if audit:
                state['recentLatency'] = (state['recentLatency']+[audit])[-12:]
            audit = dict(key=key, direction=side, signalBarAt=at, firstWarningObservedAt=now, warningExpiresAt=w['expiresAt'],
                         confirmationObservedAt=None, productQuoteAt=None, productObservedAt=None,
                         pushSentAt=None, pushReceivedAt=None,
                         pushEvidence='Nur mit korreliertem Versand-/Empfangsbeleg; hier unbekannt.')
            state['latency'] = audit
    if not audit:
        return
    audit['checkedAt'] = now
    audit['blockingReason'] = str(market.get('decisionReason') or '')[:240]
    audit['sourceAt'] = market.get('dataAt') if number(market.get('dataAt')) else None
    audit['sourceAgeMs'] = max(0,now-audit['sourceAt']) if audit['sourceAt'] is not None and audit['sourceAt']<=now else None
    # Correlation is limited to the warning's 15-minute episode, not a later signal.
    if w.get('state')=='withdrawn' and w.get('signalBarAt')==audit['signalBarAt']:
        audit['status'] = 'withdrawn'
        return
    if audit.get('status')=='withdrawn':
        return
    if now>=audit.get('warningExpiresAt',0) or now-audit['firstWarningObservedAt'] > 15*MINUTE:
        audit['status'] = 'expired'
        return
    if market.get('direction') == audit['direction'] and audit['confirmationObservedAt'] is None:
        audit['confirmationObservedAt'] = now
        audit['confirmationDelayMs'] = now-audit['firstWarningObservedAt']
    for choice in (selection or {}).get('choices',[]):
        if choice.get('direction') != audit['direction']:
            continue
        raw = quotes.get(choice.get('isin')) or {}
        if raw.get('estimated') is True or raw.get('priceKind') in ('calculated','issuer-chart') or raw.get('paperFxConversion'):
            continue
        q = fresh_quote(raw,now,choice.get('isin'))
        if q and audit['productQuoteAt'] is None:
            audit.update(productQuoteAt=stamp(q.get('askAt')),productObservedAt=now,
                         isin=choice['isin'],productPriceKind=q.get('priceKind'))
            break


def summarize_arm(a):
    return {k:copy.deepcopy(v) for k,v in a.items() if k not in ('position','lastSignal')}


def prospective_protective_stop(position, observed_price, config):
    """Paper-only stop proposal from a fresh, actually observed price.

    Never moves the existing stop away from the entry, assumes a historical
    intrabar fill, or changes the main Bob stop manager. No proposal before
    1R favorable movement. At 1.5R the ATR arm can protect more than entry.
    """
    mode = config.get('protective_exit')
    if mode not in ('break-even', 'atr-trailing'):
        return None
    side = position.get('direction')
    entry, risk, current = (position.get('entryPrice'),
                            position.get('risk'), position.get('stop'))
    if side not in ('LONG', 'SHORT') or not all(
            positive(v) for v in (entry, risk, current, observed_price)):
        return None
    sign = 1 if side == 'LONG' else -1
    progress = sign * (observed_price - entry)
    if progress < risk:
        return None
    proposal = entry
    if mode == 'atr-trailing' and progress >= 1.5 * risk:
        atr = position.get('atr')
        if not positive(atr):
            return None  # Never invent an ATR from incomplete evidence.
        proposal = observed_price - sign * atr
    return proposal if positive(proposal) and sign * (proposal-current) > 0 else None


def advance(old, bundle, market, selection, quotes, now):
    state = copy.deepcopy(old)
    if number(state.get('checkedAt')) and now <= state['checkedAt']:
        return state, []
    gap = number(state.get('checkedAt')) and now-state['checkedAt']>90000
    state['checkedAt'] = now; state['cycles'] += 1
    latency(state,market,selection,quotes,now)
    completed = []
    trend = dict(market.get('trendContext') or {})
    trend['direction'] = trend.get('hourDirection',trend.get('direction'))
    frames = ((bundle.get('history') or {}).get('bars_by_tf') or {})
    hour = [b for b in frames.get('1h',[]) if isinstance(b,dict) and b.get('instrument')=='XAU/USD'
            and number(b.get('openTime')) and b.get('isOpen') is False
            and b.get('providerIsOpen') is not True and b.get('estimated') is not True
            and b['openTime']+3600000<=now]
    if not hour or not 0<=now-max(b['openTime']+3600000 for b in hour)<=3660000:
        trend = dict(available=False)
    for mode in ('original','modeled'):
        modeled = mode=='modeled'
        rows, error = minute_history(bundle,now,modeled)
        signals = {(m,p):frame_signal(rows,m,now,p) for m,p in ((3,False),(5,False),(7,False),(5,True))} if rows else {}
        if rows:
            signals[(5,'continuation')] = fresh_continuation_signal(rows,now)
        price = source(bundle,now,modeled)
        for name,cfg in VARIANTS.items():
            key_signal=(cfg['minutes'], 'continuation' if cfg.get('continuation') else bool(cfg.get('pullback')))
            sig = signals.get(key_signal,dict(available=False,reason=error))
            allowed, reason = gate(sig,trend,cfg)
            if allowed:
                allowed,reason=score_gate(sig,market,cfg)
            if (allowed and price['available'] and market.get('ready') is True
                    and market.get('priceFresh') is True and number(market.get('dataAt'))
                    and abs(market['dataAt']-price['at'])<=2000
                    and market.get('direction') in ('LONG','SHORT')
                    and market['direction']!=sig['direction']):
                allowed,reason=False,'main-opposes-entry'
            for horizon in HORIZONS:
                key = f'{mode}:{name}:{horizon}'
                a = state['arms'].setdefault(key,dict(mode=mode,variant=name,horizonMinutes=horizon,
                    label=cfg['label'],started=0,closed=0,inconclusive=0,estimatedClosed=0,
                    originalClosed=0,originalSumNetPct=0.,estimatedSumNetPct=0.,
                    sumNetPct=0.,worstNetPct=None,maxAdversePct=0.,falseStarts=0,
                    lastSignal=None,position=None,blockCounts={},reversalExits=0,reversalEntries=0,
                    firstObservedAt=now,followThroughEntries=0,baselineOverlapEntries=0))
                a['reason'] = reason if not allowed else None if price['available'] else 'spot-source-unavailable'
                p = a['position']
                if p:
                    # Large gaps remain unknown. Small carried-source windows are model only.
                    if gap or now-p['lastObservedAt']> (180000 if modeled else 90000):
                        p.update(status='inconclusive',exitReason='observation-gap',closedAt=now,netPct=None)
                    elif price['available'] and price['at']>p['lastSourceAt']:
                        if modeled and now-p['lastObservedAt']>90000:
                            p['estimatedUsed'] = True
                        sign = 1 if p['direction']=='LONG' else -1
                        change = 100*sign*(price['price']/p['entryPrice']-1)
                        p['maxAdversePct'] = max(p['maxAdversePct'],-change)
                        p['maxFavorablePct'] = max(p['maxFavorablePct'],change)
                        p['lastSourceAt'] = price['at']; p['lastObservedAt'] = now
                        p['estimatedUsed'] |= price['estimated']
                        held = price['at']-p['entryObservedAt']
                        reversal = reversal_evidence(rows,cfg['minutes'],now,p,market,price)
                        # Time stop: 1/3 horizon (10/60/100 min), progress < 0.25R.
                        why = ('stop' if sign*(price['price']-p['stop'])<=0 else
                               'target' if sign*(price['price']-p['target'])>=0 else
                               'trend-reversal' if reversal else
                               'session-close' if not session(now) or datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich')).strftime('%H:%M') >= '21:45' else
                               'horizon' if held>=horizon*MINUTE else
                               'no-progress' if cfg.get('time_stop') and held>=horizon*MINUTE/3
                               and sign*(price['price']-p['entryPrice'])<.25*p['risk'] else None)
                        if not why:
                            proposed_stop = prospective_protective_stop(p,price['price'],cfg)
                            if proposed_stop is not None:
                                p['stop'] = proposed_stop
                                p['stopAdjustments'] = p.get('stopAdjustments',0)+1
                                p['lastStopObservedAt'] = price['at']
                        if why:
                            if why=='trend-reversal':
                                p['reversalEvidence']=reversal
                                p['estimatedUsed'] |= reversal['estimated']
                            p.update(status='closed',exitReason=why,closedAt=now,exitSourceAt=price['at'],
                                     exitPrice=price['price'],netPct=change-COST_PCT)
                    if p.get('status') in ('closed','inconclusive'):
                        a[p['status']] += 1
                        if p['status']=='closed':
                            a['sumNetPct'] += p['netPct']
                            cohort = 'estimated' if p['estimatedUsed'] else 'original'
                            a[cohort+'Closed'] += 1; a[cohort+'SumNetPct'] += p['netPct']
                            a['worstNetPct'] = min(a['worstNetPct'],p['netPct']) if a['worstNetPct'] is not None else p['netPct']
                            a['maxAdversePct'] = max(a['maxAdversePct'],p['maxAdversePct'])
                            a['falseStarts'] += int(p['exitReason']=='stop' and now-p['entryObservedAt']<=15*MINUTE)
                        a['lastExitAt']=now
                        a['lastExitSourceAt']=p.get('exitSourceAt',p['lastSourceAt'])
                        if p.get('exitReason')=='trend-reversal':
                            a['reversalExits']=a.get('reversalExits',0)+1
                            a['pendingReversal']=dict(caseId=p['id'],direction=p['reversalEvidence']['direction'],
                                                      closedAt=now,sourceAt=a['lastExitSourceAt'])
                        completed.append(p); a['position'] = None
                    # Never close and re-enter on the same sample.
                    continue
                signal_key = f"{sig.get('barAt')}:{sig.get('direction')}"
                if signal_key != a.get('lastEvaluatedSignal'):
                    if reason:
                        a['blockCounts'][reason] = a['blockCounts'].get(reason,0)+1
                a['lastEvaluatedSignal'] = signal_key
                if (not allowed or not price['available'] or price['estimated'] or not session(now)
                        or datetime.fromtimestamp(now/1000,ZoneInfo('Europe/Zurich')).strftime('%H:%M') >= '21:45'
                        or now>=state['deadlineAt'] or a['started']>=MAX_CASES or signal_key==a['lastSignal']):
                    continue
                # No stale original quote may be relabelled as an entry at current time.
                if price['at'] < sig['closedAt'] or price['at']<=max(a.get('lastExitSourceAt',0),state.get('entryAfterSourceAt',0)):
                    continue
                sign = 1 if sig['direction']=='LONG' else -1
                risk = sig['atr']*1.5
                # Frozen objective, reject already extended entry with insufficient room.
                target = sig['level']+sign*3*risk
                if not target_room(target,price['price'],risk,sig['direction'],cfg):
                    a['reason']='entry-too-late'; a['lastSignal']=signal_key
                    continue
                a['started'] += 1; a['lastSignal']=signal_key
                if cfg.get('continuation'):
                    if sig.get('setup')=='closed-5m-follow-through':
                        a['followThroughEntries'] += 1
                    else:
                        a['baselineOverlapEntries'] += 1
                a['position'] = dict(id=f'{VERSION}:{key}:{int(now)}',arm=key,version=VERSION,
                    ruleVersion=market.get('ruleVersion'),entryObservedAt=now,entrySourceAt=price['at'],
                    signalEvidence=copy.deepcopy(sig), signalClosedAt=sig['closedAt'],
                    setupType=sig.get('setup') if cfg.get('continuation') else None,
                    entryPrice=price['price'],direction=sig['direction'],
                    hourDirection=trend.get('direction'),stop=price['price']-sign*risk,target=target,risk=risk,
                    atr=sig['atr'],stopAdjustments=0,
                    horizonMinutes=horizon,costAssumptionPct=COST_PCT,estimatedUsed=bool(sig.get('estimated')),
                    lastSourceAt=price['at'],lastObservedAt=now,maxAdversePct=0.,maxFavorablePct=0.,
                    status='open',exitPolicy=EXIT_POLICY,realOrders=False,productReturnVerified=False)
                pending=a.get('pendingReversal') or {}
                if (pending.get('direction')==sig['direction'] and
                        0<now-pending.get('closedAt',now)<=30*MINUTE):
                    a['position']['followsReversalCaseId']=pending['caseId']
                    a['reversalEntries']=a.get('reversalEntries',0)+1
                a.pop('pendingReversal',None)
    state['status'] = ('draining' if any(a['position'] for a in state['arms'].values()) else 'completed-review-required') if now>=state['deadlineAt'] else 'collecting'
    state['lastDecision'] = dict(at=now,mainDirection=market.get('direction'),
                               reason=str(market.get('decisionReason') or '')[:240])
    return state, completed


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_intraday_timing_state
        (id TEXT PRIMARY KEY, payload JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_intraday_timing_cases
        (id TEXT PRIMARY KEY, campaign TEXT NOT NULL, payload JSONB NOT NULL)''')


def tick(conn,bundle,market,selection,quotes,now):
    migration_exit_at=None
    # Preserve v1 originals. Drain its open positions with the requested exit
    # protection, explicitly label the change, and never mix its results with v2.
    legacy=conn.execute('SELECT payload FROM bob_intraday_timing_state WHERE id=%s FOR UPDATE',(LEGACY_VERSION,)).fetchone()
    if legacy and legacy[0].get('status')!='superseded':
        prior=copy.deepcopy(legacy[0])
        prior.setdefault('originalDeadlineAt',prior['deadlineAt'])
        prior['deadlineAt']=min(prior['deadlineAt'],now)
        for arm in prior['arms'].values():
            if arm.get('position'):
                arm['position'].setdefault('exitPolicyChangedAt',now)
                arm['position']['exitPolicy']=EXIT_POLICY
        prior,done=advance(prior,bundle,market,selection,quotes,now)
        for case in done:
            conn.execute('INSERT INTO bob_intraday_timing_cases VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                         (case['id'],LEGACY_VERSION,json.dumps(case,allow_nan=False)))
        draining=any(a.get('position') for a in prior['arms'].values())
        prior['status']='draining' if draining else 'superseded'
        prior['supersededBy']=VERSION
        conn.execute('UPDATE bob_intraday_timing_state SET payload=%s::jsonb WHERE id=%s',
                     (json.dumps(prior,allow_nan=False),LEGACY_VERSION))
        if draining:
            return
        if done:
            migration_exit_at=source(bundle,now,False).get('at') or now
    row=conn.execute('SELECT payload FROM bob_intraday_timing_state WHERE id=%s FOR UPDATE',(VERSION,)).fetchone()
    old=row[0] if row else seed(now)
    if migration_exit_at is not None:
        old['entryAfterSourceAt']=migration_exit_at
    if old['status']=='completed-review-required':
        return
    state,done=advance(old,bundle,market,selection,quotes,now)
    for case in done:
        conn.execute('INSERT INTO bob_intraday_timing_cases VALUES(%s,%s,%s::jsonb) ON CONFLICT DO NOTHING',
                     (case['id'],VERSION,json.dumps(case,allow_nan=False)))
    conn.execute('''INSERT INTO bob_intraday_timing_state VALUES(%s,%s::jsonb)
        ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload''',(VERSION,json.dumps(state,allow_nan=False)))


def push_evidence(conn, audit):
    if not audit or not number(audit.get('signalBarAt')):
        return audit
    from datetime import timezone
    import push_delivery_history
    out = copy.deepcopy(audit)
    start = audit['signalBarAt']
    end = start+30*MINUTE
    iso = lambda t: datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
    data = push_delivery_history.report(conn,dict(start=iso(start),end=iso(end)))
    matches = [r for r in data['records'] if r.get('signalBarAt')==start
               and r.get('direction')==audit.get('direction') and r.get('test') is False
               and r.get('synthetic') is False and 'early-warning' in (r.get('eventKinds') or [])
               and r.get('outcome')=='provider-accepted']
    out['pushScanTruncated'] = data.get('nextOffset') is not None
    if matches:
        r = matches[0]
        out.update(pushSentAt=r.get('providerStartedAt'),pushBrowserReceiptAt=r.get('browserShowAt'),
                   pushEvidence='Passender Frühwarnungs-Versand vom Anbieter angenommen; Browserbeleg separat. Kein Android-Anzeigenachweis.',
                   pushLatency=r.get('latency'),matchedPushAttempts=len(matches))
    return out


def report(conn):
    row=conn.execute('SELECT payload FROM bob_intraday_timing_state WHERE id=%s',(VERSION,)).fetchone()
    if not row:
        legacy=conn.execute('SELECT payload FROM bob_intraday_timing_state WHERE id=%s',(LEGACY_VERSION,)).fetchone()
        prior=legacy[0] if legacy else {}
        pending=sum(bool(a.get('position')) for a in prior.get('arms',{}).values())
        return dict(version=VERSION,status='legacy-positions-draining' if pending else 'awaiting-first-worker-check',
                    checkedAt=prior.get('checkedAt') if pending else None,legacyOpenPositions=pending,
                    exitPolicy=EXIT_POLICY,note=NOTE)
    s=row[0]
    arms=[]
    audit = s['latency']
    try:
        with conn.transaction():
            audit = push_evidence(conn,audit)
    except Exception:
        audit = {**audit, 'pushEvidence':'Versand-/Empfangsnachweis derzeit nicht abrufbar.'}
    for a in s['arms'].values():
        r=summarize_arm(a)
        r['open']=bool(a.get('position'))
        r['meanOriginalNetPct']=a['originalSumNetPct']/a['originalClosed'] if a['originalClosed'] else None
        r['meanEstimatedNetPct']=a['estimatedSumNetPct']/a['estimatedClosed'] if a['estimatedClosed'] else None
        arms.append(r)
    return dict(version=VERSION,status=s['status'],startedAt=s['startedAt'],checkedAt=s['checkedAt'],
                deadlineAt=s['deadlineAt'],variants=arms,latency=audit,recentLatency=s['recentLatency'],
                horizonsMinutes=list(HORIZONS),timeframesMinutes=[3,5,7],lookbackMinutes=105,
                continuationVariant='follow5',
                exitPolicy=EXIT_POLICY,strategyWinnerConfirmed=False,liveRulesChanged=False,realOrders=False,note=NOTE)
