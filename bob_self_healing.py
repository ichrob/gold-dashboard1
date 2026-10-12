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

_LOCK = threading.RLock()
_EVENTS = deque(maxlen=40)
_LAST_ATTEMPTS = {}
_ACTIVE = ()
_COOLDOWN = 180

MESSAGES = {
    "market-feed-not-current": "Gold-Kursversorgung oder Marktdatensammlung nicht aktuell",
    "background-not-current": "Trade-/Fibonacci-Hintergrundüberwachung nicht aktuell",
    "market-worker-stopped": "Worker für automatische Marktdatensammlung gestoppt",
    "background-worker-stopped": "Hintergrund-Worker nicht gestartet",
    "research-worker-stopped": "Automatischer Forschungs-Worker gestoppt",
    "unknown-service-failure": "Gesundheitsprüfung meldet eine nicht klassifizierte Störung",
}
WORKERS = {
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


def restart_worker(code, stopped, starter, *, now=None):
    """Only restart explicitly approved background threads; rate-limit attempts.

    A starter is the existing idempotent start() function. This does NOT restart
    Render, change configurations, trigger trades, or fetch market data directly.
    """
    if code not in WORKERS or not stopped:
        return False
    timestamp = time.monotonic() if now is None else now
    with _LOCK:
        if timestamp - _LAST_ATTEMPTS.get(code, float("-inf")) < _COOLDOWN:
            return False
        _LAST_ATTEMPTS[code] = timestamp
    try:
        starter()
    except Exception as exc:
        # Only the exception CLASS, never a message or arguments, is recorded.
        _append("repair-failed", code, "Neustart fehlgeschlagen (" + type(exc).__name__ + ")")
        return False
    _append("repair-attempt", code, "Kontrollierter Wiederanlauf angestoßen")
    return True


def classify(health):
    """Return fixed diagnostic codes only, never arbitrary upstream text."""
    reasons = health.get("reasons") if isinstance(health, dict) else []
    reasons = reasons if isinstance(reasons, list) else []
    codes = [r for r in reasons if isinstance(r, str) and r in MESSAGES]
    if isinstance(health, dict):
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


def observe(health):
    """Write a deduplicated local incident timeline."""
    global _ACTIVE
    codes = tuple(classify(health))
    with _LOCK:
        previous = _ACTIVE
        _ACTIVE = codes
    for code in codes:
        if code not in previous:
            _append("detected", code, MESSAGES[code])
    for code in previous:
        if code not in codes:
            _append("recovered", code, "Prüfung meldet wieder einen gesunden Zustand")
    return codes


def snapshot(health):
    codes = observe(health)
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
<p class="small">Bob startet ausgefallene, bekannte Hintergrund-Worker kontrolliert neu. Ein unabhängiger GitHub-Wächter dokumentiert ungelöste Störungen. KI-Codeänderungen erfolgen nicht ungeprüft.</p>
<div id="bobHealingHistory" class="small"></div>
<details style="margin-top:12px"><summary>KI-Hilfebericht anzeigen</summary>
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
