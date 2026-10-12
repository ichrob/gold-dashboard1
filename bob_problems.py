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
CACHE_SECONDS = 90
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
        if title not in allowed or not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 999999999:
            continue
        code, description = allowed[title]
        if code in seen:
            continue
        seen.add(code)
        created = row.get("created_at")
        if not isinstance(created, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", created):
            created = None
        items.append({
            "number": number,
            "code": code,
            "message": description,
            "createdAt": created,
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
        if _CACHED is not None and now - _LAST_TRY < CACHE_SECONDS:
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
 let latest=null;
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
 async function refresh(){
  if(document.visibilityState==='hidden'||window.BobSession?.expired?.())return;
  const summary=document.getElementById('bobProblemsSummary');
  try {
   const response=await fetch('/api/problems',{cache:'no-store',credentials:'same-origin'});
   if(!response.ok)throw Error('Status nicht verfügbar');
   const data=await response.json();
   if(data.status==='unavailable'||!Array.isArray(data.problems)||!Number.isInteger(data.count))
    throw Error('Index nicht verfügbar');
   latest=data;
   badge(data.count);
   const items=document.getElementById('bobProblemsList');items.replaceChildren();
   summary.textContent=(data.count===1?'1 offenes Problem':data.count+' offene Probleme')+
    (data.status==='stale'?' · letzter gespeicherter Stand, Aktualisierung momentan nicht möglich':' · Status geprüft '+readableDate(data.checkedAt));
   if(data.count===0){
    const p=document.createElement('p');p.textContent='✅ Keine offenen KI-Hilfeanfragen.';items.append(p);
   }
   for(const issue of data.problems){
    const article=document.createElement('article');
    article.className='bob-problem-item';
    article.style.cssText='border:1px solid #dce3ed;border-radius:12px;padding:12px;margin:10px 0';
    const title=document.createElement('strong');title.textContent='Problem #'+issue.number+' · '+issue.message;
    const meta=document.createElement('p');meta.className='small';meta.textContent='Erkannt: '+readableDate(issue.createdAt)+' · offen · KI-Hilfe erforderlich';
    const link=document.createElement('a');link.href=issue.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Technischen Eintrag öffnen';
    const button=document.createElement('button');button.type='button';button.textContent='KI-Hilfebericht kopieren';
    const note=document.createElement('p');note.className='small';note.setAttribute('role','status');
    button.addEventListener('click',()=>copy(report(issue),note));
    article.append(title,meta,link,document.createElement('br'),button,note);
    items.append(article);
   }
  }catch(_){
   summary.textContent=latest?'⚠️ Probleme können derzeit nicht neu abgefragt werden; letzter Stand bleibt sichtbar.':'⚠️ Problemarchiv momentan nicht erreichbar – Zahl unbekannt. Bitte GitHub prüfen.';
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
