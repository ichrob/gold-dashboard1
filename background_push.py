"""Durable per-device push transitions. No broker/order actions."""
import copy
import json
import math
import re
import signal
import subprocess
import evaluator_runtime
import ko_protection
import time
from pathlib import Path


from datetime import datetime, time as clock_time, timedelta
from zoneinfo import ZoneInfo


def gold_weekend_close(now_ms):
    """Friday 23:00 until Monday 00:00, in Zurich local time. Holidays are separate."""
    zurich = ZoneInfo('Europe/Zurich')
    current = datetime.fromtimestamp(now_ms / 1000, zurich)
    weekday = current.weekday()
    if weekday == 4 and current.hour >= 23:
        days_since_friday = 0
    elif weekday == 5:
        days_since_friday = 1
    elif weekday == 6:
        days_since_friday = 2
    else:
        return None
    friday = current.date() - timedelta(days=days_since_friday)
    return int(datetime.combine(friday, clock_time(23), tzinfo=zurich).timestamp() * 1000)


def gold_weekend_seconds_remaining(now_ms=None):
    """Seconds until Monday 00:00 Europe/Zurich, including DST transitions."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    close_ms = gold_weekend_close(now_ms)
    if close_ms is None:
        return 0
    zurich = ZoneInfo('Europe/Zurich')
    friday = datetime.fromtimestamp(close_ms / 1000, zurich).date()
    monday = datetime.combine(friday + timedelta(days=3), clock_time(0), tzinfo=zurich)
    return max(0, (monday.timestamp() * 1000 - now_ms) / 1000)


def degiro_session(now_ms=None):
    """User-confirmed routine 08:00–22:00 Zurich, with 07:30 warm-up.

    This is a user trading workflow window, not an exchange-hours guarantee.
    Never use it to claim the underlying gold market is closed.
    """
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    local = datetime.fromtimestamp(now_ms / 1000, ZoneInfo('Europe/Zurich'))
    if gold_weekend_close(now_ms) is not None:
        return 'weekend'
    minute = local.hour * 60 + local.minute
    if 450 <= minute < 480 and local.weekday() < 5:
        return 'preparation'
    if 480 <= minute < 1320 and local.weekday() < 5:
        return 'trading'
    return 'night'


def degiro_entry_allowed(now_ms=None):
    return degiro_session(now_ms) == 'trading'


def degiro_seconds_to_transition(now_ms=None):
    """Bound polling sleeps so the 07:30/08:00/22:00 phase is not missed."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    local = datetime.fromtimestamp(now_ms / 1000, ZoneInfo('Europe/Zurich'))
    boundaries = []
    for offset in range(5):
        day = local.date() + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for h, m in ((7, 30), (8, 0), (22, 0), (23, 0)):
            boundary = datetime.combine(day, clock_time(h, m), tzinfo=local.tzinfo)
            delta = boundary.timestamp() - now_ms / 1000
            if delta > 0:
                boundaries.append(delta)
    weekend_left = gold_weekend_seconds_remaining(now_ms)
    if weekend_left:
        boundaries.append(weekend_left)
    return min(boundaries) if boundaries else 300


def degiro_poll_seconds(now_ms=None, active_trade=False):
    phase = degiro_session(now_ms)
    if phase == 'weekend':
        return gold_weekend_seconds_remaining(now_ms)
    if active_trade or phase in ('trading', 'preparation'):
        return 30
    return min(300, degiro_seconds_to_transition(now_ms))


def weekend_quote_at_close(now_ms, data_at):
    """Only a near-close quote can justify a normal weekend pause, never old failures."""
    close_at = gold_weekend_close(now_ms)
    return (close_at is not None and positive(data_at) and
            close_at - 20 * 60000 <= data_at <= close_at + 5 * 60000 and
            data_at <= now_ms)


