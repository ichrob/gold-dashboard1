"""Private visualisation of server-side DEGIRO list evidence checks."""
PANEL = r'''<section id="bobProductAudit" class="card">
<h3>Automatische Prüfung der gespeicherten DEGIRO-Produkte</h3>
<p id="bobProductAuditStatus" role="status" class="small">Prüfbericht wird geladen …</p>
<p id="bobProductAuditUpdated" class="small">Letzte Prüfung: noch unbekannt</p>
<details><summary>Werte, Zeitstempel und automatische Nachprüfung pro ISIN</summary>
<div id="bobProductAuditItems" class="small"></div></details>
<p class="small">Bob überprüft ausschließlich die aktive Screenshotliste mit Emittenten- und vorhandenen Ersatzquellen. Fehlende Daten werden erneut abgefragt, aber niemals ersetzt oder als aktuell ausgegeben, solange der Originalnachweis fehlt. Kurse sind keine DEGIRO-Handelsbestätigung.</p>
</section>
<section id="bobProductAuditProblem" class="card">
<h3>Produktdaten · Offene Prüfprobleme</h3>
<p id="bobProductAuditProblemCount" role="status">Produktprüfung wird geladen …</p>
<div id="bobProductAuditProblemItems" class="small"></div>
<p class="small">Ab drei aufeinanderfolgenden unvollständigen Prüfungen erscheint ein KI-Hilfebedarf. Die private Produktliste und ISINs werden nicht in öffentlichen GitHub-Issues veröffentlicht. Die Prüfung ändert keine echten Orders, Produktfreigaben oder Stopps.</p>
</section>
<script>
(function(){
 const byId=id=>document.getElementById(id);
 const fmt=iso=>{const d=new Date(iso);return Number.isNaN(d.getTime())?'unbekannt':d.toLocaleString('de-CH',{timeZone:'Europe/Zurich',dateStyle:'short',timeStyle:'medium'});};
 function mount(){
  const product=byId('bob-view-products'),problems=byId('bob-view-problems');
  if(product)product.append(byId('bobProductAudit'));
  if(problems)problems.append(byId('bobProductAuditProblem'));
  else {const main=document.querySelector('main');if(main)main.append(byId('bobProductAuditProblem'));}
 }
 function render(r){
  const status=byId('bobProductAuditStatus'),updated=byId('bobProductAuditUpdated'),out=byId('bobProductAuditItems');
  const problem=byId('bobProductAuditProblemCount'),details=byId('bobProductAuditProblemItems');
  out.replaceChildren();details.replaceChildren();
  const good=r.status==='ok',items=Array.isArray(r.items)?r.items:[],incomplete=Number.isInteger(r.incomplete)?r.incomplete:null;
  if(r.status==='waiting-for-screenshot'){
   status.textContent='Keine aktuelle DEGIRO-Screenshotliste auf dem Hintergrundserver bestätigt.';
  }else if(r.status==='checking-new-list'){
   status.textContent='Neue Liste erkannt · erneute Quellenprüfung läuft. Vorherige Prüfwerte sind ungültig.';
  }else if(r.status==='stale'){
   status.textContent='⚠️ Der Prüfbericht ist veraltet. Keine aktuelle Produktbestätigung.';
  }else if(good){
   status.textContent=items.length+' Produkte geprüft · '+(incomplete===0?'alle Emittentennachweise vollständig (DEGIRO-Verfügbarkeit weiterhin unbestätigt)':incomplete+' mit fehlenden oder veralteten Werten')+' · Hintergrundüberwachung';
  }else{
   status.textContent='Prüfung derzeit nicht erreichbar; aktuelle Produktnachweise fehlen.';
  }
  status.className='small '+(good&&incomplete===0?'ok':'bad');
  updated.textContent='Letzte Hintergrundprüfung (Zürich): '+(r.lastCheckedAt?fmt(r.lastCheckedAt):'noch nicht bestätigt')+' · Listenstand: '+(r.listUploadedAt?fmt(r.listUploadedAt):'nicht bestätigt');
  const help=good?items.filter(i=>i.needsKiHelp):[];
  problem.textContent=!good?'Produktüberwachung nicht aktuell · Prüfstatus unbestätigt':(help.length+' Produkte benötigen noch KI-Hilfe · '+incomplete+' insgesamt unvollständig');
  for(const item of items){
   const node=document.createElement('details'),summary=document.createElement('summary');
   const healthy=item.state==='issuer-evidence-complete';
   summary.textContent=(healthy?'✓ ':'⚠ ') +(item.isin||'ISIN unbekannt')+' · '+(healthy?'Emittentennachweise vorhanden':'Fehlende Nachweise: '+(item.missing||[]).length);
   const list=document.createElement('p');list.style.whiteSpace='pre-line';
   list.textContent=(item.messages||[]).join('\n')+'\nPrüfungen in Folge: '+(item.consecutiveChecks||0)+' · Nächster Schritt: '+item.autoRecovery+
        '\nGeldkurszeit: '+(item.quoteSourceAt?fmt(item.quoteSourceAt):'nicht nachgewiesen')+
        ' · Hebelzeit: '+(item.leverageSourceAt?fmt(item.leverageSourceAt):'nicht nachgewiesen')+
        '\nKeine automatische DEGIRO-Handelsfreigabe.';
   node.append(summary,list);out.append(node);
  }
  for(const item of help){
   const p=document.createElement('p');
   p.textContent=(item.isin||'Unbekannte ISIN')+' · '+(item.messages||[]).join(' · ')+
       ' · Erste Feststellung: '+fmt(item.firstSeenAt);
   details.append(p);
  }
  if(good&&!help.length){
   const p=document.createElement('p');
   p.textContent=incomplete?'Nachprüfung läuft. Für noch nicht wiederherstellbare Nachweise bleibt die Produktfreigabe gesperrt.':'Keine offenen Produktdaten-Probleme.';
   details.append(p);
  }
 }
 let busy=false;
 async function refresh(){
  if(busy||window.BobSession?.expired?.())return;busy=true;
  const ctl=new AbortController(), timer=setTimeout(()=>ctl.abort(),10000);
  try{
   const response=await fetch('/api/degiro/audit',{cache:'no-store',credentials:'same-origin',signal:ctl.signal});
   if(!response.ok)throw Error('unavailable');
   render(await response.json());
  }catch(_){render({status:'unavailable',items:[]});}
  finally{clearTimeout(timer);busy=false;}
 }
 function init(){mount();refresh();setInterval(()=>{if(document.visibilityState!=='hidden')refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
</script>'''
