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
from urllib.error import HTTPError

from bob_issue_watchdog import CODES, ISSUE_TITLE, issue_title

REPOSITORY_URL = "https://github.com/ichrob/gold-dashboard1"
ISSUES_URL = "https://api.github.com/repos/ichrob/gold-dashboard1/issues?state=open&per_page=100"
CACHE_SECONDS = 600  # Public GitHub requests share an egress IP quota.
FAILURE_RETRY_SECONDS = 120  # Retry outages sooner than successful snapshots.
_LOCK = threading.Lock()
_CACHED = None
_LAST_TRY = 0.0
_RETRY_AFTER = 0.0
_ETAG = None
_ISSUE_ROWS = None

# A tiny machine-readable, public-safe status marker in issue bodies is the
# return channel from the hourly ChatGPT repair task back to Bob's phone UI.
# Markers never imply that a product quote, lever, KO or trade is approved.
MANUAL_LABELS = {
    'training-signal-start-evidence-history': 'Historische Signaltests: ursprüngliche Startdaten unvollständig',
    'training-signal-followup-evidence-history': 'Historische Signaltests: ursprüngliche Folgekurse fehlen',
}

KI_STATUS_LABELS = {
    "new": "Wartet auf KI-Prüfung",
    "needs-user": "Deine Hilfe ist nach KI-Prüfung nötig",
    "in-progress": "KI prüft die Ursache",
    "testing": "Reparatur in technischer Prüfung",
    "waiting-for-evidence": "Originalnachweis fehlt weiterhin",
    "waiting-for-review": "Änderung wartet auf Freigabeprüfung",
}
_KI_MARKER = re.compile(r"(?m)^<!-- BOB_KI_STATUS:(in-progress|testing|waiting-for-evidence|waiting-for-review|needs-user) -->$")
# Owner-authored code-review pointer. Never proof that a live fault has recovered.
_REVIEW_MARKER = re.compile(
    r"(?m)^<!-- BOB_KI_REVIEW:pr=([1-9][0-9]{0,7});sha=([a-f0-9]{40});phase=(proposed|ci-tested|deployed-unverified) -->$")


def ki_review(issue):
    author = issue.get("user")
    if not isinstance(author, dict) or author.get("login") not in ("ichrob", "github-actions[bot]"):
        return None
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 8000:
        return None
    matches = _REVIEW_MARKER.findall(body)
    if not matches:
        return None
    pr, commit, phase = matches[-1]
    return {"pr": int(pr), "commit": commit, "phase": phase}



def ki_status(issue):
    # All arbitrary issue prose is ignored; only allowlisted markers from
    # the trusted repository owner or the GitHub Actions watchdog are used.
    author = issue.get("user")
    if not isinstance(author, dict) or author.get("login") not in ("ichrob", "github-actions[bot]"):
        return "new"
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 8000:
        return "new"
    matches = _KI_MARKER.findall(body)
    return matches[-1] if matches else "new"



def fetch_open_issues(*, opener=urlopen):
    global _ETAG, _ISSUE_ROWS
    req = Request(ISSUES_URL, headers={
        "User-Agent": "Bob-problem-index/1",
        "Accept": "application/vnd.github+json",
    })
    if _ETAG and _ISSUE_ROWS is not None:
        req.add_header('If-None-Match', _ETAG)
    try:
        with opener(req, timeout=10) as response:
            raw = response.read(400001)
            etag = response.headers.get('ETag')
    except HTTPError as exc:
        if exc.code == 304 and _ISSUE_ROWS is not None:
            return _ISSUE_ROWS
        raise
    if len(raw) > 400000:
        raise ValueError("Issue index too large")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("Invalid GitHub issue index")
    _ETAG, _ISSUE_ROWS = etag, data
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
            description = MANUAL_LABELS.get(description, description)
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
        state = ki_status(row)
        items.append({
            "number": number,
            "code": code,
            "message": description,
            "createdAt": created,
            "updatedAt": updated,
            "url": REPOSITORY_URL + "/issues/" + str(number),
            "kiStatus": state,
            "kiStatusLabel": KI_STATUS_LABELS[state],
            "caseId": "BOB-" + str(number) + "-" + code,
            "review": ki_review(row),
        })
    items.sort(key=lambda problem: problem["number"], reverse=True)
    at = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return {
        "status": "ok",
        "count": len(items),
        "problems": items,
        "resolved": [],
        "checkedAt": at,
        "meaning": "offene KI-Hilfeanfragen; Lesen setzt den Zähler nicht zurück",
        "source": "sanitized-github-issues",
    }


