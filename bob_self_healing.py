"""Controlled Bob worker self-healing and privacy-safe escalation summaries.

Runtime events are deliberately volatile. The independent GitHub watchdog keeps
a durable issue history, even when a Render instance dies. This module never
changes trading strategies, product data, orders, or credentials.
"""
from collections import deque
from datetime import datetime, timezone
import re
import threading
import time

import bob_repair_store

_LOCK = threading.RLock()
_EVENTS = deque(maxlen=40)
_LAST_ATTEMPTS = {}
_ACTIVE = ()
_UNRESOLVED = set()
_SUSPECT = {}
_HEALTHY = {}
_PENDING = {}
_RESTART_HISTORY = {}
_PAUSE_LOGGED = set()
_RESTART_WINDOW = 1800
_MAX_RESTARTS = 3
_COOLDOWN = 180
_CONFIRM_SECONDS = 20

MESSAGES = {
    "repair-watch-stalled": "Reparaturüberwachung liefert keine neuen Prüfergebnisse",
    "cfd-worker-stopped": "CFD-Abrufdienst gestoppt oder Wiederanlauf unbestätigt",
    "spot-change-worker-stopped": "Spot-Tagesänderungsdienst gestoppt oder Wiederanlauf unbestätigt",
    "comparison-worker-stopped": "Quellenvergleich gestoppt oder Wiederanlauf unbestätigt",
    "market-feed-not-current": "Gold-Kursversorgung oder Marktdatensammlung nicht aktuell",
    "background-not-current": "Trade-/Fibonacci-Hintergrundüberwachung nicht aktuell",
    "market-worker-stopped": "Worker für automatische Marktdatensammlung gestoppt",
    "background-worker-stopped": "Hintergrund-Worker nicht gestartet",
    "research-worker-stopped": "Automatischer Forschungs-Worker gestoppt",
    "unknown-service-failure": "Gesundheitsprüfung meldet eine nicht klassifizierte Störung",
}
WORKERS = {
    "cfd-worker-stopped": "CFD-Abruf",
    "spot-change-worker-stopped": "Spot-Tagesänderung",
    "comparison-worker-stopped": "Quellenvergleich",
    "market-worker-stopped": "Marktdatensammlung",
    "background-worker-stopped": "Trade-/Fibonacci-Überwachung",
    "research-worker-stopped": "Strategieforschung",
}
ISSUE_URL = "https://github.com/ichrob/gold-dashboard1/issues?q=is%3Aissue+%22Bob+KI-Hilfe%22"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(kind, code, detail):
    with _LOCK:
        _EVENTS.appendleft(dict(at=_now(), kind=kind, code=code, detail=detail))
    # Private, allowlisted append-only archive; enqueue without blocking analysis.
    try:
        bob_repair_store.queue_event(kind, code)
    except ValueError:
        pass


def restart_worker(code, stopped, starter, *, now=None):
    """Attempt only an allowlisted idempotent worker restart, not a code change.

    Restarting a thread is NOT considered a successful repair. The background
    health probe must independently confirm good operation after the attempt.
    """
    if code not in WORKERS or not stopped:
        return False
    timestamp = time.monotonic() if now is None else now
    with _LOCK:
        if timestamp - _LAST_ATTEMPTS.get(code, float("-inf")) < _COOLDOWN:
            return False
        attempts = [at for at in _RESTART_HISTORY.get(code, []) if 0 <= timestamp-at < _RESTART_WINDOW]
        _RESTART_HISTORY[code] = attempts
        if len(attempts) >= _MAX_RESTARTS:
            if code not in _PAUSE_LOGGED:
                _append("repair-failed", code, "Drei Wiederanläufe ohne bestätigte Erholung; Neustarts vorübergehend pausiert, KI-Prüfung erforderlich")
                _PAUSE_LOGGED.add(code)
            return False
        _PAUSE_LOGGED.discard(code)
        attempts.append(timestamp)
        _LAST_ATTEMPTS[code] = timestamp
        if code not in _UNRESOLVED:
            _UNRESOLVED.add(code)
            _append("detected", code, MESSAGES[code])
    try:
        starter()
    except Exception as exc:
        _append("repair-failed", code, "Neustart fehlgeschlagen (" + type(exc).__name__ + ")")
        return False
    with _LOCK:
        _PENDING[code] = dict(at=timestamp, startedWall=time.time(), healthySince=None, goodChecks=0)
        _HEALTHY.pop(code, None)
    _append("repair-attempt", code, "Kontrollierter Wiederanlauf angestoßen; Erfolg noch nicht bestätigt")
    return True


