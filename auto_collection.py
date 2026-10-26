"""Bounded server-side GCZ26 collection, independent of browser sessions."""
import copy
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import bob_market_store
import bob_validation_store
import estimate_quality
import future_estimate
import sg_quotes
import future_analysis
import cme_reference
import investing_card
import background_push

ISIN = 'DE000FG309G0'
_lock = threading.Lock()
_thread = None
_research = {}
_next_source = 0
_failures = 0
_report = {}
_source_error = None
_next_archive = 0

# At most twenty process-local scheduler observations. These record actual
# starts/completions, not market ticks or proof of missed jobs.
_cycle_lock = threading.Lock()
_cycle_history = []


def _record_worker_cycle(started_mono, started_at, duration_ms, interval, wait_seconds):
    """Record bounded timing only; never alter the worker's sleep decision."""
    if not isinstance(started_at, datetime) or started_at.tzinfo is None:
        return
    with _cycle_lock:
        previous = _cycle_history[-1] if _cycle_history else None
        # A gap is comparable only within one process and unchanged cadence.
        gap = None
        if previous and previous["configuredSeconds"] == interval:
            delta = started_mono - previous["_startMono"]
            if delta > 0:
                gap = round(delta, 3)
        item = dict(_startMono=started_mono, startedAt=started_at.isoformat(),
                    completedAt=datetime.now(timezone.utc).isoformat(),
                    durationMs=duration_ms, configuredSeconds=interval,
                    plannedWaitSeconds=round(wait_seconds, 3),
                    observedStartGapSeconds=gap)
        _cycle_history.append(item)
        del _cycle_history[:-20]


def _worker_cycle_summary():
    with _cycle_lock:
        history = [dict(item) for item in _cycle_history]
    if not history:
        return dict(status="not-observed", observedCycles=0, readOnly=True,
                    workerMissedCyclesVerified=False,
                    scope="process-local-worker-starts-not-market-tick-proof")
    comparable = [item["observedStartGapSeconds"] for item in history
                  if item["observedStartGapSeconds"] is not None]
    last = history[-1]
    return dict(status="observed", observedCycles=len(history),
                comparableStartIntervals=len(comparable),
                maxObservedStartGapSeconds=max(comparable) if comparable else None,
                lastStartedAt=last["startedAt"],
                lastCompletedAt=last["completedAt"],
                lastDurationMs=last["durationMs"],
                configuredSeconds=last["configuredSeconds"],
                plannedWaitSeconds=last["plannedWaitSeconds"],
                lastObservedStartGapSeconds=last["observedStartGapSeconds"],
                readOnly=True, workerMissedCyclesVerified=False,
                scope="process-local-worker-starts-not-market-tick-proof")



def enabled():
    return os.environ.get('BOB_AUTO_COLLECTION', '') == '1'


def in_window(now):
    local = now.astimezone(ZoneInfo('Europe/Zurich'))
    return background_push.gold_weekend_close(now.timestamp() * 1000) is None


def paused_report(now):
    """Restore evidence while exact-contract collection is paused; spot runs separately."""
    global _next_archive, _report
    with _lock:
        report = dict(_report, enabled=True, state='paused', ready=False,
                      estimateAvailable=False, estimationReleased=True, estimatePriceUsd=None, estimateAt=None,
                      updateIntervalSeconds=30, evaluatedAt=now.isoformat(),
                      reason='Futures-Sammlung und Spotarchiv werktags durchgehend; am Wochenende pausiert',
                      retentionHours=168)
    if time.monotonic() >= _next_archive:
        _next_archive = time.monotonic() + 60
        try:
            saved = bob_validation_store.request('read', {})
            evaluated = datetime.now(timezone.utc)
            estimate_quality.restore_durable(saved['pairs'], evaluated)
            report.update(archive=saved.get('diagnostics', {}), archiveStatus='loaded',
                          archiveCheckedAt=evaluated.isoformat(),
                          horizons=[estimate_quality.quality(bob_validation_store.KEY, h, evaluated)
                                    for h in (45, 180, 600, 1200)])
        except (OSError, ValueError, TypeError, KeyError):
            report['archiveStatus'] = 'unavailable'
        try:
            spot = bob_market_store.request('read', {})
            report.update(spotArchive=spot.get('diagnostics', {}), spotArchiveStatus='loaded')
        except (OSError, ValueError, TypeError, KeyError):
            report['spotArchiveStatus'] = 'unavailable'
    with _lock:
        _report = report