def snapshot(*, fetcher=None, clock=time.monotonic):
    """Bound repeated GitHub queries; fail visibly, never manufacture a 0."""
    global _CACHED, _LAST_TRY, _RETRY_AFTER
    now = clock()
    with _LOCK:
        ttl = (FAILURE_RETRY_SECONDS if _CACHED is not None
               and _CACHED.get('status') != 'ok' else CACHE_SECONDS)
        mirror_fresh=True
        if _CACHED and _CACHED.get('source')=='sanitized-github-watchdog-snapshot' and _CACHED.get('status')=='ok':
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(_CACHED['checkedAt'])).total_seconds()
                mirror_fresh=age<=1200
            except (ValueError,TypeError,KeyError):mirror_fresh=False
        quota_wait=now < _RETRY_AFTER and (fetcher is not None or (_CACHED or {}).get('status')=='ok')
        if _CACHED is not None and mirror_fresh and (quota_wait or now - _LAST_TRY < ttl):
            return dict(_CACHED)
        try:
            if fetcher is not None:result = from_issues(fetcher())
            else:
                try:
                    import bob_problem_mirror
                    result = bob_problem_mirror.read()
                except Exception:
                    if now < _RETRY_AFTER:raise OSError('Statusquelle wartet auf Freigabe des Abruflimits')
                    result = from_issues(fetch_open_issues())
            _RETRY_AFTER = 0.0
        except Exception as exc:
            # No raw exception or API body may leave this endpoint.
            if _CACHED is not None and _CACHED.get("count") is not None:
                result = dict(_CACHED, status="stale")
            else:
                result = {
                    "status": "unavailable", "count": None, "problems": [],
                    "checkedAt": None, "source": "sanitized-github-issues",
                }
            detail = ''
            if isinstance(exc, HTTPError):
                detail = ' http_status=' + str(exc.code)
                if exc.code in (403, 429):
                    # Shared Render egress can exhaust GitHub's anonymous quota.
                    # Honor the server's wait instead of retrying every 2 minutes.
                    headers = exc.headers or {}
                    delay = 600
                    for value, relative in ((headers.get('Retry-After'), True),
                                            (headers.get('X-RateLimit-Reset'), False)):
                        try:
                            seconds = float(value) - (0 if relative else time.time())
                            if 0 < seconds < 86400: delay = max(delay, seconds + 1)
                        except (TypeError, ValueError): pass
                    _RETRY_AFTER = now + delay
            print("BOB_PROBLEMS read_error=" + type(exc).__name__ + detail, flush=True)
        _CACHED = result
        _LAST_TRY = now
        return dict(result)