def positive(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def product_model(value, direction):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('simpleSpotTurbo') is not True or value.get('referenceConfirmed') is not True or value.get('currency') not in ('EUR','CHF'):
        raise ValueError('Bestätigtes Gold-Spot-Turbo-Modell in EUR oder CHF fehlt')
    if value.get('direction') != direction or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', str(value.get('isin', ''))):
        raise ValueError('Produktidentität oder Trade-Richtung widersprüchlich')
    keys = ('bid','goldReference','fxReference','fxScenario','ratio','strike','ko','entry','quantity')
    if not all(positive(value.get(k)) for k in keys) or value['quantity'] % 1:
        raise ValueError('Produktreferenz unvollständig')
    if not all(isinstance(value.get(k),str) and 0<len(value[k])<=2000 for k in ('source','referenceAt')):
        raise ValueError('Produktquelle oder Referenzzeit fehlt')
    d = 1 if direction == 'LONG' else -1
    if d*(value['goldReference']-value['ko'])<=0:
        raise ValueError('Produktreferenz jenseits der KO-Barriere')
    return {k:value[k] for k in (*keys,'isin','direction','currency','source','referenceAt','simpleSpotTurbo','referenceConfirmed')}


def product_price(model, gold):
    if not model or not positive(gold):
        return None
    d = 1 if model['direction']=='LONG' else -1
    if d*(gold-model['ko'])<=0:
        return None
    price=model['bid']+d*model['ratio']*((gold-model['strike'])*model['fxScenario']-(model['goldReference']-model['strike'])*model['fxReference'])
    return price if positive(price) else None


def level_text(trade, gold):
    model=trade.get('product')
    price=product_price(model,gold)
    if model:
        return f"≈ {price:.4f} {model.get('currency','EUR')}/Stück (geschätzt) · Gold {gold:.2f} USD/oz" + (' · FX-Aktualisierung verzögert' if model.get('fxDelayed') else '') if price else 'Produktkurs nicht berechenbar (KO/Modellgrenze)'
    return f"{gold:.2f} USD/oz (Goldreferenz; Produktdaten fehlen)"


def config(value):
    value = value if isinstance(value, dict) else {}
    tf = value.get('timeframe', '15m')
    if tf not in ('5m', '15m', '1h'):
        raise ValueError('Ungültige Push-Zeitebene')
    result = {'timeframe': tf, 'trailAtr': 1.5, 'trade': None}
    if 'riskEnabled' in value:
        if type(value['riskEnabled']) is not bool:
            raise ValueError('Risiko-Schalter muss wahr oder falsch sein')
        result['riskEnabled'] = value['riskEnabled']
    mult = value.get('trailAtr', 1.5)
    if not positive(mult) or mult > 10:
        raise ValueError('Ungültiger ATR-Faktor')
    result['trailAtr'] = mult
    t = value.get('trade')
    if t is not None and not isinstance(t, dict):
        raise ValueError('Ungültige Trade-Einstellungen')
    if t and t.get('active') and not t.get('test'):
        if t.get('dir') not in ('LONG', 'SHORT') or not all(positive(t.get(k)) for k in ('entry', 'stop', 'initialRisk')):
            raise ValueError('Einstieg, Stop und Anfangsrisiko fehlen für Hintergrund-Push')
        if t.get('instrument') != 'XAU/USD':
            raise ValueError('Trade-Basiswert für Hintergrund-Push muss XAU/USD sein')
        if not isinstance(t.get('tradeId'), str) or not 1 <= len(t['tradeId']) <= 100:
            raise ValueError('Trade-ID fehlt für Hintergrund-Push')
        result['trade'] = {k: t.get(k) for k in ('tradeId', 'dir', 'entry', 'stop', 'initialRisk', 'target', 'instrument')}
        result['trade']['active'] = True
        personal = t.get('personalRisk')
        result['trade']['personalRisk'] = None
        if personal is not None:
            if not isinstance(personal, dict) or not positive(personal.get('account')) or not positive(personal.get('percent')) or personal['percent'] > 100:
                raise ValueError('Persönliche Risikoeinstellung ungültig')
            result['trade']['personalRisk'] = {'account': personal['account'], 'percent': personal['percent']}

        result['trade']['product'] = product_model(t.get('product'), t['dir'])
        if t.get('target') is not None and not positive(t['target']):
            raise ValueError('Ungültiges Kursziel')
    return result


def analyze(bundle, settings, *, priority=None):
    import diagnostic_history as history
    import uuid
    trace_id=history.trace(bundle)
    decision_id=uuid.uuid4().hex
    spots=bundle.get('spots') or {}
    bars=(bundle.get('history') or {}).get('bars_by_tf') or {}
    history.emit('input',trace_id,{**spots,'fetchedAt':bundle.get('fetched_at'),
        'counts':{tf:len(values) for tf,values in bars.items() if isinstance(values,list)}},decision_id)
    try:
        result=_analyze(bundle,settings,priority=priority)
    except Exception as exc:
        history.emit('analysis-failed',trace_id,{'timeframe':settings.get('timeframe','15m'),
            'errorType':type(exc).__name__},decision_id)
        raise
    history.emit('analysis',trace_id,{'timeframe':settings.get('timeframe','15m'),
        'purpose':'trade-monitor' if (settings.get('trade') or {}).get('active') else 'market-analysis',
        'result':result},decision_id)
    result['traceId']=trace_id
    result['decisionId']=decision_id
    return result


def _analyze(bundle, settings, *, priority=None):
    started = time.monotonic()
    payload = json.dumps({**settings, 'bundle': bundle})
    # One fresh process after SIGABRT, within the original ten-second budget.
    # The evaluator rechecks source freshness; no previous result is reused.
    for attempt in range(2):
        remaining = 10 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError('Zeitlimit der Hintergrundanalyse erreicht')
        p = evaluator_runtime.run(['node', str(Path(__file__).with_name('background_analysis.js'))],
                           input=payload, text=True, capture_output=True, timeout=remaining,
                           priority=(0 if (settings.get('trade') or {}).get('active') else 1) if priority is None else priority)
        if p.returncode != -signal.SIGABRT or attempt:
            break
        print('BOB_ANALYSIS_RETRY signal=SIGABRT attempt=1', flush=True)
    if p.returncode:
        # The child reports only error metadata, never input/settings or quote payloads.
        try:
            error = json.loads(p.stderr)
            print('BOB_ANALYSIS_ERROR '+json.dumps(error, ensure_ascii=True), flush=True)
        except (ValueError, TypeError):
            print('BOB_ANALYSIS_ERROR exit='+str(p.returncode), flush=True)
        raise RuntimeError('Hintergrundanalyse fehlgeschlagen')
    result = json.loads(p.stdout)
    # Diagnostics must never alter or block an existing analysis result.
    try:
        import bob_diagnostics
        bob_diagnostics.observe_analysis(result, settings.get('timeframe', '15m'))
    except Exception:
        pass
    print('BOB_BACKGROUND_ANALYSIS ready='+str(result.get('ready'))+' priceFresh='+str(result.get('priceFresh'))+' duration_ms='+str(round((time.monotonic()-started)*1000)), flush=True)
    return result


def failed_analysis_market(bundle):
    """Preserve a genuine source clock when computation fails, without approving it."""
    from datetime import datetime
    at = None
    try:
        stamp = datetime.fromisoformat(bundle['spots']['spot_price_as_of'].replace('Z', '+00:00'))
        candidate = stamp.timestamp()*1000
        if stamp.tzinfo is not None and 0 < candidate <= time.time()*1000:
            at = candidate
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        pass
    return {'ready': False, 'priceFresh': False, 'analysisError': True, 'dataAt': at}


def advance(previous, settings, market, general, trade_enabled, now=None, log=True):
    from datetime import datetime
    settings = copy.deepcopy(settings)
    model = (settings.get('trade') or {}).get('product')
    currency=(model or {}).get('currency','EUR')
    fx = (market.get('fxByCurrency') or {}).get(currency) or (market.get('fx') or {} if currency=='EUR' else {})
    if model:model['fxDelayed']=True
    if model and positive(fx.get('rate')):
        try:
            stamp = datetime.fromisoformat(fx.get('fetchedAt','').replace('Z','+00:00')).timestamp()*1000
            clock = time.time()*1000 if now is None else now
            if 0 <= clock-stamp:
                model['fxScenario'] = fx['rate']
                model['fxDelayed'] = bool(fx.get('error')) or clock-stamp>90000
        except (ValueError, TypeError):
            pass
    now = int(time.time()*1000) if now is None else now
    state = copy.deepcopy(previous or {})
    if not general and not trade_enabled:
        state.pop('trade', None)
        return state, []
    events = []
    risk = market.get('risk')
    if settings.get('riskEnabled') is not True:
        state.pop('risk', None)
    elif isinstance(risk, dict) and isinstance(risk.get('state'), dict):
        candidate = risk['state']
        checked = candidate.get('checkedAt')
        if positive(checked) and 0 <= now-checked <= 60000:
            state['risk'] = copy.deepcopy(candidate)
            for event in risk.get('events', []):
                data = event.get('data') or {}
                channel = data.get('kind')
                if not (positive(data.get('expiresAt')) and now < data['expiresAt']):
                    continue
                if channel == 'general' and general and degiro_entry_allowed(now):
                    events.append(copy.deepcopy(event))
                elif channel == 'trade' and trade_enabled and data.get('tradeId') == (settings.get('trade') or {}).get('tradeId'):
                    events.append(copy.deepcopy(event))
    def audit(kind, outcome, reason):
        history = state.setdefault('pushHistory', [])
        # Keep a bounded durable history without adding an entry every tick.
        if history and history[-1]['kind'] == kind and history[-1]['outcome'] == outcome and now-history[-1]['at'] < 300000:
            return
        history.append({'at': now, 'kind': kind, 'outcome': outcome, 'reason': reason})
        del history[:-50]
        if log:print('BOB_PUSH_DECISION '+json.dumps({'kind': kind, 'outcome': outcome, 'reason': reason[:160]}, ensure_ascii=True), flush=True)
    def add(kind, title, reason, channel='trade'):
        audit(kind, 'planned', reason[:160])
        product=(settings.get('trade') or {}).get('product') if channel=='trade' else None
        if product:
            reason=reason+' · '+product['isin']+' · Modellreferenz '+product['referenceAt']+'; verfügbarer Wechselkurs und gespeicherte Produktbedingungen. Kein bestätigter DEGIRO-Kurs.'
        events.append({'title': title, 'body': reason, 'tag': 'bob-background-'+channel,
                       'data': {'kind': channel, 'eventKind': kind, 'url': '/#trade' if channel=='trade' else '/', 'dataAt': market.get('dataAt'), 'generatedAt': now,
                                'expiresAt': now+180000, 'tradeId': (settings.get('trade') or {}).get('tradeId')}})
    # Market closure is a third status, not a source outage or a fresh quote.
    # Keep the last genuine timestamp and do not hide failures already seen while open.
    raw_healthy = market.get('ready') is True and market.get('priceFresh') is True
    previous_state = previous or {}
    last_data_at = market.get('dataAt')
    if not positive(last_data_at):
        last_data_at = (state.get('lastAnalysis') or {}).get('dataAt')
    market_closed = (weekend_quote_at_close(now, last_data_at) and
                     (previous_state.get('dataStatus') == 'closed' or
                      previous_state.get('healthy', True) is not False))
    healthy = raw_healthy and not market_closed
    # Keep computing with the last usable observations, without renewing their clocks.
    snapshot = state.get('lastAnalysis') or {}
    if positive(market.get('price')) and positive(market.get('dataAt')) and market['dataAt'] <= now:
        snapshot = {**snapshot, **{key: copy.deepcopy(market.get(key)) for key in
                    ('price', 'dataAt', 'analysisBarAt', 'score', 'atr', 'macd', 'signal', 'analysisSnapshot', 'trendContext', 'continuedPlan') if market.get(key) is not None}}
        state['lastAnalysis'] = snapshot
    calculation = {'available': bool(snapshot), 'stale': not healthy, 'marketClosed': market_closed, 'computedAt': now,
                   'dataAt': snapshot.get('dataAt'), 'price': snapshot.get('price'),
                   'score': snapshot.get('score'), 'analysisBarAt': snapshot.get('analysisBarAt'),
                   'plan': copy.deepcopy(snapshot.get('continuedPlan'))}
    model_trade = settings.get('trade') or {}
    if calculation['plan'] and calculation['plan'].get('tradeId') != model_trade.get('tradeId'):
        calculation['plan'] = None
    if calculation['plan']:
        plan = calculation['plan']
        plan['computedAt'] = now
        existing = state.get('trade') or {}
        stop = existing.get('stop') if existing.get('tradeId') == model_trade.get('tradeId') else model_trade.get('stop')
        if positive(stop):
            plan['stop'] = (max if model_trade['dir']=='LONG' else min)(plan['stop'], stop)
    if snapshot and model_trade:
        reference = snapshot['price']
        sign = 1 if model_trade['dir'] == 'LONG' else -1
        calculation.update(stopDistance=sign*(reference-model_trade['stop']),
                           targetDistance=sign*(model_trade['target']-reference) if positive(model_trade.get('target')) else None,
                           productEstimate=product_price(model_trade.get('product'), reference))
    state['continuedCalculation'] = calculation
    channel = 'trade' if trade_enabled and settings.get('trade') else 'general'
    # Market closure does not produce a stale/recovery push. On reopening,
    # freshness is checked as usual and a persistent outage still alerts.
    if market_closed:
        state['announcedHealthy'] = True
        state.pop('healthPending', None)
        state['dataStatus'] = 'closed'
    else:
        if previous_state.get('dataStatus') == 'closed' and healthy:
            state['announcedHealthy'] = True
            state.pop('healthPending', None)
        # Notification debounce never makes unhealthy data eligible for analysis.
        announced = state.setdefault('announcedHealthy', state.get('healthy', True))
        pending = state.get('healthPending')
        if healthy == announced:
            state.pop('healthPending', None)
        elif not pending or pending['value'] != healthy:
            state['healthPending'] = {'value': healthy, 'since': now, 'count': 1, 'checkedAt': now}
        elif now-pending['checkedAt'] >= 25000:
            pending.update(count=pending['count']+1, checkedAt=now)
        pending = state.get('healthPending')
        confirmed = pending and pending['count'] >= (2 if healthy else 3) and now-pending['since'] >= (30000 if healthy else 60000)
        if healthy != announced and not confirmed:
            audit('data-status', 'suppressed', 'Statuswechsel noch nicht mehrfach bestätigt')
        if confirmed:
            if not healthy:
                reason = ('Die Hintergrundanalyse ist fehlgeschlagen. Bob rechnet mit dem letzten verfügbaren Datenstand weiter, sofern vorhanden; keine aktuelle Marktbestätigung.'
                          if market.get('analysisError') else 'Aktualität oder zeitliche Abstimmung der vorhandenen Markt-/Analysedaten nicht bestätigt. Berechnung mit vorhandenen Werten läuft weiter; Überwachung eingeschränkt.')
                add('data-unavailable', 'DATENSTATUS · Berechnung mit veralteten Werten', reason, channel)
            else:
                add('data-recovered', 'DATENSTATUS · Überwachung fortgesetzt', 'Aktuelle Daten wieder vorhanden. Keine Entwarnung für einen Trade.', channel)
            state['announcedHealthy'] = healthy
            state.pop('healthPending', None)
        state['dataStatus'] = 'active' if healthy else 'unavailable'
    state['healthy'] = healthy
    direction = market.get('direction', 'NEUTRAL') if healthy else 'NEUTRAL'
    mtf = market.get('mtf', 'NEUTRAL') if healthy else 'NEUTRAL'
    # A market-based early warning is a separate, advisory-only event.
    # Require an independently clocked CLOSED 5m signal bar, a fresh shared
    # spot observation, no already-confirmed main direction, and no weekend.
    # Persist the last notified candle in the existing per-device push state;
    # delivery failure already prevents the state from being committed.
    warning = market.get('earlyWarning')
    active_warning = (
        general and healthy and not market_closed
        and (market.get('session') or {}).get('entryAllowed') is True
        and isinstance(warning, dict)
        and warning.get('version') == 'early-warning-v2'
        and warning.get('monitoring') is True
        and warning.get('available') is True
        and warning.get('comparisonOnly') is True
        and warning.get('affectsApproval') is False
        and warning.get('state') == 'active'
        and warning.get('direction') in ('LONG', 'SHORT')
        and warning.get('direction') != direction
        and positive(warning.get('signalBarAt'))
        and positive(warning.get('checkedAt'))
        and positive(warning.get('expiresAt'))
        and positive(market.get('dataAt'))
        and 0 <= now-warning['signalBarAt'] <= 300000
        and 0 <= now-warning['checkedAt'] <= 90000
        and warning['signalBarAt'] <= market['dataAt'] + 300000
        and now < warning['expiresAt']
    )
    last_warning = state.get('earlyWarningSent')
    if active_warning:
        side = warning['direction']
        bar_at = warning['signalBarAt']
        # At most one notification per signal candle. Only a different side
        # may bypass the 30-minute same-side noise limit.
        recent_same = (isinstance(last_warning, dict)
                       and last_warning.get('direction') == side
                       and type(last_warning.get('sentAt')) in (int,float)
                       and 0 <= now-last_warning['sentAt'] < 1800000)
        previously_sent = isinstance(last_warning, dict) and (
            last_warning.get('direction') == side
            and last_warning.get('signalBarAt') == bar_at)
        if not recent_same and not previously_sent:
            add('early-warning', 'FRÜHWARNUNG · '+side,
                'Gold: '+side+'-Frühimpuls auf geschlossener 5m-Kerze beobachtet. '
                'Hauptsignal noch nicht in dieser Richtung bestätigt. '
                'Nur Marktbeobachtung, keine Produktfreigabe oder Order.', 'general')
            e = events[-1]
            e['tag'] = 'bob-early-warning-'+side.lower()+'-'+str(int(bar_at))
            e['data'].update(direction=side, signalBarAt=bar_at,
                             warningState='active', comparisonOnly=True,
                             affectsApproval=False,
                             expiresAt=min(warning['expiresAt'],now+180000))
            state['earlyWarningSent'] = {
                'direction':side, 'signalBarAt':bar_at, 'sentAt':now}
    elif (general and healthy and isinstance(last_warning,dict)
          and isinstance(warning,dict) and warning.get('version')=='early-warning-v2'
          and warning.get('state')=='withdrawn'
          and warning.get('signalBarAt')==last_warning.get('signalBarAt')
          and not last_warning.get('withdrawn')):
        # Only withdraw an actually delivered warning; never invent a
        # withdrawal when the source is unavailable or simply expires.
        add('early-warning-withdrawn','FRÜHWARNUNG · zurückgenommen',
            'Der zuvor gemeldete '+last_warning['direction']+
            '-Frühimpuls wurde durch einen geschlossenen Gegenkurs '
            'zurückgenommen. Keine Trade-Entwarnung.', 'general')
        events[-1]['data'].update(comparisonOnly=True,affectsApproval=False)
        last_warning['withdrawn']=True
    # Timeliness applies only to newly suggested entries, not risk alerts
    # or ongoing monitoring of a real position.
    timing = market.get('entryTimingGate')
    timely = not isinstance(timing, dict) or timing.get('allowed') is True
    if general and healthy and (market.get('session') or {}).get('entryAllowed', True) and not timely:
        state.setdefault('notifiedDirection', 'NEUTRAL')
        state.pop('signalPending', None)
        audit('late-entry', 'suppressed', 'ABWARTEN: '+str(timing.get('reason') or 'Einstiegszeit nicht geprüft')[:120])
    if general and healthy and timely and (market.get('session') or {}).get('entryAllowed', True):
        notified = state.setdefault('notifiedDirection', state.get('direction'))
        pending = state.get('signalPending')
        if direction not in ('LONG', 'SHORT') or direction == notified:
            state.pop('signalPending', None)
        elif not pending or pending['direction'] != direction:
            # The actual shared analysis already verified two distinct closed
            # 1m follow-through candles beyond the prepared 5m setup. Do not
            # impose another 30s delay, but only with a current source-clocked
            # non-extended Gold timing check. No product/broker approval.
            fast=(market.get('entryTiming')=='two-minute-follow-through-v1'
                  and isinstance(timing,dict) and timing.get('allowed') is True
                  and positive(market.get('dataAt')))
            if fast:
                add('signal-change', 'EINSTIEG · '+direction,
                    'Früh bestätigtes '+direction+' (zwei geschlossene 1m-Kerzen) · MTF '+mtf+
                    '. Einstiegsfenster aktuell; keine Produktfreigabe.', 'general')
                state['notifiedDirection']=direction
                state.pop('signalPending',None)
            else:
                state['signalPending'] = {'direction': direction, 'since': now, 'dataAt': market.get('dataAt')}
                audit('signal-change', 'suppressed', 'Richtung wartet auf erneute aktuelle Bestätigung')
        elif now-pending['since'] >= 30000 and positive(market.get('dataAt')) and market['dataAt'] != pending['dataAt']:
            add('signal-change', 'EINSTIEG · '+direction, 'Neuer Einstieg: '+direction+' bestätigt · MTF '+mtf+'. Keine Produktfreigabe.', 'general')
            state['notifiedDirection'] = direction
            state.pop('signalPending', None)
        # MTF confirmation is included in the direction message, never a second alert.
    else:
        state.pop('signalPending', None)
    if healthy:
        state.update(direction=direction, mtf=mtf)
    t = settings.get('trade') if trade_enabled else None
    if not t:
        state.pop('trade', None)
        return state, present_events(events, settings, market)
    # Learned filters govern new entries only; preserve reversal/exit monitoring.
    direction = market.get('baseDirection', direction) if healthy else 'NEUTRAL'
    old = state.get('trade', {})
    if old.get('tradeId') != t['tradeId']:
        old = {**t, 'stage': 0}
    # Never loosen a previously suggested model stop on a stale browser sync.
    old['stop'] = max(old['stop'], t['stop']) if t['dir']=='LONG' else min(old['stop'], t['stop'])
    old['product'] = t.get('product')
    if positive(t.get('target')):
        old['target'] = (max if t['dir']=='LONG' else min)(old.get('target') or t['target'], t['target'])
    state['trade'] = old
    session = market.get('session') or {}
    if session.get('closeReminder') and session.get('date') and old.get('intradayEndDate') != session['date']:
        add('intraday-end', 'INTRADAY · Tagesende', 'Bobs Tagesende-Zeit 21:45 (Zürich) ist erreicht. Offene Position und Schließung bei DEGIRO prüfen. Produkthandelszeiten können abweichen. Keine automatische Order.')
        old['intradayEndDate'] = session['date']
        events[-1]['tag'] = 'bob-intraday-end-' + t['tradeId']
    if market_closed or not market.get('priceFresh') or not positive(market.get('price')):
        return state, present_events(events, settings, market)
    p, stop, entry, risk = market['price'], old['stop'], t['entry'], t['initialRisk']
    personal, model = t.get('personalRisk'), t.get('product')
    # Shared KO proximity guard for Bob's real-position advisory push, not
    # merely the automated paper portfolios. Trade remains user-controlled.
    # A fresh, source-clocked XAU/USD price and a verified Spot model are
    # mandatory: never compare a Gold Future KO level with Spot.
    market_at = market.get('dataAt')
    if model and raw_healthy and positive(market_at) and 0 <= now-market_at <= 60000:
        guard = ko_protection.assess(p, model['ko'], t['dir'], market.get('atr'))
        old['koProtection'] = guard
        level = guard['level']
        previous_level = old.get('koAlertLevel')
        if level in ('warning', 'critical') and level != previous_level:
            text = (f"KO-Abstand {guard['distancePct']:.2f}% / "
                    + (f"{guard['atrMultiple']:.2f} ATR. " if guard['atrMultiple'] is not None else "ATR nicht bestätigt. ")
                    + f"Schutzmarke Gold ≈ {guard['protectiveStopGold']:.2f} USD/oz. "
                    + "Produkt-Geldkurs, KO-Status und eigenen Stop-Loss bei DEGIRO prüfen. "
                    + "Kein automatischer Verkauf und keine garantierte Ausführung.")
            add('ko-risk-critical' if level == 'critical' else 'ko-risk-warning',
                'TRADE-WARNUNG · KO-Gefahr' if level == 'critical' else 'TRADE-HINWEIS · KO-Abstand', text)
        old['koAlertLevel'] = level
    if model and (p <= model['ko'] if t['dir']=='LONG' else p >= model['ko']) and not old.get('koSent'):
        add('ko-hit', 'TRADE-WARNUNG · KO-Barriere erreicht', 'Goldreferenz erreicht die gespeicherte KO-Barriere. Produktstatus bei DEGIRO prüfen; kein bestätigter Emittentenstatus.')
        old['koSent'] = True
    if personal and model:
        budget = personal['account'] * personal['percent'] / 100
        estimated = product_price(model, p)
        conversion=1.0 if model.get('currency')=='EUR' else None
        if model.get('currency')=='CHF':
            eur=(market.get('fxByCurrency') or {}).get('EUR') or {}
            try:
                clocks=[datetime.fromisoformat(v['fetchedAt'].replace('Z','+00:00')).timestamp()*1000 for v in (eur,fx)]
                if all(positive(v.get('rate')) and not v.get('error') for v in (eur,fx)) and all(0<=now-c<=90000 for c in clocks) and abs(clocks[0]-clocks[1])<=90000:conversion=eur['rate']/fx['rate']
            except (KeyError,ValueError,TypeError):pass
        marker = [personal['account'], personal['percent'], model['entry'], model['quantity']]
        if estimated is not None and conversion is not None and (model['entry'] - estimated) * model['quantity'] * conversion >= budget and old.get('personalRiskSent') != marker:
            loss = (model['entry'] - estimated) * model['quantity'] * conversion
            add('personal-risk', 'Persönliche Verlustgrenze erreicht',
                f"Berechneter Verlust ≈ {loss:.2f} EUR; Risikobudget {budget:.2f} EUR ({personal['percent']:g}% von {personal['account']:g} EUR). Ohne Gebühren. Position prüfen; kein automatischer Verkauf.")
            events[-1]['tag'] = 'bob-personal-risk-' + t['tradeId']
            old['personalRiskSent'] = marker

    main_trend = market.get('trendContext') or {}
    trend_intact = healthy and main_trend.get('available') is True and main_trend.get('intact') is True and main_trend.get('direction') == t['dir']
    long = t['dir']=='LONG'
    reached = p<=stop if long else p>=stop
    near = max((market.get('atr') or 0)*.25, 1)
    phase = 'hit' if reached else 'near' if abs(p-stop)<=near else 'clear'
    send_hit = reached and not old.get('stopHitSent')
    send_near = phase == 'near' and phase != old.get('stopPhase') and now-old.get('stopNearAt', -300000) >= 300000 and not old.get('stopHitSent')
    if send_hit or send_near:
        add('stop-'+phase, 'TRADE-WARNUNG · '+('Stop erreicht' if reached else 'Stop wird knapp'), f"{t['dir']} · Modell-Stop {level_text(t,stop)}. Position prüfen.")
        if reached:
            old['stopHitSent'] = True
        else:
            old['stopNearAt'] = now
    old['stopPhase'] = phase
    target = old.get('target')
    target_hit = positive(target) and (p>=target if long else p<=target)
    if target_hit and not old.get('targetSent'):
        add('target', 'TRADE-WARNUNG · Ziel erreicht', f"{t['dir']} · Ziel {level_text(t,target)} anhand Goldreferenz erreicht. {('Haupttrend intakt: Fortsetzung mit geschütztem Stop prüfen.' if trend_intact else 'Fortsetzung nicht bestätigt: Gewinnschutz und Stop prüfen; kein automatischer Ausstieg.')}")
        old['targetSent'] = True
    if healthy and not trend_intact and direction in ('LONG','SHORT') and direction != t['dir'] and direction != old.get('opposite'):
        add('reversal', 'TRADE-WARNUNG · Richtungswechsel', f"Bestätigtes {direction}-Signal gegen deinen {t['dir']}-Trade. Schließen prüfen.")
        old['opposite'] = direction
    elif healthy and direction == t['dir']:
        old['opposite'] = None
    if reached or not healthy:
        return state, present_events(events, settings, market)
    if model and not old.get('initialPlanSent') and product_price(model, stop) is not None and product_price(model, old.get('target')) is not None:
        add('initial-stop', 'TRADE-PLAN · Stop und Ziel', f"Stop: {level_text(t,stop)} · Ziel: {level_text(t,old['target'])}. Initialer Überwachungsplan; bei DEGIRO selbst eintragen.")
        old['initialPlanSent'] = True
    r = (p-entry if long else entry-p)/risk
    stage = 2 if r>=2 else 1.5 if r>=1.5 else 1 if r>=1 else 0
    desired = stop
    if stage > old.get('stage',0):
        lock = 1 if stage>=2 else .5 if stage>=1.5 else 0
        level = entry+risk*lock if long else entry-risk*lock
        desired = max(stop,level) if long else min(stop,level)
        old['stage'] = stage
    candidate = market.get('suggestedStop')
    if positive(candidate) and (candidate<p if long else candidate>p):
        desired = max(desired,candidate) if long else min(desired,candidate)
    notified_stop = old.get('notifiedStop', stop)
    change = abs(desired-notified_stop)
    minimum = max((market.get('atr') or 0)*.25, risk*.1, .01)
    if change >= minimum and now-old.get('stopUpdateAt', -300000) >= 300000:
        add('profit-protection' if stage else 'trailing-stop', 'TRADE-WARNUNG · Stop nachziehen', f"{t['dir']} · Neuer Modell-Stop {level_text(t,desired)} (zuletzt gemeldet {level_text(t,notified_stop)}); {r:.1f}R (Goldplan). Bei DEGIRO selbst anpassen.")
        old.update(notifiedStop=desired, stopUpdateAt=now)
    elif change > .0001:
        audit('trailing-stop', 'suppressed', 'Änderung zu klein oder letzte Meldung weniger als fünf Minuten her')
    old.setdefault('notifiedStop', stop)
    if abs(desired-stop)>.0001:
        old['stop'] = desired
    # Extend only after the old objective is reached and a new closed bar confirms continuation.
    candidate = market.get('suggestedTarget')
    bar = market.get('analysisBarAt')
    macd, signal = market.get('macd'), market.get('signal')
    strong = (direction==t['dir'] and mtf==t['dir'] and
              isinstance(macd,(int,float)) and isinstance(signal,(int,float)) and
              (macd>=signal and market.get('score',0)>=70 if long else macd<=signal and market.get('score',100)<=30))
    strong = (main_trend.get('phase') == 'CONTINUATION') if trend_intact else strong
    target_plan = market.get('suggestedTargetPlan') or {}
    if target_hit and strong and target_plan.get('entrySuitable') is not False and positive(candidate) and positive(bar) and bar>old.get('targetBarAt',0):
        step=max(risk*.5, (market.get('atr') or 0)*.5)
        beyond = candidate>=max(p,target)+step if long else candidate<=min(p,target)-step
        if beyond:
            old.update(target=candidate,targetSent=False,targetBarAt=bar)
            add('target-extension','TRADE-PLAN · Ziel erreicht – neues Ziel',
                f"{t['dir']} · Bisheriges Ziel erreicht. Neues Ziel {level_text(t,candidate)}; Stop {level_text(t,old['stop'])}. {('Haupttrend-Fortsetzung durch geschlossene Kerze bestätigt' if trend_intact else 'Richtung, MTF und Momentum weiter bestätigt')}. Vorschlag bei DEGIRO selbst übernehmen. {target_plan.get('warning','')}")
    estimated_now=product_price(t.get('product'),p)
    product_in_profit=not t.get('product') or (estimated_now is not None and estimated_now>t['product']['entry'])
    weak = not trend_intact and (main_trend.get('phase') == 'WEAKENING' or mtf != t['dir'] or (market.get('score',50)<65 if long else market.get('score',50)>35))
    if weak and r>=1 and product_in_profit and not old.get('weak'):
        add('profit-weak', 'TRADE-WARNUNG · Gewinn schützen', f"{t['dir']} · Aktueller Modell-Stop {level_text(t,old['stop'])}. Momentum schwächer bei {r:.1f}R (Goldplan). Stop/Position prüfen.")
    old['weak'] = weak and r>=1 and product_in_profit
    return state, present_events(events, settings, market)




def present_events(events, settings, market):
    """Presentation only: retain triggers/checkpoints, combine compatible messages."""
    events = copy.deepcopy(events)
    kinds = {e['data']['eventKind'] for e in events}
    if 'target-extension' in kinds:
        events = [e for e in events if e['data']['eventKind'] != 'target']
    trade = settings.get('trade')
    trend = market.get('trendContext') or {}
    for event in events:
        if event['data']['eventKind'] == 'signal-change' and trade:
            intact = trend.get('available') and trend.get('intact') and trend.get('direction') == trade['dir']
            event['body'] += ' Dein '+trade['dir']+'-Trade: '+('Haupttrend intakt.' if intact else 'Bestand separat prüfen; Einstiegssignal ist kein automatischer Ausstieg.')
    return events


def notification_batches(events):
    """Existing alerts first; separate optional risk alerts for device opt-out."""
    ordinary = [e for e in events if e.get('data', {}).get('riskOnly') is not True]
    risk = [e for e in events if e.get('data', {}).get('riskOnly') is True]
    return [group for group in (ordinary, risk) if group]


def compose_events(events):
    """Urgent action first; advisory plans never compete with an exit warning."""
    priority = {'ko-hit': 0, 'stop-hit': 1, 'personal-risk': 2, 'reversal': 3,
                'risk-exit': 3, 'data-unavailable': 4, 'stop-near': 5, 'target-extension': 6, 'target': 7}
    ordered = sorted(events, key=lambda e: priority.get(e['data']['eventKind'], 8))
    message = copy.deepcopy(ordered[0])
    urgent = ordered[0]['data']['eventKind'] in ('ko-hit', 'stop-hit', 'reversal', 'risk-exit')
    advisory = {'target', 'target-extension', 'trailing-stop', 'profit-protection', 'profit-weak', 'signal-change', 'initial-stop', 'risk-warning', 'risk-confirmed'}
    visible = [e for e in ordered if not urgent or e['data']['eventKind'] not in advisory]
    message['body'] = ' | '.join(e['body'] for e in visible)
    message['data']['events'] = [e['data']['eventKind'] for e in ordered]
    if any(e['data'].get('riskOnly') for e in ordered):
        message['data']['expiresAt'] = min(e['data']['expiresAt'] for e in ordered)
        # A mixed message must retain existing critical warnings after risk opt-out.
        message['data']['riskOnly'] = all(e['data'].get('riskOnly') is True for e in ordered)
    if any(e['data']['kind'] == 'trade' for e in ordered):
        message['data']['kind'] = 'trade'
    return message