def _post_restart_success_time(value, code):
    """True only for a timestamped *new successful cycle* after restart.

    Market worker uses an ISO clock, other workers may use seconds or
    milliseconds. Require an original timezone-aware source timestamp;
    boolean/naive/future/stale/invalid values can never approve a repair.
    """
    from math import isfinite
    if code not in WORKERS or not isinstance(health := _PENDING.get(code), dict):
        return False
    start = health.get("startedWall")
    if type(start) not in (int, float) or not isfinite(start):
        return False
    if type(value) in (int, float) and isfinite(value):
        at = float(value)
        if at > 1e11:  # Unix milliseconds, not observation count.
            at /= 1000.0
    elif isinstance(value, str) and len(value) <= 48:
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return False
            at = parsed.timestamp()
        except (ValueError, OverflowError):
            return False
    else:
        return False
    clock = time.time()
    return start < at <= clock and 0 <= clock - at <= 650


def worker_healthy(code, health):
    """A recent original success *after* restart, not merely a running flag."""
    if code in ("cfd-worker-stopped", "spot-change-worker-stopped", "comparison-worker-stopped"):
        state=(health.get('auxiliaryWorkers') or {}).get(code) or {}
        at=state.get('successfulAt')
        pending=_PENDING.get(code) or {}
        return bool(state.get('running') and isinstance(at,(int,float))
                    and at > pending.get('startedWall',float('inf')) and 0 <= time.time()-at <= 650
                    and state.get('state') not in ('unavailable','error','stale','starting')
                    and (code!='comparison-worker-stopped' or state.get('archiveStatus')=='loaded'))
    collection = health.get("automaticCollection") or {}
    bg = health.get("fibonacciMonitor") or {}
    research = health.get("strategyResearch") or {}
    if code == "market-worker-stopped":
        return bool(collection.get("enabled") and collection.get("running")
                    and collection.get("state") in ("ready", "estimating", "collecting")
                    and _post_restart_success_time(collection.get("lastCycleAt"), code)
                    and "market-feed-not-current" not in health.get("reasons", []))
    if code == "background-worker-stopped":
        return bool(bg.get("configured") and bg.get("status") in ("active", "idle")
                    and _post_restart_success_time(bg.get("lastSuccessAt"), code)
                    and "background-not-current" not in health.get("reasons", []))
    if code == "research-worker-stopped":
        return bool(research.get("enabled") and research.get("running")
                    and research.get("phase") not in ("retry", "unconfigured", "starting")
                    and _post_restart_success_time(research.get("lastSuccessAt"), code))
    return False


def classify(health):
    """Return fixed diagnostic codes only, never arbitrary upstream text."""
    reasons = health.get("reasons") if isinstance(health, dict) else []
    reasons = reasons if isinstance(reasons, list) else []
    codes = [r for r in reasons if isinstance(r, str) and r in MESSAGES]
    if isinstance(health, dict):
        for code,state in (health.get('auxiliaryWorkers') or {}).items():
            if code in WORKERS and isinstance(state,dict) and state.get('running') is False:
                codes.append(code)
        collection = health.get("automaticCollection") or {}
        background = health.get("fibonacciMonitor") or {}
        research = health.get("strategyResearch") or {}
        if collection.get("enabled") and not collection.get("running"):
            codes.append("market-worker-stopped")
        if background.get("configured") and background.get("status") == "unavailable":
            codes.append("background-not-current")
        if research.get("enabled") and not research.get("running"):
            codes.append("research-worker-stopped")
        if health.get("status") == "degraded" and not codes:
            codes.append("unknown-service-failure")
    return sorted(set(codes))