def tick(now=None):
    global _research, _next_source, _failures, _report, _source_error
    now = now or datetime.now(timezone.utc)
    if not enabled():
        return
    # Gold outcomes are needed for the round-the-clock weekday signal study.
    # The spot archive must survive restarts outside the separate futures window.
    if not in_window(now):
        paused_report(now)
        return
    cycle_started = time.monotonic()
    reference_ms = None
    future_estimate.ensure_collector()
    if time.monotonic() >= _next_source:
        reference_started = time.monotonic()
        try:
            # Exact-contract source only. The SG/Onvista product-page fallback
            # is disabled by user request; no retry through SG on failure.
            research = future_analysis.fetch_reference()
            if research.get('contract') != future_estimate.CONTRACT:
                raise ValueError('GCZ26-Referenz momentan nicht verfügbar')
            future_estimate.remember_reference(research, datetime.now(timezone.utc))
            _research = dict(research)
            _failures = 0
            _source_error = None
            _next_source = time.monotonic() + 60
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            _failures += 1
            delay, source_error = future_analysis.reference_failure(exc)
            _next_source = time.monotonic() + delay
            _source_error = source_error+'; erneuter Abruf mit Wartezeit'
            # Independent exchange reference; Yahoo's cooldown stays intact.
            try:
                research = cme_reference.fetch_reference()
                future_estimate.remember_reference(research, datetime.now(timezone.utc))
                _research = dict(research)
                _failures = 0
                _source_error = None
                _next_source = time.monotonic() + 60
            except (OSError, ValueError, TypeError, KeyError, IndexError):
                backup_delay, backup_error = cme_reference.failure()
                _next_source = time.monotonic() + min(delay, backup_delay)
                _source_error += ' · ' + backup_error
        reference_ms = max(0, int((time.monotonic() - reference_started) * 1000))

    result = future_estimate.current_estimate(_research, now)
    archive_error = None
    diagnostics = {}
    spot_archive = {}
    archive_started = time.monotonic()
    try:
        saved = bob_validation_store.request('read', {})
        estimate_quality.restore_durable(saved['pairs'], datetime.now(timezone.utc))
        diagnostics = saved.get('diagnostics', {})
        spot_saved = bob_market_store.request('read', {})
        # Merge real ticks saved by another instance after a process pause.
        # Never invent observations or refresh original source timestamps.
        future_estimate.restore_spot_observations(spot_saved.get('observations', []), datetime.now(timezone.utc))
        spot_archive = spot_saved.get('diagnostics', {})
    except (OSError, ValueError, TypeError, KeyError):
        archive_error = 'Dauerhafter Messspeicher momentan nicht erreichbar'
    archive_ms = max(0, int((time.monotonic() - archive_started) * 1000))
    evaluated = datetime.now(timezone.utc)
    result = future_estimate.current_estimate(_research, evaluated)
    groups = [estimate_quality.quality(bob_validation_store.KEY, h, evaluated)
              for h in (45, 180, 600, 1200)]
    # A historic error report never grants current eligibility. Preserve the
    # original input freshness, sample/span, receipt-time and horizon gates.
    validation = result.get('validation', {})
    ready = bool(result.get('available') and validation.get('ready') and not archive_error)
    reason = archive_error or ('' if ready else _source_error or result.get('reason') or
              validation.get('reason') or 'Noch nicht genügend passende Vergleichspaare')
    reference_at = _research.get('underlyingAt')
    total_ms = max(0, int((time.monotonic() - cycle_started) * 1000))
    # These values are execution timings only, never proof of a fresh quote,
    # complete archive or an actual market-worker scheduling deadline.
    stage_timing = dict(totalMs=total_ms, referenceMs=reference_ms,
                        archiveMs=archive_ms, exceeded30s=total_ms > 30000,
                        scope='one-completed-collection-call-not-scheduler-proof')
    report = dict(enabled=True, state='ready' if ready else 'estimating' if result.get('available') else 'collecting', contract=future_estimate.CONTRACT,
                  evaluatedAt=evaluated.isoformat(), lastCycleAt=evaluated.isoformat(),
                  referenceAt=reference_at, referenceAgeSeconds=result.get('referenceAgeSeconds'),
                  referenceSource=_research.get('source'),
                  estimateAvailable=bool(result.get('available')), estimationReleased=True,
                  estimatePriceUsd=result.get('priceUsd') if result.get('available') else None,
                  estimateAt=result.get('priceAt') if result.get('available') else None,
                  updateIntervalSeconds=30, ready=ready, reason=reason,
                  collection=result.get('collection', {}), archive=diagnostics, spotArchive=spot_archive,
                  cycleTiming=stage_timing,
                  archiveStatus='unavailable' if archive_error else 'loaded',
                  spotArchiveStatus='unavailable' if archive_error else 'loaded',
                  archiveCheckedAt=evaluated.isoformat() if not archive_error else None,
                  horizons=groups, retentionHours=168, sourceIntervalSeconds=60,
                  spotIntervalSeconds=30, isExchangeRealtime=False,
                  sourceStatus=_source_error, sourceFailures=_failures,
                  estimateReason=result.get('reason'), proxyAgeSeconds=result.get('proxyAgeSeconds'),
                  nextSourceInSeconds=max(0, round(_next_source-time.monotonic())))
    with _lock:
        _report = report
    print('BOB_COLLECTION_TIMING total_ms='+str(total_ms)+
          ' reference_ms='+str(reference_ms if reference_ms is not None else 'not-due')+
          ' archive_ms='+str(archive_ms)+
          ' exceeded_30s='+str(total_ms > 30000), flush=True)
    print('BOB_COLLECTION state='+report['state']+' pairs='+str(diagnostics.get('pairCount', 0))+
          ' estimate_available='+str(report['estimateAvailable'])+
          ' reason='+str(report['reason'])+
          ' reference_source='+str(report['referenceSource'])+
          ' reference_age='+str(report['referenceAgeSeconds'])+
          ' spot_age='+str(report['proxyAgeSeconds']), flush=True)


