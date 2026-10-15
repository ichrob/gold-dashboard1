"""Read-only, evidence-scoped status overview for Bob's eight app areas.

Only an explicitly proven check gets a green checkmark. This is not a
certificate that all code in a feature is bug-free or that a trade is safe.
Data stays in the authenticated app; the browser only reads existing APIs.
"""

PANEL = r'''<details id="bobAreaChecks" hidden class="card bob-disclosure" aria-label="Gesamtprüfung aller Bob-Bereiche" style="margin:12px 0">
<summary>Gesamtprüfung · alle Bereiche</summary>
<p id="bobAreaSummary" role="status" class="small">Bereichsprüfung noch nicht abgeschlossen.</p>
<p id="bobAreaCheckedAt" class="small">Letzter Prüfversuch: noch keiner.</p>
<div id="bobAreaRows" style="display:grid;gap:8px"></div>
<button type="button" id="bobAreaRefresh" style="margin-top:12px">Alle Bereiche jetzt prüfen</button>
<p class="small">✓ = genau die genannten Prüfungen bestätigt; ⚠ = erkannte Störung oder offenes Problem; ? = Nachweis fehlt bzw. Bereich nur teilweise prüfbar. Ein Haken ist keine Garantie für Fehlerfreiheit oder Handelsfreigabe. Keine Push-Nachrichten, Orders oder Änderungen an Risikoregeln.</p>
</details>
<script>
(function(){
 'use strict';
 const areas=[
  ['overview','Übersicht / Marktanalyse'],
  ['products','Gold-Hebelprodukte'],
  ['trade','Mein Trade'],
  ['auto','Vollautomatisch'],
  ['future','Zukunft'],
  ['research','YouTube / Recherche'],
  ['learning','Lernen / Simulationen'],
  ['problems','Problem / KI-Hilfe']
 ];
 const root=document.getElementById('bobAreaChecks');
 const byId=id=>document.getElementById(id);
 const nodes={};let busy=false, last=null, at=null;
 const marker={ok:'✓',warning:'⚠',unknown:'?'};
 const colors={ok:'#166534',warning:'#92400e',unknown:'#526070'};
 const statuses={ok:'Bestätigt',warning:'Problem',unknown:'Nicht vollständig geprüft'};
 const say=(state,reason)=>({state,reason});
 const known=(x)=>x&&typeof x==='object'&&!Array.isArray(x);
 const number=(x)=>typeof x==='number'&&Number.isFinite(x);
 const time=(x)=>typeof x==='number'?x*1000:Date.parse(x);
 const age=(x)=>{const t=time(x);return Number.isFinite(t)?Date.now()-t:Infinity;};
 const swissDay=(t)=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(t));
 const fmt=(t)=>new Date(t).toLocaleString('de-CH',{timeZone:'Europe/Zurich',dateStyle:'short',timeStyle:'medium'});
 async function read(path,ms=12000){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),ms);
  try{
   const res=await fetch(path,{credentials:'same-origin',cache:'no-store',signal:ctl.signal});
   if(!res.ok&&!(path==='/health/background'&&res.status===503))return null;
   const data=await res.json();
   return known(data)?data:null;
  }catch(_){return null;}finally{clearTimeout(timer);}
 }
 function issueMatch(items,area){
  return items.find(x=>{
   const code=String(x.code||''),desc=String(x.message||'');
   if(area==='products')return code.startsWith('product-')||/Emittent|Hebel|Produktdaten|DEGIRO/i.test(desc);
   if(area==='research')return /MCO|Video|Untertitel|Transkript|Recherche/i.test(desc);
   if(area==='trade')return /trade|background|push-/i.test(code);
   if(area==='learning')return /paper-|simulation/i.test(code+' '+desc);
   if(area==='overview')return /scanner-|market-|background-/i.test(code);
   if(area==='future')return /research-worker/i.test(code);
   return false;
  });
 }
 function makeNodes(){
  const list=byId('bobAreaRows');
  for(const [key,name] of areas){
   const row=document.createElement('div');
   row.style.cssText='border:1px solid #dce3ed;border-radius:10px;padding:10px 12px';
   const head=document.createElement('div');
   head.style.cssText='display:flex;align-items:center;gap:8px';
   const flag=document.createElement('strong');flag.style.cssText='font-size:19px;min-width:18px';flag.textContent='?';
   const nameEl=document.createElement('strong');nameEl.textContent=name;
   const state=document.createElement('span');state.className='small';state.textContent='Nicht geprüft';
   state.style.marginLeft='auto';head.append(flag,nameEl,state);
   const detail=document.createElement('p');detail.className='small';detail.style.margin='6px 0 0';
   detail.textContent='Aktuelle Prüfergebnisse fehlen.';
   row.append(head,detail);list.append(row);
   nodes[key]={flag,state,detail};
  }
 }
 function mount(){
  const parent=byId('bob-view-problems');
  if(parent){parent.prepend(root);root.hidden=false;}
 }
 function render(result){
  const summary={ok:0,warning:0,unknown:0};
  for(const [key] of areas){
   const entry=result[key]||say('unknown','Noch nicht geprüft');
   const status=entry.state in marker?entry.state:'unknown';
   summary[status]++;
   const n=nodes[key];n.flag.textContent=marker[status];n.flag.style.color=colors[status];
   n.state.textContent=statuses[status];n.state.style.color=colors[status];
   n.detail.textContent=entry.reason;

  }
  byId('bobAreaSummary').textContent=summary.ok+' bestätigt · '+summary.warning+' mit Problemen · '+summary.unknown+' nicht vollständig geprüft.';
  byId('bobAreaCheckedAt').textContent='Letzter Prüfversuch: '+fmt(at)+' (Schweizer Zeit). Daten nur beim Anzeigen der App aktualisiert.';
 }
 async function refresh(){
  if(busy||document.visibilityState==='hidden'||window.BobSession?.expired?.())return;
  busy=true;byId('bobAreaRefresh').disabled=true;
  byId('bobAreaSummary').textContent='Prüfe die vorhandenen Quellen …';
  try{
   const [health,background,live,audit,research,future,problems]=await Promise.all([
    read('/health',8000),read('/health/background',8000),read('/api/live',15000),
    read('/api/degiro/audit',13000),read('/api/gold-research',10000),
    read('/api/zukunft/research',12000),read('/api/problems',10000)
   ]);
   const issues=problems?.status==='ok'&&Array.isArray(problems.problems)&&
    Number.isInteger(problems.count)?problems.problems:null;
   const out={};
   const backgroundOk=background?.status==='ok';
   const healthOk=health?.status==='ok'&&health?.ready===true;
   const bars=live?.history?.bars_by_tf;
   const validBars=known(bars)&&['5m','15m','1h'].every(tf=>Array.isArray(bars[tf])&&bars[tf].length>=30);
   const warnings=live?.marketReview?.warnings;
   if(health?.status==='degraded'||background?.status==='unavailable'||
      live?.status==='partial'||(Array.isArray(warnings)&&warnings.length))
    out.overview=say('warning','Marktdaten, Marktanalyse oder Hintergrundtakt eingeschränkt. Marktprüfung und Zeitstempel kontrollieren.');
   else if(healthOk&&backgroundOk&&live?.status==='fresh'&&
      number(live?.spots?.xaus)&&live.spots.xaus>0&&
      age(live.spots.spot_price_as_of)>=0&&age(live.spots.spot_price_as_of)<=150000&&
      validBars&&Array.isArray(warnings)&&warnings.length===0)
    out.overview=say('ok','Gold-Spot, Quellzeit, 5m/15m/1h-Historie, Markt-Eingangsprüfung und Hintergrundtakt bestätigt. Keine Aussage über Vorhersagegüte.');
   else out.overview=say('unknown','Marktanalyse derzeit nicht vollständig belegbar (Kurszeit, Kerzen, Quellabgleich oder Serverabruf).');
   const rows=Array.isArray(audit?.items)?audit.items:null;
   const recent=age(audit?.lastCheckedAt)>=0&&age(audit?.lastCheckedAt)<=300000;
   const listTime=time(audit?.listUploadedAt);
   const listToday=Number.isFinite(listTime)&&swissDay(listTime)===swissDay(Date.now());
   if(audit?.status==='ok'&&rows&&rows.length>0&&Number.isInteger(audit.incomplete)&&
      audit.incomplete>0)
    out.products=say('warning',audit.incomplete+' Produkte mit fehlenden oder veralteten Nachweisen. Details unter Gold-Hebelprodukte.');
   else if(audit?.status==='ok'&&rows&&rows.length>0&&audit.incomplete===0&&recent&&listToday&&
      rows.every(x=>['issuer-evidence-complete','terminated'].includes(x.state)))
    out.products=say('ok',rows.length+' Produkte mit geprüften Emittenten-Nachweisen bzw. korrekt als beendet markiert. Keine DEGIRO-Orderfreigabe.');
   else out.products=say('unknown','Aktuelle Screenshotliste, letzte Prüfung oder vollständige Quellen-/Zeitnachweise nicht bestätigt.');
   out.trade=background?.status==='unavailable'
    ?say('warning','Stopp-/Fibonacci-Hintergrundüberwachung aktuell nicht funktionsfähig.')
    :say('unknown',backgroundOk?'Hintergrundüberwachung erreichbar; individueller Trade, Stop, KO und Brokerpreis nicht vollständig geprüft.':'Trade-Überwachung und individuelle Produktkurse nicht nachgewiesen.');
   out.auto=say('unknown','Auto-Simulation und Wieder-Einstieg benötigen eigene Ergebnis- und Ausführungskontrolle. Keine Broker-Automation freigegeben.');
   const rt=future?.runtime;
   out.future=known(future)&&future.mode==='RESEARCH_ONLY'&&rt?.running===true
    ?say('unknown','Forschungs-Worker läuft; Broker-Handelbarkeit und spätere API-Integration nicht geprüft.')
    :say('unknown','Zukunft-Forschung oder Broker-Nachweis derzeit nicht vollständig überprüfbar.');
   if(research?.fresh===false||research?.successfulFeeds===0)
    out.research=say('warning','MCO-Videofeed fehlt oder ist veraltet. Untertitel und Zusammenfassungen separat prüfen.');
   else if(research?.fresh===true&&research.successfulFeeds>0)
    out.research=say('unknown','MCO-Feed aktuell; Transkriptzugang, Videoinhalte und Zusammenfassungen noch nicht vollständig bestätigt.');
   else out.research=say('unknown','Videorecherche aktuell nicht zuverlässig prüfbar.');
   out.learning=say('unknown','Simulationen 100/300/800 €, Ausführungen und Ergebnisse benötigen einen unabhängigen aktuellen Paper-Statusnachweis.');
   out.problems=issues===null
    ?say('unknown','Das gespeicherte KI-Hilfe-/Problemarchiv ist nicht aktuell erreichbar.')
    :issues.length
      ?say('warning',issues.length+' offene öffentliche KI-Hilfeanfragen; private Produktfälle zusätzlich unter Produkte.')
      :say('ok','Öffentliches KI-Hilfe-Archiv erfolgreich abgefragt: keine offenen Einträge. Andere, nicht überwachte Fehler bleiben möglich.');
   if(issues){
    for(const key of ['overview','products','trade','future','research','learning']){
     const issue=issueMatch(issues,key);
     if(issue)out[key]=say('warning','Offene KI-Hilfeanfrage #'+issue.number+': '+issue.message+'. Details im Bereich Problem.');
    }
   }else{
    // A missing incident index is not affirmative proof of complete health.
    for(const key of ['overview','products']){
     if(out[key].state==='ok')out[key]=say('unknown',out[key].reason+' · Offene Probleme nicht unabhängig abgeglichen.');
    }
   }
   for(const [key] of areas){
    if(!byId('bob-view-'+key))out[key]=say('warning','Der zugehörige App-Bereich fehlt in der geladenen Benutzeroberfläche.');
   }
   last=out;at=Date.now();render(out);
  }catch(_){
   at=Date.now();
   byId('bobAreaSummary').textContent='Bereichsprüfung momentan nicht erreichbar; frühere Haken sind nicht mehr bestätigt.';
   if(last){for(const item of Object.values(last))item.state='unknown';render(last);}
  }finally{busy=false;byId('bobAreaRefresh').disabled=false;}
 }
 makeNodes();
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
 else mount();
 byId('bobAreaRefresh').addEventListener('click',refresh);
 window.BobAreaChecks={refresh};
 refresh();
 setInterval(refresh,120000);
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});
})();
</script>'''
