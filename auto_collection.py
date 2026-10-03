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

ISIN = 'DE000FG309G0'
_lock = threading.Lock()
_thread = None
_research = {}
_next_source = 0
_failures = 0
_report = {}
_source_error = None
_next_archive = 0


def enabled():
    return os.environ.get('BOB_AUTO_COLLECTION', '') == '1'


def in_window(now):
    local = now.astimezone(ZoneInfo('Europe/Zurich'))
    return local.weekday() < 5 and 6 <= local.hour < 22


def paused_report(now):
    """Restore measured evidence after a restart without polling market feeds."""
    global _next_archive, _report
    with _lock:
        report = dict(_report, enabled=True, state='paused', ready=False,
                      estimateAvailable=False, estimationReleased=True, estimatePriceUsd=None, estimateAt=None,
                      updateIntervalSeconds=30, evaluatedAt=now.isoformat(),
                      reason='Sammlung werktags 06–22 Uhr Schweizer Zeit',
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
    if not in_window(now):
        paused_report(now)
        return
    future_estimate.ensure_collector()
    if time.monotonic() >= _next_source:
        try:
            # Existing exact-contract Yahoo feed; no SG OTC/FX prerequisite.
            # Fixed fallback to the registered onvista underlying, no guessed
            # contract, continuous future or source timestamp replacement.
            try:
                research = future_analysis.fetch_reference()
            except (OSError, ValueError, TypeError, KeyError, IndexError) as primary_error:
                try:
                    research = sg_quotes.fetch_future_reference()
                except (OSError, ValueError, TypeError, KeyError, IndexError):
                    # Preserve Yahoo's failure and shared retry deadline when
                    # the fixed fallback is unavailable (including consent).
                    raise primary_error
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
    result = future_estimate.current_estimate(_research, now)
    archive_error = None
    diagnostics = {}
    spot_archive = {}
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
    evaluated = datetime.now(timezone.utc)
    result = future_estimate.current_estimate(_research, evaluated)
    groups = [estimate_quality.quality(bob_validation_store.KEY, h, evaluated)
              for h in (45, 180, 600, 1200)]
    # A historic error report never grants current eligibility. Preserve the
    # original input freshness, sample/span, receipt-time and horizon gates.
    validation = result.get('validation', {})
    ready = bool(result.get('available') and validation.get('ready') and not archive_error)
    reason = archive_error or ('' if ready else result.get('reason') or _source_error or
              validation.get('reason') or 'Noch nicht genügend passende Vergleichspaare')
    reference_at = _research.get('underlyingAt')
    report = dict(enabled=True, state='ready' if ready else 'estimating' if result.get('available') else 'collecting', contract=future_estimate.CONTRACT,
                  evaluatedAt=evaluated.isoformat(), lastCycleAt=evaluated.isoformat(),
                  referenceAt=reference_at, referenceAgeSeconds=result.get('referenceAgeSeconds'),
                  referenceSource=_research.get('source'),
                  estimateAvailable=bool(result.get('available')), estimationReleased=True,
                  estimatePriceUsd=result.get('priceUsd') if result.get('available') else None,
                  estimateAt=result.get('priceAt') if result.get('available') else None,
                  updateIntervalSeconds=30, ready=ready, reason=reason,
                  collection=result.get('collection', {}), archive=diagnostics, spotArchive=spot_archive,
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
    print('BOB_COLLECTION state='+report['state']+' pairs='+str(diagnostics.get('pairCount', 0))+
          ' estimate_available='+str(report['estimateAvailable'])+
          ' reason='+str(result.get('reason') or validation.get('reason') or '')+
          ' reference_age='+str(report['referenceAgeSeconds'])+
          ' spot_age='+str(report['proxyAgeSeconds']), flush=True)


def _run():
    while enabled():
        started = time.monotonic()
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
        threading.Event().wait(max(1, 30-(time.monotonic()-started)))


def start():
    global _thread
    if not enabled():
        return
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name='bob-auto-collection', daemon=True)
            _thread.start()


def status():
    with _lock:
        report = copy.deepcopy(_report)
        running = bool(_thread and _thread.is_alive())
    return dict(report, enabled=enabled(), running=running,
                state=report.get('state', 'starting' if enabled() else 'disabled'))


def health():
    report = status()
    # The public health check deliberately excludes prices, products, archive
    # rows and empirical errors. Detailed measurement data requires Bob auth.
    return {k: report.get(k) for k in ('enabled', 'running', 'state', 'lastCycleAt')}


PANEL = '''<section id="bobAutoCollection" style="max-width:860px;margin:16px auto;padding:18px;border-radius:16px;background:white"><h3>Automatische Future-Schätzung</h3><p id="bobAutoStatus">Messstand wird geladen …</p><div id="bobAutoGroups"></div></section><script>
(()=>{const panel=document.getElementById('bobAutoCollection');const header=document.querySelector('h1')?.parentElement;if(header)header.after(panel);
async function update(){try{const r=await fetch('/api/collection-status',{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();const a=d.archive||{};const s=d.spotArchive||{};const count=(x,k)=>Number.isInteger(x[k])?String(x[k]):'unbekannt';
document.getElementById('bobAutoStatus').textContent=(d.state==='paused'?'Sammlung pausiert':d.running?'Serverseitige Sammlung läuft':d.enabled?'Sammlung startet':'Automatische Sammlung ausgeschaltet')+' · '+(d.estimationReleased?'Schätzung zur Anzeige freigegeben · Aktualisierung alle 30 Sekunden während der Sammelzeiten':'Schätzung startet')+' · '+(d.estimateAvailable?'Schätzwert verfügbar':d.state==='paused'?'Aktualisierung werktags 06–22 Uhr (Zürich)':'Warte auf passende aktuelle Kursdaten')+' · '+(d.ready?'Genauigkeitstest: ausreichend Vergleiche vorhanden':'Genauigkeitstest läuft weiter')+' · '+(d.reason||'')+' · Messstand '+(d.evaluatedAt?new Date(d.evaluatedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch ausstehend')+' · '+count(a,'predictionCount')+' Schätzungen, '+count(a,'truthCount')+' GCZ26-Referenzen, '+count(a,'pairCount')+' passende Paare · '+count(s,'sampleCount')+' gespeicherte Spot-Beobachtungen · Aufbewahrung 7 Tage'+(d.archiveStatus==='unavailable'?' · Messarchiv nicht erreichbar; angezeigte Zähler gegebenenfalls letzter bekannter Stand':'')+(d.spotArchiveStatus==='unavailable'?' · Spot-Archiv nicht erreichbar':'');
const box=document.getElementById('bobAutoGroups');box.replaceChildren();for(const g of d.horizons||[]){const p=document.createElement('p');p.textContent=g.horizonBucket+': '+g.sampleCount+'/'+g.minSamples+' Vergleiche'+(Number.isFinite(g.meanAbsoluteError)?' · mittlerer Fehler '+g.meanAbsoluteError.toFixed(2)+' USD · größter Fehler '+g.maxAbsoluteError.toFixed(2)+' USD':'')+' · '+(d.state==='paused'?'gespeicherter Messstand':g.ready?'ausreichend geprüft':'noch nicht ausreichend geprüft');box.append(p);}}
catch{document.getElementById('bobAutoStatus').textContent='Messstand momentan nicht erreichbar.';}}update();setInterval(update,30000);})();
</script>'''