def _run():
    while enabled():
        started = time.monotonic()
        started_at = datetime.now(timezone.utc)
        remaining = background_push.gold_weekend_seconds_remaining()
        if remaining:
            with _cycle_lock:
                _cycle_history.clear()  # A weekend break cannot be a missed cycle.
            paused_report(datetime.now(timezone.utc))
            print('BOB_COLLECTION weekend_paused until=Monday 00:00 Europe/Zurich', flush=True)
            threading.Event().wait(remaining)
            continue
        try:
            tick()
        except Exception as exc:
            # No provider response, URL or credential is exposed.
            with _lock:
                _report.update(state='error', ready=False, estimateAvailable=False,
                               estimatePriceUsd=None, estimateAt=None,
                               reason='Sammlung unterbrochen; automatischer Wiederholungsversuch',
                               errorType=type(exc).__name__)
            print('BOB_COLLECTION error='+type(exc).__name__, flush=True)
        # Total cycle time also covers errors. Do not call this a missed
        # scheduled evaluation: threads and provider clocks are distinct.
        cycle_duration_ms = max(0, int((time.monotonic()-started) * 1000))
        print('BOB_COLLECTION_CYCLE duration_ms='+str(cycle_duration_ms)+
              ' exceeded_30s='+str(cycle_duration_ms > 30000), flush=True)
        interval = background_push.degiro_poll_seconds()
        planned_wait = max(1, interval-(time.monotonic()-started))
        _record_worker_cycle(started, started_at, cycle_duration_ms, interval, planned_wait)
        threading.Event().wait(planned_wait)


def start():
    global _thread
    if not enabled():
        return
    # Existing independent worker loops, started through a single idempotent
    # supervision point. Do not restart healthy threads or invent their data.
    import auxiliary_workers
    auxiliary_workers.start_initial(True)
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name='bob-auto-collection', daemon=True)
            _thread.start()


def status():
    import future_comparison
    with _lock:
        report = copy.deepcopy(_report)
        running = bool(_thread and _thread.is_alive())
    phase = background_push.degiro_session()
    report['updateIntervalSeconds'] = 300 if phase == 'night' else 30 if phase != 'weekend' else None
    report['sessionMode'] = phase
    return dict(report, cycleCadence=_worker_cycle_summary(),
                cfdFeed=investing_card.health(), comparison=future_comparison.status(), enabled=enabled(), running=running,
                state=report.get('state', 'starting' if enabled() else 'disabled'))


def health():
    report = status()
    # The public health check deliberately excludes prices, products, archive
    # rows and empirical errors. Detailed measurement data requires Bob auth.
    return {k: report.get(k) for k in ('enabled', 'running', 'state', 'lastCycleAt', 'cfdFeed')}


