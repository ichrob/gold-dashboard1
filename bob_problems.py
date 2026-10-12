"""Public-issue index for Bob's authenticated Problem tab.

Problems are stored as sanitized, per-category GitHub issues by the independent
watchdog. This reader never returns arbitrary user-written issue text or logs.
"""
from datetime import datetime, timezone
import json
import re
import threading
import time
from urllib.request import Request, urlopen

from bob_issue_watchdog import CODES, ISSUE_TITLE, issue_title

REPOSITORY_URL = "https://github.com/ichrob/gold-dashboard1"
ISSUES_URL = "https://api.github.com/repos/ichrob/gold-dashboard1/issues?state=open&per_page=100"
CACHE_SECONDS = 600  # Public GitHub requests share an egress IP quota.
FAILURE_RETRY_SECONDS = 120  # Retry outages sooner than successful snapshots.
_LOCK = threading.Lock()
_CACHED = None
_LAST_TRY = 0.0


def fetch_open_issues(*, opener=urlopen):
    req = Request(ISSUES_URL, headers={
        "User-Agent": "Bob-problem-index/1",
        "Accept": "application/vnd.github+json",
    })
    with opener(req, timeout=10) as response:
        raw = response.read(400001)
    if len(raw) > 400000:
        raise ValueError("Issue index too large")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Invalid GitHub issue index")
    return data


def from_issues(rows, *, now=None):
    """Whitelist descriptions, titles and links; reject PRs and unrelated issues."""
    if not isinstance(rows, list):
        raise ValueError("GitHub issues missing")
    allowed = {issue_title(code): (code, CODES[code]) for code in CODES}
    # Migration compatibility: one old combined issue, if still open.
    allowed[ISSUE_TITLE] = ("legacy-incident", "Ältere zusammengefasste KI-Hilfeanfrage")
    items = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or "pull_request" in row:
            continue
        title = row.get("title")
        number = row.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 999999999:
            continue
        if title in allowed:
            code, description = allowed[title]
        elif (isinstance(title, str) and title.startswith("[Bob KI-Hilfe] ")
              and isinstance(row.get("user"), dict)
              and row["user"].get("login") == "ichrob"):
            # Curated manual help requests from the repository owner. Never
            # reflect arbitrary public GitHub issue bodies or unknown authors.
            description = title[len("[Bob KI-Hilfe] "):].strip()
            if not description or len(description) > 150 or any(ord(c) < 32 for c in description):
                continue
            code = "manual-" + str(number)
        else:
            continue
        if code in seen:
            continue
        seen.add(code)
        created = row.get("created_at")
        updated = row.get("updated_at")
        stamp_pattern = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
        if not isinstance(created, str) or not re.fullmatch(stamp_pattern, created):
            created = None
        if not isinstance(updated, str) or not re.fullmatch(stamp_pattern, updated):
            updated = None
        items.append({
            "number": number,
            "code": code,
            "message": description,
            "createdAt": created,
            "updatedAt": updated,
            "url": REPOSITORY_URL + "/issues/" + str(number),
        })
    items.sort(key=lambda problem: problem["number"], reverse=True)
    at = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return {
        "status": "ok",
        "count": len(items),
        "problems": items,
        "checkedAt": at,
        "meaning": "offene KI-Hilfeanfragen; Lesen setzt den Zähler nicht zurück",
        "source": "sanitized-github-issues",
    }


def snapshot(*, fetcher=fetch_open_issues, clock=time.monotonic):
    """Bound repeated GitHub queries; fail visibly, never manufacture a 0."""
    global _CACHED, _LAST_TRY
    now = clock()
    with _LOCK:
        ttl = (FAILURE_RETRY_SECONDS if _CACHED is not None
               and _CACHED.get('status') != 'ok' else CACHE_SECONDS)
        if _CACHED is not None and now - _LAST_TRY < ttl:
            return dict(_CACHED)
        try:
            result = from_issues(fetcher())
        except Exception as exc:
            # No raw exception or API body may leave this endpoint.
            if _CACHED is not None and _CACHED.get("count") is not None:
                result = dict(_CACHED, status="stale")
            else:
                result = {
                    "status": "unavailable", "count": None, "problems": [],
                    "checkedAt": None, "source": "sanitized-github-issues",
                }
            print("BOB_PROBLEMS read_error=" + type(exc).__name__, flush=True)
        _CACHED = result
        _LAST_TRY = now
        return dict(result)


