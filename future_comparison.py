"""Independent shadow comparison; never changes current_estimate or trade inputs."""
import copy
import threading
import time
from datetime import datetime, timezone

import bob_validation_store
import comparison_store
import future_estimate
import investing_card
import background_push

_lock = threading.Lock()
_thread = None
_report = {}
_ticks = []


def aligned(ticks, target):
    rows = sorted(ticks, key=lambda t: future_estimate.stamp(t['at']))
    before = [r for r in rows if 0 <= (target-future_estimate.stamp(r['at'])).total_seconds() <= 30]
    after = [r for r in rows if 0 <= (future_estimate.stamp(r['at'])-target).total_seconds() <= 30]
    if not before or not after:raise ValueError('Zeitgleiche Spot-/CFD-Beobachtung fehlt (maximal 30 Sekunden je Seite)')
    a, b = before[-1], after[0]
    ta, tb = future_estimate.stamp(a['at']), future_estimate.stamp(b['at'])
    weight = (target-ta).total_seconds()/(tb-ta).total_seconds() if tb != ta else 0
    point = dict(a, at=target.isoformat(), price=a['price']+weight*(b['price']-a['price']))
    return [r for r in rows if future_estimate.stamp(r['at']) < target]+[point], ta != tb


def predict(research, spots, cfds, now):
    if not spots or not cfds:raise ValueError('Spot- und CFD-Beobachtungen werden gesammelt')
    target = min(max(future_estimate.stamp(r['at']) for r in spots),
                 max(future_estimate.stamp(r['at']) for r in cfds))
    if not 0 <= (now-target).total_seconds() <= 60:raise ValueError('Gemeinsamer Quellenzeitpunkt nicht aktuell')
    if (target-future_estimate.stamp(research['underlyingAt'])).total_seconds() <= 5:
        raise ValueError('Warte auf Bewegung nach der Future-Referenz')
    spot_rows, si = aligned(spots, target)
    cfd_rows, ci = aligned(cfds, target)
    spot = future_estimate.calculate(research, spot_rows, now, 'gold-api-spot')
    cfd = future_estimate.calculate(research, cfd_rows, now, 'investing-cfd')
    for result in (spot, cfd):
        if not result['available']:raise ValueError(result.get('reason', 'Schätzung noch nicht verfügbar'))
    return dict(type='prediction', at=target.isoformat(), referenceAt=research['underlyingAt'],
                spot=spot['priceUsd'], cfd=cfd['priceUsd']), si or ci


def tick(now=None):
    import auto_collection
    now = now or datetime.now(timezone.utc)
    with _lock:report = dict(_report)
    report.update(activeSource='Gold-Spot', automaticSwitch=False, evaluatedAt=now.isoformat(),
                  state='collecting' if auto_collection.in_window(now) else 'paused',
                  current=None, reason='', archiveStatus='unavailable')
    events = []
    if auto_collection.in_window(now):
        with future_estimate._lock:
            research = dict(future_estimate._research_reference)
            spots = copy.deepcopy(future_estimate._spot_ticks)
        try:
            # Archive truth even if the CFD feed fails. The original quote
            # time is retained; archive first receipts enforce no lookahead.
            if research.get('contract') == 'GCZ26':
                truth = dict(type='truth', at=research['underlyingAt'], value=research['underlyingPriceUsd'])
                comparison_store.checked(truth, now)
                events.append(truth)
            q = investing_card.fetch()
            if q.get('declaredContract') != 'GCZ26' or not q.get('realtimeCfd'):
                raise ValueError('Investing-CFD: Dezember-2026-Zuordnung oder aktuelle Kursdaten fehlen')
            at = future_estimate.stamp(q['at'])
            if not 0 <= (datetime.now(timezone.utc)-at).total_seconds() <= 60:
                raise ValueError('Investing-CFD älter als 60 Sekunden')
            if _ticks and at == future_estimate.stamp(_ticks[-1]['at']) and q['price'] != _ticks[-1]['price']:
                raise ValueError('CFD-Quellenzeit mit widersprüchlichem Kurs')
            if not _ticks or at > future_estimate.stamp(_ticks[-1]['at']):
                _ticks.append(dict(at=q['at'], price=q['price'], contract='GCZ26', proxyKind='investing-cfd'))
            _ticks[:] = [t for t in _ticks if (now-future_estimate.stamp(t['at'])).total_seconds() <= 3600][-240:]
            report['cfdAt'] = q['at']
            prediction, interpolated = predict(research, spots, _ticks, datetime.now(timezone.utc))
            events.append(prediction)
            report.update(current=prediction, interpolated=interpolated, state='comparing')
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError) as exc:
            report['reason'] = str(exc) if isinstance(exc, ValueError) else 'Vergleichsdaten momentan nicht verfügbar'
    else:
        report['reason'] = 'Vergleich werktags 06–22 Uhr (Zürich); gespeicherte Ergebnisse bleiben erhalten'
    try:
        saved = bob_validation_store.request('write' if events else 'read',
            dict(key=comparison_store.KEY, events=events), key=comparison_store.KEY)
        report.update(summary=saved['summary'], predictionCount=saved['predictionCount'],
                      truthCount=saved['truthCount'], archiveStatus='loaded')
    except (OSError, ValueError, TypeError, KeyError):
        report['reason'] += ' · Vergleichsarchiv nicht erreichbar; neue Messungen nicht gesichert'
    with _lock:
        _report.clear()
        _report.update(report)


def _run():
    import auto_collection
    while auto_collection.enabled():
        remaining = background_push.gold_weekend_seconds_remaining()
        if remaining:
            with _lock:
                _report.update(state='paused', current=None,
                               reason='Goldmarkt geschlossen · Vergleich bis Montag 00:00 (Zürich) pausiert')
            threading.Event().wait(remaining)
            continue
        started = time.monotonic()
        try:tick()
        except Exception as exc:
            with _lock:_report.update(state='error', current=None, reason='Vergleich unterbrochen; automatischer Wiederholungsversuch')
            print('BOB_COMPARISON error='+type(exc).__name__, flush=True)
        interval = background_push.degiro_poll_seconds()
        threading.Event().wait(max(1, interval-(time.monotonic()-started)))


def start():
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name='bob-future-comparison', daemon=True)
            _thread.start()


def status():
    with _lock:return copy.deepcopy(_report)