PANEL = r'''<section id="bobProblemPanel" class="card" style="margin:12px 0">
<h3>Offene KI-Hilfeanfragen</h3>
<p class="small">Zuerst prüft Bob selbst. Technische Hilferufe bearbeitet der geplante ChatGPT-Reparaturwächter stündlich, nicht sofort. Nur ausdrücklich mit „Deine Hilfe ist nötig“ markierte Fälle benötigen eine Nutzeraktion. Kritische Trade-Warnungen bleiben unabhängig davon sichtbar.</p>
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
 <details id="bobOpenKiProblems" style="margin:12px 0">
 <summary><strong>Offene Probleme für ChatGPT</strong> <span id="bobOpenKiCount">· wird geladen …</span></summary>
 <p class="small">Automatisch zur KI-Prüfung erfasst. Der Reparaturwächter ruft diese Fälle stündlich ab; erfasst bedeutet noch nicht gelesen oder gelöst.</p>
 <div id="bobProblemsList"></div>
 </details>
 <details><summary>Letzte automatische Problemerkennung und Reparatur</summary>
 <div id="bobRepairEvents" class="small">Noch keine gespeicherten Ereignisse.</div>
 </details>
 <p class="small">Gezählt werden dokumentierte Fehlerereignisse seit Aktivierung dieser Statistik, nicht sämtliche Fehler aus Bobs Vergangenheit. Ein Neustartversuch ist noch keine bestätigte Lösung. Die Zahlen liegen im privaten Speicher und bleiben nach einem Render-Neustart erhalten.</p>
</div>
<p id="bobProblemsBreakdown" class="small" role="status"></p>
<details id="bobVerifiedRecoveries" style="border:1px solid #dce3ed;border-radius:12px;padding:10px;margin:10px 0">
<summary><strong>Technisch nachgeprüfte Erholungen</strong> <span id="bobRecoveriesCount">—</span></summary>
<p class="small">Zwei Prüfungen erkennen eine frühere technische Störung nicht mehr. Dies ist kein Beweis für einen ChatGPT-Fix, und keine Produkt- oder Handelsfreigabe.</p>
<div id="bobRecoveriesList"></div>
</details>
<p class="small">Der Zähler zeigt, wie viele Probleme noch KI-Hilfe benötigen. Weitere Probleme erhöhen die Zahl. Nach bestätigter Behebung sinkt sie wieder. Das Öffnen der Sparte löscht keine Einträge.</p>
<p class="small">Ungelöste technische Meldungen werden vom eingerichteten KI-Reparaturwächter automatisch geprüft. Du musst keinen Bericht teilen.</p>
<div hidden aria-hidden="true">
<button id="bobProblemsShare" type="button" style="width:100%;min-height:46px;background:#1563b5;color:white;font-weight:700;border-radius:10px">Fehlerdiagnose an ChatGPT teilen · ohne Kopieren</button>
<p id="bobProblemsShareStatus" role="status" class="small">Beim Teilen ChatGPT auswählen und den Bericht dort selbst absenden. Nur freigegebene technische Fehlercodes; keine Kontodaten, Logins oder Handelsaufträge.</p>
<div id="bobProblemsShareFallback" hidden>
  <button id="bobProblemsCopy" type="button">Ersatzweg: Bericht kopieren</button>
  <textarea id="bobProblemsShareText" readonly aria-label="Fehlerdiagnose zum manuellen Kopieren" style="width:100%;min-height:145px"></textarea>
</div>
</div>
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
 function renderRecoveries(data){
  const list=document.getElementById('bobRecoveriesList');
  const count=document.getElementById('bobRecoveriesCount');
  const rows=Array.isArray(data?.resolved)?data.resolved:[];
  list.replaceChildren();
  count.textContent=data?.status==='stale'?'(Stand veraltet)':'('+rows.length+')';
  if(!rows.length){list.textContent='Keine unabhängig dokumentierte Erholung im Verlauf. Das bedeutet nicht, dass keine Fehler vorliegen.';return;}
  for(const item of rows.slice(0,20)){
    if(!item||!Number.isInteger(item.number)||!Object.hasOwn(publicCodes,item.code))continue;
    const p=document.createElement('p');p.className='small';
    const a=document.createElement('a');a.href='https://github.com/ichrob/gold-dashboard1/issues/'+item.number;
    a.textContent='Fall BOB-'+item.number+'-'+item.code;a.target='_blank';a.rel='noopener noreferrer';
    p.append(a,document.createTextNode(' · zweimaliger Gesundheitscheck: '+readableDate(item.verifiedAt)));
    list.append(p);
  }
 }
 function badge(count){
  window.BobProblemsArchiveCount=count;
  // Private per-product KI-help counts stay off public GitHub issues.
  const productCount=window.BobProductAuditHelpCount;
  const extra=Number.isInteger(productCount)?productCount:0;
  const breakdown=document.getElementById('bobProblemsBreakdown');
  if(breakdown)breakdown.textContent=(Number.isInteger(count)?count:'Unbekannte Anzahl')+
   ' technische KI-Hilfeanfragen · '+(Number.isInteger(productCount)?productCount:'Unbekannte Anzahl')+
   ' Produktprobleme. Der rote Zähler zählt beide Bereiche; Produktdetails stehen weiter unten.';
  const combined=Number.isInteger(count)?count+extra:(extra>0?extra:null);
  const b=counter();
  if(!b)return;
  b.hidden=!(Number.isInteger(combined)&&combined>0);
  b.textContent=b.hidden?'':String(combined);
  const button=b.closest('button');
  if(button)button.setAttribute('aria-label',combined===null?'Problem, Anzahl unbekannt':
    combined===1?'Problem, 1 offene KI-Hilfeanfrage':'Problem, '+combined+' offene KI-Hilfeanfragen');
 }
 function readableDate(s){
  if(!s)return 'Zeitpunkt unbekannt';
  const d=new Date(s);
  return Number.isFinite(d.getTime())?d.toLocaleString('de-CH',{timeZone:'Europe/Zurich'}):'Zeitpunkt unbekannt';
 }
 function report(item){
  return 'BOB – KI-HILFEANFRAGE #'+item.number+'\nProblem: '+item.message+
   '\nCode: '+item.code+'\nErkannt: '+readableDate(item.createdAt)+
   '\nStatus: '+(item.kiStatusLabel||'Noch nicht geprüft')+
   '\nLetzte Bearbeitung: '+readableDate(item.updatedAt)+
   '\nFehlerprotokoll: '+item.url+
   '\nBitte prüfe den Fehler in GitHub und Render. Dokumentiere einen echten PR-Nachweis anschließend in genau dieser GitHub-Issue gemäß BOB_DIAGNOSTIC_CHATGPT_HANDOFF.md. Nicht ohne unabhängigen Health-Nachweis als behoben melden. Keine echten Trades.';
 }
 // Privacy boundary: export ONLY allowlisted technical issue codes, safe
 // issue identifiers and aggregate counts. Never raw messages or logs.
 function diagnosticShareText(snapshot,stats){
  const state=['ok','stale'].includes(snapshot?.status)?snapshot.status:'unavailable';
  const count=state==='unavailable'||!Number.isInteger(snapshot?.count)||
    snapshot.count<0||snapshot.count>1000?'unbekannt':String(snapshot.count);
  const checkedAt=typeof snapshot?.checkedAt==='string'&&
    /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)$/.test(snapshot.checkedAt)?
    snapshot.checkedAt:'nicht nachgewiesen';
  const items=state==='unavailable'||!Array.isArray(snapshot?.problems)?[]:
    snapshot.problems.filter(item=>item&&Number.isInteger(item.number)&&item.number>0&&
      item.number<100000000&&typeof item.code==='string'&&
      (Object.hasOwn(publicCodes,item.code)||/^manual-\d{1,8}$/.test(item.code)))
      .slice(0,20);
  const lines=[
    'BOB-FEHLERDIAGNOSE/1 · bewusst vom Nutzer per Android geteilt',
    'Projekt: ichrob/gold-dashboard1 · Dienste: bob-private-scanner / bob-push-service',
    'Auftrag: Prüfe die Fehler anhand von GitHub und Render; recherchiere Ursache, Tests und sichere Korrektur. Wenn ein echter Code-PR vorliegt, aktualisiere nur nach nachweisbarer Prüfung die bestehende GitHub-Issue (Fall-ID) mit einem BOB_KI_STATUS- und BOB_KI_REVIEW-Marker gemäß BOB_DIAGNOSTIC_CHATGPT_HANDOFF.md. Einen Code-Fix niemals als unabhängig bestätigte Reparatur melden. Keine Echtgeldorders oder Handelsfreigaben.',
    'Indexstatus: '+state+(state==='stale'?' (nicht als aktuell bestätigen)':''),
    'Indexzeit (UTC): '+checkedAt,
    'Offene technische KI-Hilfeanfragen laut Index: '+count,
    'Produktprobleme: separat in Bob/Produkte prüfen; hier nicht enthalten.',
    'Gemeldete Codekorrekturen sind keine unabhängig bestätigten Reparaturen.'
  ];
  if(state==='unavailable')lines.push('Technische Fehlerliste derzeit nicht verfügbar; nicht als fehlerfrei interpretieren.');
  else if(count==='0')lines.push('Im Index keine offenen technischen KI-Hilfeanfragen; kein Beweis allgemeiner Fehlerfreiheit.');
  else if(!items.length)lines.push('Keine einzeln freigegebenen Fehlerdetails verfügbar. Bitte GitHub selbst prüfen.');
  for(const item of items){
    const desc=Object.hasOwn(publicCodes,item.code)?publicCodes[item.code]:
      'Manuelle KI-Hilfeanfrage; genauer Inhalt nicht automatisch geteilt';
    const stage=Object.hasOwn(kiStatusLabels,item.kiStatus)?kiStatusLabels[item.kiStatus]:
      kiStatusLabels.new;
    lines.push('Fall BOB-'+item.number+'-'+item.code+' · '+desc+' · '+stage+
      ' · https://github.com/ichrob/gold-dashboard1/issues/'+item.number);
  }
  if(state!=='unavailable'&&count!=='unbekannt'&&Number(count)>items.length)
    lines.push('Weitere Probleme möglich; maximal 20 geprüfte Einträge aufgeführt.');
  const validStats=stats&&['ok','stale'].includes(stats.status);
  for(const [key,label] of [['detected','Problemereignisse'],['verifiedRepairs','Bestätigte Reparaturen']]){
    const num=validStats&&Number.isInteger(stats[key])&&stats[key]>=0&&stats[key]<1000000?
      String(stats[key]):'nicht nachgewiesen';
    lines.push(label+': '+num+(validStats&&stats.status==='stale'?' (veraltet)':''));
  }
  lines.push('Quelle: freigegebene Fehlercodes und aggregierte Reparaturzähler. Keine Logins, Screenshots, Depotdaten oder Originalproduktwerte.');
  lines.push('Das Teilen bestätigt weder ChatGPT-Empfang noch Fehlerbehebung.');
  return lines.join('\n');
 }
 function shareToChatGPT(){
  // Called directly from a tap; do not await a fetch before native share.
  const value=diagnosticShareText(latest,lastStats);
  const status=document.getElementById('bobProblemsShareStatus');
  document.getElementById('bobProblemsShareText').value=value;
  document.getElementById('bobProblemsShareFallback').hidden=false;
  if(typeof navigator.share!=='function'){
    status.textContent='Android-Teilen hier nicht verfügbar. Bericht unten kopieren und in ChatGPT einfügen.';
    return;
  }
  try{
    const result=navigator.share({title:'Bob · technische Fehlerdiagnose',text:value});
    status.textContent='Android-Teilen geöffnet: ChatGPT auswählen und die Nachricht dort selbst absenden. Empfang nicht bestätigt.';
    Promise.resolve(result).then(()=>{
      status.textContent='Teilen-Dialog beendet. Ob ChatGPT den Bericht erhalten hat, dort prüfen und selbst absenden.';
    },error=>{
      status.textContent=error?.name==='AbortError'?
        'Teilen abgebrochen. Keine automatische Übertragung; Ersatzbericht verfügbar.':
        'Android-Teilen fehlgeschlagen. Ersatzweg: Bericht kopieren und in ChatGPT einfügen.';
    });
  }catch(_){status.textContent='Android-Teilen nicht möglich. Bericht unten kopieren und in ChatGPT einfügen.';}
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
 const publicCodes=__BOB_PUBLIC_CODES__;
 const manualDescriptions=__BOB_MANUAL_LABELS__;
 const kiStatusLabels={
   'new':'Wartet auf KI-Prüfung',
   'needs-user':'Deine Hilfe ist nach KI-Prüfung nötig',
   'in-progress':'KI prüft die Ursache',
   'testing':'Reparatur in technischer Prüfung',
   'waiting-for-evidence':'Originalnachweis fehlt weiterhin',
   'waiting-for-review':'Änderung wartet auf Freigabeprüfung'
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
     code='manual-'+issue.number;message=manualDescriptions[rest]||rest;
    }
   }
   if(!code||seen.has(code))continue;
   seen.add(code);
   const stamp=x=>typeof x==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(x)?x:null;
   let kiStatus='new';
   if(['ichrob','github-actions[bot]'].includes(issue.user?.login)&&
      typeof issue.body==='string'&&issue.body.length<=8000){
     const matches=[...issue.body.matchAll(/^<!-- BOB_KI_STATUS:(in-progress|testing|waiting-for-evidence|waiting-for-review|needs-user) -->$/gm)];
     if(matches.length)kiStatus=matches[matches.length-1][1];
   }
   let review=null;
   if(['ichrob','github-actions[bot]'].includes(issue.user?.login)&&typeof issue.body==='string'&&issue.body.length<=8000){
     const matches=[...issue.body.matchAll(/^<!-- BOB_KI_REVIEW:pr=([1-9][0-9]{0,7});sha=([a-f0-9]{40});phase=(proposed|ci-tested|deployed-unverified) -->$/gm)];
     if(matches.length){const m=matches[matches.length-1];review={pr:Number(m[1]),commit:m[2],phase:m[3]};}
   }
   problems.push({number:issue.number,code,message,kiStatus,kiStatusLabel:kiStatusLabels[kiStatus],
      caseId:'BOB-'+issue.number+'-'+code,review,
      createdAt:stamp(issue.created_at),updatedAt:stamp(issue.updated_at),
      url:'https://github.com/ichrob/gold-dashboard1/issues/'+issue.number});
  }
  problems.sort((x,y)=>y.number-x.number);
  browserSnapshot={status:'ok',count:problems.length,problems,resolved:[],
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
    if(data.status==='stale'||data.status==='unavailable'||!Array.isArray(data.problems)||!Number.isInteger(data.count))
     throw Error('GitHub-Index nicht verfügbar');
   }catch(_){
    try{data=await publicIndex();}
    catch(error){
     if(!data||!Array.isArray(data.problems)||!Number.isInteger(data.count))throw error;
     data={...data,status:'stale'};
    }
   }
   latest=data;
   badge(data.count);
   document.getElementById('bobOpenKiCount').textContent='· '+data.count+(data.status==='stale'?' · letzter bekannter Stand':'');
   renderRecoveries(data);
   const items=document.getElementById('bobProblemsList');items.replaceChildren();
   summary.textContent=(data.count===1?'1 offenes Problem':data.count+' offene Probleme')+
    (data.status==='stale'?' · letzter bekannter Stand':'');
   document.getElementById('bobProblemsLastUpdate').textContent=
    'Letzte Aktualisierung der offenen KI-Hilfeanfragen: '+readableDate(data.checkedAt)+
    ' (Schweizer Zeit)'+(data.status==='stale'?' · GitHub momentan nicht erreichbar':'');
   if(data.count===0){
    const p=document.createElement('p');p.textContent='Keine offenen technischen KI-Hilfeanfragen. Produktprobleme werden separat aufgeführt.';items.append(p);
   }
   for(const issue of data.problems){
    const article=document.createElement('article');
    article.className='bob-problem-item';
    article.style.cssText='border:1px solid #dce3ed;border-radius:12px;padding:12px;margin:10px 0';
    const title=document.createElement('strong');title.textContent=issue.message;
    const meta=document.createElement('p');meta.className='small';
    meta.textContent='Fall #'+issue.number+' · Erkannt: '+readableDate(issue.createdAt)+
      ' · Letzte Änderung: '+readableDate(issue.updatedAt)+
      ' · offen · '+(issue.kiStatusLabel||kiStatusLabels.new);
    const link=document.createElement('a');link.href=issue.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Technischen Eintrag öffnen';
    const button=document.createElement('button');button.type='button';button.textContent='KI-Hilfebericht kopieren';
    const note=document.createElement('p');note.className='small';note.setAttribute('role','status');
    button.addEventListener('click',()=>copy(report(issue),note));
    article.append(title,meta,link);
    const review=issue.review;
    if(review&&Number.isInteger(review.pr)&&review.pr>0&&
       typeof review.commit==='string'&&/^[a-f0-9]{40}$/.test(review.commit)&&
       ['proposed','ci-tested','deployed-unverified'].includes(review.phase)){
      const evidence=document.createElement('p');evidence.className='small';
      evidence.textContent='Gemeldeter Codebericht ('+review.phase+') – noch keine unabhängig bestätigte Fehlerbehebung: ';
      const pr=document.createElement('a');pr.href='https://github.com/ichrob/gold-dashboard1/pull/'+review.pr;
      pr.target='_blank';pr.rel='noopener noreferrer';pr.textContent='PR #'+review.pr;
      evidence.append(pr);article.append(evidence);
    }
    if(issue.kiStatus==='needs-user'){
     const action=document.createElement('p');action.textContent='Deine Hilfe ist nötig. Öffne den technischen Eintrag für die konkrete Rückfrage.';action.style.fontWeight='700';article.append(action);
    }
    items.append(article);
   }
  }catch(_){
   // The last successful snapshot is no longer independently current.
   // Never share a failed refresh with the previous 'ok' freshness flag.
   if(latest)latest={...latest,status:'stale'};
   summary.textContent=latest?'⚠️ Probleme können derzeit nicht neu abgefragt werden; letzter Stand bleibt sichtbar.':'⚠️ Problemarchiv momentan nicht erreichbar – Zahl unbekannt. Bitte GitHub prüfen.';
   document.getElementById('bobProblemsLastUpdate').textContent=
     'Letzte erfolgreiche Aktualisierung: '+(latest?readableDate(latest.checkedAt):'unbekannt');
   document.getElementById('bobOpenKiCount').textContent=latest?'· '+latest.count+' · letzter bekannter Stand':'· Anzahl unbekannt';
   if(!latest){
    badge(null);
    document.getElementById('bobProblemsList').textContent='Offene Probleme können momentan nicht geladen werden.';
   }
   if(latest)renderRecoveries({...latest,status:'stale'});
  }
 }
 document.getElementById('bobProblemsRefresh').addEventListener('click',refresh);
 document.getElementById('bobProblemsShare').addEventListener('click',shareToChatGPT);
 document.getElementById('bobProblemsCopy').addEventListener('click',()=>{
  copy(document.getElementById('bobProblemsShareText').value,document.getElementById('bobProblemsShareStatus'));
 });
 window.BobProblems={refresh,badge,shareToChatGPT};
 document.addEventListener('DOMContentLoaded',()=>{if(latest)badge(latest.count);});
 refresh();
 setInterval(refresh,60000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});
})();
</script>'''

# Keep server and browser fallback categories identical as new monitors are added.
PANEL = PANEL.replace("__BOB_PUBLIC_CODES__", json.dumps(CODES, ensure_ascii=True))

PANEL = PANEL.replace("__BOB_MANUAL_LABELS__", json.dumps(MANUAL_LABELS, ensure_ascii=True))

# Keep reliability metrics inside the existing Problems navigation section.
from source_reliability_panel import PANEL as RELIABILITY_PANEL
PANEL = PANEL.replace('<p id="bobProblemsBreakdown"', RELIABILITY_PANEL+'<p id="bobProblemsBreakdown"')