PANEL = r'''<section id="bobProblemPanel" class="card" style="margin:12px 0">
<h3>Offene KI-Hilfeanfragen</h3>
<p id="bobProblemsSummary" role="status" class="small">Lade gespeicherte Probleme …</p>
<p id="bobProblemsLastUpdate" class="small">Letzte Aktualisierung: wird geladen …</p>
<div id="bobRepairStatistics" style="border:1px solid #dce3ed;border-radius:12px;padding:12px;margin:12px 0">
 <h3 style="margin:0 0 8px">Bobs automatische Fehlerbehebung</h3>
 <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">
  <div><div class="small">Selbstständig erkannt</div><strong id="bobRepairDetected">—</strong></div>
  <div><div class="small">Selbst repariert · geprüft</div><strong id="bobRepairVerified">—</strong></div>
  <div><div class="small">Ohne bestätigten Neustart wieder gesund</div><strong id="bobRepairNormalized">—</strong></div>
  <div><div class="small">Reparaturversuche</div><strong id="bobRepairAttempts">—</strong></div>
 </div>
 <p id="bobRepairStatsAt" class="small" role="status">Lade dauerhaften Fehlerzähler …</p>
 <details><summary>Letzte automatische Problemerkennung und Reparatur</summary>
 <div id="bobRepairEvents" class="small">Noch keine gespeicherten Ereignisse.</div>
 </details>
 <p class="small">Gezählt werden dokumentierte Fehlerereignisse seit Aktivierung dieser Statistik, nicht sämtliche Fehler aus Bobs Vergangenheit. Ein Neustartversuch ist noch keine bestätigte Lösung. Die Zahlen liegen im privaten Speicher und bleiben nach einem Render-Neustart erhalten.</p>
</div>
<div id="bobProblemsList"></div>
<p class="small">Der Zähler zeigt, wie viele Probleme noch KI-Hilfe benötigen. Weitere Probleme erhöhen die Zahl. Nach bestätigter Behebung sinkt sie wieder. Das Öffnen der Sparte löscht keine Einträge.</p>
<button id="bobProblemsRefresh" type="button">Probleme aktualisieren</button>
<p class="small"><a target="_blank" rel="noopener noreferrer" href="https://github.com/ichrob/gold-dashboard1/issues?q=is%3Aissue+%22Bob+KI-Hilfe%22">Fehlerarchiv auf GitHub öffnen</a></p>
</section>
<script>
(function(){
 const panel=document.getElementById('bobProblemPanel');
 const source=document.querySelector('main h1')?.closest('.card');
 if(source)source.after(panel);
 let latest=null, lastStats=null, browserSnapshot=null, browserSnapshotAt=0;
 const counter=()=>document.querySelector('#bobNavigation [data-problem-count]');
 function badge(count){
  const b=counter();
  if(!b)return;
  b.hidden=!(Number.isInteger(count)&&count>0);
  b.textContent=b.hidden?'':String(count);
  const button=b.closest('button');
  if(button)button.setAttribute('aria-label',count===null?'Problem, Anzahl unbekannt':
    count===1?'Problem, 1 offene KI-Hilfeanfrage':'Problem, '+count+' offene KI-Hilfeanfragen');
 }
 function readableDate(s){
  if(!s)return 'Zeitpunkt unbekannt';
  const d=new Date(s);
  return Number.isFinite(d.getTime())?d.toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'Zeitpunkt unbekannt';
 }
 function report(item){
  return 'BOB – KI-HILFEANFRAGE #'+item.number+'\nProblem: '+item.message+
   '\nCode: '+item.code+'\nErkannt: '+readableDate(item.createdAt)+
   '\nFehlerprotokoll: '+item.url+
   '\nBitte prüfe den Fehler in GitHub und Render, suche die Ursache, teste eine sichere Behebung und veröffentliche nur geprüfte Änderungen. Keine echten Trades.';
 }
 async function copy(value, label){
  try {
   if(navigator.clipboard && window.isSecureContext)await navigator.clipboard.writeText(value);
   else {
    const t=document.createElement('textarea');t.value=value;t.style.position='fixed';t.style.opacity='0';
    document.body.append(t);t.select();
    const ok=document.execCommand('copy');t.remove();
    if(!ok)throw Error('clipboard');
   }
   label.textContent='Kopiert – Bericht hier in ChatGPT einfügen.';
  } catch(_){label.textContent='Kopieren blockiert. Bitte den GitHub-Link verwenden.';}
 }
 function renderStatistics(stats){
  let statsOk=(stats.status==='ok'||stats.status==='stale')&&
      Number.isInteger(stats.detected)&&Number.isInteger(stats.verifiedRepairs);
  if(statsOk)lastStats=stats;
  else if(lastStats&&Number.isInteger(lastStats.detected)){
   stats={...lastStats,status:'stale'};
   statsOk=true;
  }
   for(const [key,id] of [['detected','bobRepairDetected'],
                          ['verifiedRepairs','bobRepairVerified'],
                          ['normalizedWithoutVerifiedRepair','bobRepairNormalized'],
                          ['repairAttempts','bobRepairAttempts']]){
      document.getElementById(id).textContent=statsOk&&Number.isInteger(stats[key])?
       String(stats[key]):'—';
   }
   document.getElementById('bobRepairStatsAt').textContent=
      statsOk?'Zähler seit Aktivierung · zuletzt aus privatem Archiv geladen: '+
       readableDate(stats.checkedAt)+' (Schweizer Zeit)'+
       (stats.status==='stale'?' · veralteter Speicherstand':''):
       'Statistik derzeit nicht erreichbar; keine erfundenen Nullwerte.';
   const repairs=document.getElementById('bobRepairEvents');repairs.replaceChildren();
   const eventNames={'detected':'Problem erkannt','repair-attempt':'Neustart versucht',
     'repair-failed':'Neustart fehlgeschlagen','repair-verified':'Reparatur bestätigt',
     'recovered':'Störung nicht mehr erkennbar'};
   if(statsOk&&Array.isArray(stats.events)&&stats.events.length){
     for(const event of stats.events.slice(0,10)){
       const p=document.createElement('p');
       p.textContent=readableDate(event.at)+' · '+(eventNames[event.kind]||'Ereignis')+
          ' · '+(event.code||'unbekannte Ursache');repairs.append(p);
     }
   }else{
     repairs.textContent=statsOk?'Noch keine archivierten Ereignisse.':'Ereignisarchiv derzeit nicht erreichbar.';
   }
 }
 async function refreshStatistics(){
  try{
   const response=await fetch('/api/repair-statistics',{cache:'no-store',credentials:'same-origin'});
   if(!response.ok)throw Error('Reparaturarchiv nicht erreichbar');
   renderStatistics(await response.json());
  }catch(_){
   renderStatistics({status:'unavailable'});
  }
 }
 const publicCodes={
  'scanner-unreachable':'Bob-Webdienst nicht erreichbar',
  'scanner-degraded':'Markt-/Hintergrunddaten werden als beeinträchtigt gemeldet',
  'market-worker-stopped':'Marktdatensammlung läuft nicht',
  'background-not-current':'Trade-/Fibonacci-Überwachung nicht aktuell',
  'research-worker-stopped':'Täglicher Forschungs-Worker läuft nicht',
  'push-unreachable':'Push-/Datenbankdienst nicht erreichbar',
  'push-unhealthy':'Push-/Datenbank-Gesundheitsprüfung fehlgeschlagen',
  'paper-unhealthy':'Papierkonten-Hintergrundstatus beeinträchtigt'
 };
 async function publicIndex(){
  // Browser fallback is intentionally rare: Render's shared egress IP can
  // hit GitHub's unauthenticated quota despite healthy Bob services.
  const now=Date.now();
  if(browserSnapshot&&now-browserSnapshotAt<600000)
   return {...browserSnapshot,status:'stale'};
  const response=await fetch('https://api.github.com/repos/ichrob/gold-dashboard1/issues?state=open&per_page=100',
    {cache:'no-store',headers:{Accept:'application/vnd.github+json'}});
  if(!response.ok)throw Error('Öffentliche GitHub-Liste nicht erreichbar');
  const raw=await response.json();
  if(!Array.isArray(raw))throw Error('Ungültige GitHub-Liste');
  const problems=[],seen=new Set();
  const prefix='[Bob KI-Hilfe] ';
  for(const issue of raw){
   if(!issue||typeof issue!=='object'||issue.pull_request||
      !Number.isInteger(issue.number)||issue.number<=0)continue;
   const title=issue.title;
   let code='',message='';
   if(title===prefix+'Ungelöste Gesundheitsstörung'){
    code='legacy-incident';message='Ältere zusammengefasste KI-Hilfeanfrage';
   }else if(typeof title==='string'&&title.startsWith(prefix)){
    const rest=title.slice(prefix.length);
    if(Object.hasOwn(publicCodes,rest)){
     code=rest;message=publicCodes[rest];
    }else if(issue.user?.login==='ichrob'&&rest.length>0&&rest.length<=150&&!/[\x00-\x1f]/.test(rest)){
     code='manual-'+issue.number;message=rest;
    }
   }
   if(!code||seen.has(code))continue;
   seen.add(code);
   const stamp=x=>typeof x==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(x)?x:null;
   problems.push({number:issue.number,code,message,
      createdAt:stamp(issue.created_at),updatedAt:stamp(issue.updated_at),
      url:'https://github.com/ichrob/gold-dashboard1/issues/'+issue.number});
  }
  problems.sort((x,y)=>y.number-x.number);
  browserSnapshot={status:'ok',count:problems.length,problems,
     checkedAt:new Date().toISOString(),source:'public-github-browser'};
  browserSnapshotAt=now;
  return browserSnapshot;
 }
 async function refresh(){
  if(document.visibilityState==='hidden'||window.BobSession?.expired?.())return;
  const summary=document.getElementById('bobProblemsSummary');
  // Private repair counters must render even if the public issue index fails.
  void refreshStatistics();
  try {
   let data;
   try{
    const response=await fetch('/api/problems',{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)throw Error('Status nicht verfügbar');
    data=await response.json();
    if(data.status==='unavailable'||!Array.isArray(data.problems)||!Number.isInteger(data.count))
     throw Error('GitHub-Index nicht verfügbar');
   }catch(_){
    data=await publicIndex();
   }
   latest=data;
   badge(data.count);
   const items=document.getElementById('bobProblemsList');items.replaceChildren();
   summary.textContent=(data.count===1?'1 offenes Problem':data.count+' offene Probleme')+
    (data.status==='stale'?' · letzter bekannter Stand':'');
   document.getElementById('bobProblemsLastUpdate').textContent=
    'Letzte Aktualisierung der offenen KI-Hilfeanfragen: '+readableDate(data.checkedAt)+
    ' (Schweizer Zeit)'+(data.status==='stale'?' · GitHub momentan nicht erreichbar':'');
   if(data.count===0){
    const p=document.createElement('p');p.textContent='✅ Keine offenen KI-Hilfeanfragen.';items.append(p);
   }
   for(const issue of data.problems){
    const article=document.createElement('article');
    article.className='bob-problem-item';
    article.style.cssText='border:1px solid #dce3ed;border-radius:12px;padding:12px;margin:10px 0';
    const title=document.createElement('strong');title.textContent='Problem #'+issue.number+' · '+issue.message;
    const meta=document.createElement('p');meta.className='small';
    meta.textContent='Erkannt: '+readableDate(issue.createdAt)+
      ' · Letzte Änderung: '+readableDate(issue.updatedAt)+
      ' · offen · KI-Hilfe erforderlich';
    const link=document.createElement('a');link.href=issue.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Technischen Eintrag öffnen';
    const button=document.createElement('button');button.type='button';button.textContent='KI-Hilfebericht kopieren';
    const note=document.createElement('p');note.className='small';note.setAttribute('role','status');
    button.addEventListener('click',()=>copy(report(issue),note));
    article.append(title,meta,link,document.createElement('br'),button,note);
    items.append(article);
   }
  }catch(_){
   summary.textContent=latest?'⚠️ Probleme können derzeit nicht neu abgefragt werden; letzter Stand bleibt sichtbar.':'⚠️ Problemarchiv momentan nicht erreichbar – Zahl unbekannt. Bitte GitHub prüfen.';
   document.getElementById('bobProblemsLastUpdate').textContent=
     'Letzte erfolgreiche Aktualisierung: '+(latest?readableDate(latest.checkedAt):'unbekannt');
   if(!latest)badge(null);
  }
 }
 document.getElementById('bobProblemsRefresh').addEventListener('click',refresh);
 window.BobProblems={refresh,badge};
 document.addEventListener('DOMContentLoaded',()=>{if(latest)badge(latest.count);});
 refresh();
 setInterval(refresh,60000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});
})();
</script>'''