PANEL = '''<section id="bobAutoCollection" style="max-width:860px;margin:16px auto;padding:18px;border-radius:16px;background:white"><h3>Automatische Future-Schätzung</h3><p id="bobAutoStatus">Messstand wird geladen …</p><div id="bobAutoGroups"></div><details id="bobFutureComparison"><summary>Spot oder Investing.com · Genauigkeitsvergleich</summary><p id="bobComparisonStatus">Vergleich startet …</p><div id="bobComparisonResults"></div><p>Spot bleibt die aktive Grundlage. Beide Modelle verwenden dieselbe GCZ26-Referenz und einen gemeinsamen Quellenzeitpunkt; nötige Zwischenwerte werden linear interpoliert. Prüfung gegen später empfangene, datierte GCZ26-Kurse (höchstens 5 Sekunden Zeitabweichung). Keine automatische Umstellung. Aufbewahrung: 7 Tage.</p></details></section><script>
(()=>{const panel=document.getElementById('bobAutoCollection');const header=document.querySelector('h1')?.parentElement;if(header)header.after(panel);
async function update(){try{const r=await fetch('/api/collection-status',{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();const a=d.archive||{};const s=d.spotArchive||{};const count=(x,k)=>Number.isInteger(x[k])?String(x[k]):'unbekannt';
document.getElementById('bobAutoStatus').textContent=(d.state==='paused'?'Sammlung pausiert':d.running?'Serverseitige Sammlung läuft':d.enabled?'Sammlung startet':'Automatische Sammlung ausgeschaltet')+' · '+(d.estimationReleased?'Schätzung zur Anzeige freigegeben · Aktualisierung alle 30 Sekunden werktags durchgehend':'Schätzung startet')+' · '+(d.estimateAvailable?'Schätzwert verfügbar':d.state==='paused'?'Aktualisierung werktags durchgehend (Zürich)':'Warte auf passende aktuelle Kursdaten')+' · '+(d.ready?'Genauigkeitstest: ausreichend Vergleiche vorhanden':'Genauigkeitstest läuft weiter')+' · '+(d.reason||'')+' · Messstand '+(d.evaluatedAt?new Date(d.evaluatedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch ausstehend')+' · '+count(a,'predictionCount')+' Schätzungen, '+count(a,'truthCount')+' GCZ26-Referenzen, '+count(a,'pairCount')+' passende Paare · '+count(s,'sampleCount')+' gespeicherte Spot-Beobachtungen · Aufbewahrung 7 Tage'+(d.archiveStatus==='unavailable'?' · Messarchiv nicht erreichbar; angezeigte Zähler gegebenenfalls letzter bekannter Stand':'')+(d.spotArchiveStatus==='unavailable'?' · Spot-Archiv nicht erreichbar':'');
const box=document.getElementById('bobAutoGroups');box.replaceChildren();for(const g of d.horizons||[]){const p=document.createElement('p');p.textContent=g.horizonBucket+': '+g.sampleCount+'/'+g.minSamples+' Vergleiche'+(Number.isFinite(g.meanAbsoluteError)?' · mittlerer Fehler '+g.meanAbsoluteError.toFixed(2)+' USD · größter Fehler '+g.maxAbsoluteError.toFixed(2)+' USD':'')+' · '+(d.state==='paused'?'gespeicherter Messstand':g.ready?'ausreichend geprüft':'noch nicht ausreichend geprüft');box.append(p);}
const c=d.comparison||{},cs=c.summary||{},out=document.getElementById('bobComparisonResults');out.replaceChildren();
document.getElementById('bobComparisonStatus').textContent=(c.state==='paused'?'Vergleich pausiert':c.state==='comparing'?'Parallele Schätzungen werden gespeichert':'Vergleich sammelt Eingangsdaten')+' · '+(c.reason||'')+' · '+(c.predictionCount??0)+' gemeinsame Schätzungen · '+(cs.count??0)+' geprüfte Paare'+(c.archiveStatus==='unavailable'?' · Archiv nicht erreichbar; Zahlen können veraltet sein':'');
if(c.current){const p=document.createElement('p');p.textContent='Schätzungen vom '+new Date(c.current.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+': Spot ≈ '+c.current.spot.toFixed(2)+' USD · Investing ≈ '+c.current.cfd.toFixed(2)+' USD';out.append(p);}
for(const g of [{...cs,bucket:'Gesamt'},...(cs.horizons||[])]){if(!g.count)continue;const p=document.createElement('p');p.textContent=g.bucket+' · '+g.count+' gemeinsame Vergleiche · mittlerer / größter Fehler: Spot '+g.spot.mae.toFixed(2)+' / '+g.spot.maximum.toFixed(2)+' USD, Investing '+g.cfd.mae.toFixed(2)+' / '+g.cfd.maximum.toFixed(2)+' USD';out.append(p);}
const verdict=document.createElement('p');verdict.textContent=c.archiveStatus==='loaded'&&cs.preliminaryReady?'Vorläufiger Vergleich über '+cs.days+' UTC-Kalendertag(e): '+(cs.lowerMeanError==='equal'?'gleicher mittlerer Fehler':(cs.lowerMeanError==='cfd'?'Investing.com':'Spot')+' hat bisher den geringeren mittleren Fehler')+'. Größte Fehler und Referenzabstände ebenfalls beachten; keine Garantie für künftige Genauigkeit.':'Noch keine ausreichende aktuelle Vergleichsbasis (zunächst mindestens 20 Paare über 10 Minuten).';out.append(verdict);}
catch{document.getElementById('bobAutoStatus').textContent='Messstand momentan nicht erreichbar.';}}update();setInterval(update,30000);})();
</script>'''