def observe(health, *, now=None):
    """Debounced incident recognition and independent confirmation of recovery.

    A 20-second repeated healthy observation is required to mark a repair as
    verified. Normal recovery without a documented restart is kept separate.
    """
    global _ACTIVE
    timestamp = time.monotonic() if now is None else now
    codes = tuple(classify(health))
    broken = set(codes)
    with _LOCK:
        _ACTIVE = codes
        for code in broken:
            if code in _UNRESOLVED:
                _SUSPECT.pop(code, None)
                _HEALTHY.pop(code, None)
                continue
            first = _SUSPECT.setdefault(code, timestamp)
            if timestamp - first >= _CONFIRM_SECONDS:
                _UNRESOLVED.add(code)
                _SUSPECT.pop(code, None)
                _append("detected", code, MESSAGES[code])
        for code in list(_SUSPECT):
            if code not in broken:
                _SUSPECT.pop(code, None)

        for code, pending in list(_PENDING.items()):
            if worker_healthy(code, health):
                if pending["healthySince"] is None:
                    pending["healthySince"] = timestamp
                progress=(health.get('auxiliaryWorkers') or {}).get(code)
                if progress is None or progress.get('successfulAt') != pending.get('lastSuccess'):
                    pending["goodChecks"] += 1
                    if progress is not None:pending['lastSuccess']=progress.get('successfulAt')
                if pending["goodChecks"] >= 2 and timestamp - pending["healthySince"] >= _CONFIRM_SECONDS:
                    # This is an explicitly confirmed outcome after Bob's own
                    # restart; it is not a profitable trade or a strategy fix.
                    _append("repair-verified", code, "Eigenständiger Wiederanlauf durch wiederholte Gesundheitsprüfung bestätigt")
                    _PENDING.pop(code, None)
                    _RESTART_HISTORY.pop(code, None)
                    _PAUSE_LOGGED.discard(code)
                    _UNRESOLVED.discard(code)
                    _HEALTHY.pop(code, None)
                    _append("recovered", code, "Nach Wiederanlauf gesund gemeldet")
            else:
                pending["healthySince"] = None
                pending["goodChecks"] = 0
                pending.pop("lastSuccess", None)
        for code in list(_UNRESOLVED):
            if code in broken or code in _PENDING:
                _HEALTHY.pop(code, None)
                continue
            first, checks = _HEALTHY.get(code, (timestamp, 0))
            checks += 1
            if checks >= 2 and timestamp - first >= _CONFIRM_SECONDS:
                _UNRESOLVED.discard(code)
                _HEALTHY.pop(code, None)
                _append("recovered", code, "Störung nicht mehr feststellbar (kein bestätigter eigener Neustart)")
            else:
                _HEALTHY[code] = (first, checks)
    return codes


def pending_codes():
    """Fixed codes only; a running thread must not close an unverified repair."""
    with _LOCK:
        return sorted(code for code in _PENDING if code in WORKERS)


def snapshot(health):
    codes = sorted(set(observe(health)) | set(pending_codes()))
    build = str(health.get("build") or "unbekannt")
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", build):
        build = "unbekannt"
    timestamp = _now()
    with _LOCK:
        events = list(_EVENTS)[:12]
    active = [dict(code=code, message=MESSAGES[code]) for code in codes]
    status = "hilfe-noetig" if codes else "bereit"
    if codes:
        code_lines = "\n".join("- " + code + ": " + MESSAGES[code] for code in codes)
        report = (
            "BOB – ANFRAGE AUF KI-HILFE\n"
            "Status: Automatische Reparatur war nicht ausreichend oder ist noch nicht bestätigt.\n"
            "Geprüft (UTC): " + timestamp + "\n"
            "Build: " + build + "\n"
            "Diagnose:\n" + code_lines + "\n"
            "Bereits vorgesehen: Sichere Worker-Neustarts mit Wartefrist und erneuter Gesundheitsprüfung.\n"
            "Bitte prüfe die Ursache in GitHub/Render, schlage eine gezielte Korrektur vor, "
            "führe Tests durch und übernimm nur geprüfte Änderungen. Keine Echtgeldorders "
            "oder automatische Änderung von Handelsstrategien.\n"
            "Hinweis: Der Bericht enthält absichtlich weder Zugangsdaten noch private Handelsdaten."
        )
    else:
        report = (
            "BOB – PRÜFBERICHT\n"
            "Geprüft (UTC): " + timestamp + "\n"
            "Status: Keine aktuelle Störung durch die lokale Gesundheitsprüfung erkannt.\n"
            "Für externe Ausfälle siehe das unabhängige GitHub-Fehlerarchiv."
        )
    return dict(status=status, checkedAt=timestamp, active=active, recentEvents=events,
                helpRequest=report, issueArchiveUrl=ISSUE_URL,
                scope="Arbeitsthreads und öffentliche Gesundheitsprüfungen; kein Beleg für Kursgenauigkeit",
                automaticCodeFixes=False)


