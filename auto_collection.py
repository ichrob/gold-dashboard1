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
import product_quotes

ISIN = 'DE000FG309G0'
_lock = threading.Lock()
_thread = None
_research = {}
_next_source = 0
_failures = 0
_report = {}


def enabled():
    return os.environ.get('BOB_AUTO_COLLECTION', '') == '1'


def in_window(now):
    local = now.astimezone(ZoneInfo('Europe/Zurich'))
    return local.weekday() < 5 and 6 <= local.hour < 22


def tick(now=None):
    global _research, _next_source, _failures, _report
    now = now or datetime.now(timezone.utc)
    if not enabled():
        return
    if not in_window(now):
        with _lock:
            _report = dict(_report, enabled=True, state='paused', ready=False, evaluatedAt=now.isoformat(),
                           reason='Sammlung werktags 06–22 Uhr Schweizer Zeit')
        return
    future_estimate.ensure_collector()
    source_error = None
    if time.monotonic() >= _next_source:
        try:
            # The fixed SG adapter revalidates the exact contract identity.
            # No BNP query, provider rotation, guessed contracts or new login.
            quote = product_quotes.get_sg_quote(ISIN)
            research = quote.get('futureResearch', {})
            if research.get('contract') != future_estimate.CONTRACT:
                raise ValueError('GCZ26-Referenz momentan nicht verfügbar')
            _research = dict(research)
            _failures = 0
            _next_source = time.monotonic() + 60
        except (OSError, ValueError, TypeError, KeyError):
            _failures += 1
            _next_source = time.monotonic() + min(1800, 300 * 2**min(_failures-1, 3))
            source_error = 'GCZ26-Quelle momentan nicht verfügbar; erneuter Abruf mit Wartezeit'
    result = future_estimate.current_estimate(_research, now)
    archive_error = None
    diagnostics = {}
    spot_archive = {}
    try:
        saved = bob_validation_store.request('read', {})
        estimate_quality.restore_durable(saved['pairs'], datetime.now(timezone.utc))
        diagnostics = saved.get('diagnostics', {})
        spot_archive = bob_market_store.request('read', {}).get('diagnostics', {})
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
    reason = archive_error or source_error or ('' if ready else result.get('reason') or
              validation.get('reason') or 'Noch nicht genügend passende Vergleichspaare')
    reference_at = _research.get('underlyingAt')
    report = dict(enabled=True, state='ready' if ready else 'collecting', contract=future_estimate.CONTRACT,
                  evaluatedAt=evaluated.isoformat(), lastCycleAt=evaluated.isoformat(),
                  referenceAt=reference_at, referenceAgeSeconds=result.get('referenceAgeSeconds'),
                  estimateAvailable=bool(result.get('available')), ready=ready, reason=reason,
                  collection=result.get('collection', {}), archive=diagnostics, spotArchive=spot_archive,
                  horizons=groups, retentionHours=48, sourceIntervalSeconds=60,
                  spotIntervalSeconds=30, isExchangeRealtime=False,
                  nextSourceInSeconds=max(0, round(_next_source-time.monotonic())))
    with _lock:
        _report = report
    print('BOB_COLLECTION state='+report['state']+' pairs='+str(diagnostics.get('pairCount', 0))+
          ' estimate_available='+str(report['estimateAvailable']), flush=True)


def _run():
    while enabled():
        started = time.monotonic()
        try:
            tick()
        except Exception as exc:
            # No provider response, URL or credential is exposed.
            with _lock:
                _report.update(state='error', ready=False,
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


PANEL = '''<section id="bobAutoCollection" style="max-width:860px;margin:16px auto;padding:18px;border-radius:16px;background:white"><h3>Automatische Datensammlung</h3><p id="bobAutoStatus">Messstand wird geladen …</p><div id="bobAutoGroups"></div></section><script>
(()=>{const panel=document.getElementById('bobAutoCollection');const header=document.querySelector('h1')?.parentElement;if(header)header.after(panel);
async function update(){try{const r=await fetch('/api/collection-status',{cache:'no-store'});if(!r.ok)throw Error();const d=await r.json();const a=d.archive||{};const s=d.spotArchive||{};
document.getElementById('bobAutoStatus').textContent=(d.state==='paused'?'Sammlung pausiert':d.running?'Serverseitige Sammlung läuft':d.enabled?'Sammlung startet':'Automatische Sammlung ausgeschaltet')+' · '+(d.ready?'Genauigkeit für den aktuellen Referenzabstand ausreichend geprüft':'ABWARTEN')+' · '+(d.reason||'')+' · Messstand '+(d.evaluatedAt?new Date(d.evaluatedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'noch ausstehend')+' · '+(a.predictionCount||0)+' Schätzungen, '+(a.truthCount||0)+' GCZ26-Referenzen, '+(a.pairCount||0)+' passende Paare · '+(s.sampleCount||0)+' gespeicherte Spot-Beobachtungen · Aufbewahrung 48 Stunden';
const box=document.getElementById('bobAutoGroups');box.replaceChildren();for(const g of d.horizons||[]){const p=document.createElement('p');p.textContent=g.horizonBucket+': '+g.sampleCount+'/'+g.minSamples+' Vergleiche'+(Number.isFinite(g.meanAbsoluteError)?' · mittlerer Fehler '+g.meanAbsoluteError.toFixed(2)+' USD · größter Fehler '+g.maxAbsoluteError.toFixed(2)+' USD':'')+' · '+(g.ready?'ausreichend geprüft':'noch nicht ausreichend geprüft');box.append(p);}}
catch{document.getElementById('bobAutoStatus').textContent='Messstand momentan nicht erreichbar – keine Auswertungsfreigabe.';}}update();setInterval(update,60000);})();
</script>'''