PANEL = r'''<section id="bobSelfHealing" class="card" style="margin:16px 0;padding:16px">
<details><summary style="font-weight:700;cursor:pointer">🛠️ Fehlerüberwachung &amp; Selbstreparatur</summary>
<p id="bobHealingState" role="status">Prüfung wird geladen …</p>
<p class="small">Bob startet ausgefallene Hintergrunddienste einschließlich CFD-Abruf, Spot-Tagesänderung und Quellenvergleich kontrolliert neu. Nach drei unbestätigten Wiederanläufen innerhalb von 30 Minuten pausiert er weitere Neustarts. Ein unabhängiger GitHub-Wächter dokumentiert ungelöste Störungen. KI-Codeänderungen erfolgen nicht ungeprüft.</p>
<div id="bobHealingHistory" class="small"></div>
<details hidden aria-hidden="true" style="margin-top:12px"><summary>KI-Hilfebericht anzeigen</summary>
<pre id="bobHealingReport" style="white-space:pre-wrap;word-break:break-word;max-height:330px;overflow:auto;background:#f4f6f9;border-radius:9px;padding:10px"></pre>
<button type="button" id="bobHealingCopy">KI-Hilfebericht kopieren</button>
<span id="bobHealingCopyStatus" role="status" class="small"></span></details>
<p><a href="https://github.com/ichrob/gold-dashboard1/issues?q=is%3Aissue+%22Bob+KI-Hilfe%22" target="_blank" rel="noopener noreferrer">Gespeicherte Fehler und KI-Anfragen auf GitHub öffnen</a></p>
</details></section>
<script>
(function(){
 const panel=document.getElementById('bobSelfHealing');
 const heading=document.querySelector('main h1');
 const card=heading&&heading.closest('.card');
 if(card)card.after(panel);
 let report='';
 const state=document.getElementById('bobHealingState');
 const history=document.getElementById('bobHealingHistory');
 const pre=document.getElementById('bobHealingReport');
 async function refresh(){
   if(document.visibilityState==='hidden'||window.BobSession?.expired?.())return;
   try{
     const r=await fetch('/api/self-healing',{cache:'no-store',credentials:'same-origin'});
     if(!r.ok)throw Error('Status '+r.status);
     const d=await r.json();
     state.textContent=d.active.length
       ?'⚠️ KI-Hilfe erforderlich oder Wiederanlauf noch nicht bestätigt: '+d.active.map(x=>x.message).join(' · ')
       :'✅ Keine aktuell erkannte Störung · letzte Prüfung: '+new Date(d.checkedAt).toLocaleString('de-CH',{timeZone:'Europe/Zurich'});
     state.style.color=d.active.length?'#ad321f':'#177443';
     history.replaceChildren();
     for(const row of d.recentEvents.slice(0,8)){
       const p=document.createElement('p');
       p.textContent=new Date(row.at).toLocaleString('de-CH',{timeZone:'Europe/Zurich'})+
         ' · '+row.detail+' ['+row.kind+']';
       history.append(p);
     }
     report=d.helpRequest||'';
     pre.textContent=report;
   }catch(_){
     state.textContent='Fehlerüberwachung derzeit nicht erreichbar. Externes Fehlerarchiv prüfen.';
     state.style.color='#ad321f';
   }
 }
 document.getElementById('bobHealingCopy').addEventListener('click',async()=>{
   const note=document.getElementById('bobHealingCopyStatus');
   if(!report){note.textContent='Noch kein Bericht verfügbar.';return;}
   try{
     if(navigator.clipboard && window.isSecureContext)await navigator.clipboard.writeText(report);
     else {
       const t=document.createElement('textarea');t.value=report;t.style.position='fixed';t.style.opacity='0';
       document.body.appendChild(t);t.select();
       if(!document.execCommand('copy'))throw Error('Kopieren gesperrt');
       t.remove();
     }
     note.textContent='Kopiert – du kannst den Bericht in ChatGPT einfügen.';
   }catch(_){note.textContent='Bitte den Text oben markieren und kopieren.';}
 });
 refresh();setInterval(refresh,60000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});
})();
</script>'''


def diagnostics_snapshot():
    """Observe existing state without running observe(), repairs or persistence."""
    with _LOCK:
        return {'status':'observed','activeCodes':sorted(_UNRESOLVED),
                'pendingCodes':sorted(_PENDING),
                'events':[{'at':e.get('at'),'kind':e.get('kind'),'code':e.get('code')}
                          for e in list(_EVENTS)[:20]],
                'scope':'process-local-repair-events-durable-history-in-push-report'}
