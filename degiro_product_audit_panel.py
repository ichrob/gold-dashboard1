"""Private visualisation of server-side DEGIRO list evidence checks."""
PANEL = r'''<section id="bobProductAudit" class="card">
<h3>Automatische Prüfung der gespeicherten DEGIRO-Produkte</h3>
<p id="bobProductAuditStatus" role="status" class="small">Prüfbericht wird geladen …</p>
<p id="bobProductAuditUpdated" class="small">Letzte Prüfung: noch unbekannt</p>
<details><summary>Werte, Zeitstempel und automatische Nachprüfung pro ISIN</summary>
<div id="bobProductAuditItems" class="small"></div></details>
<p class="small">Bob überprüft ausschließlich die aktive Screenshotliste mit Emittenten- und vorhandenen Ersatzquellen. Fehlende Daten werden erneut abgefragt, aber niemals ersetzt oder als aktuell ausgegeben, solange der Originalnachweis fehlt. Die Quellenvergleichsanzeige nutzt nur bereits vorhandene datierte Beobachtungen. Onvista darf ohne schriftliche Freigabe nicht automatisiert abgefragt werden. Kurse sind keine DEGIRO-Handelsbestätigung.</p>
</section>
<section id="bobProductAuditProblem" class="card">
<h3>Produktdaten · Offene Prüfprobleme</h3>
<p id="bobProductAuditProblemCount" role="status">Produktprüfung wird geladen …</p>
<p id="bobSeriesEvidenceRuleDone" class="small">✓ Erledigt: Die Serienregel für den eindeutig gemeinsamen Zeitbezug derselben ISIN/Quelle und zugehöriger Screenshots oder SG-Werte ist in Bob umgesetzt. Das bestätigt eine zusammengehörende Beobachtung, nicht automatisch eine separate Original-Hebelzeit oder einen bei DEGIRO ausführbaren Kurs.</p>
<div id="bobProductAuditProblemItems" class="small"></div>
<p class="small">Ab drei aufeinanderfolgenden unvollständigen Prüfungen erscheint ein KI-Hilfebedarf. Die private Produktliste und ISINs werden nicht in öffentlichen GitHub-Issues veröffentlicht. Die Prüfung ändert keine echten Orders, Produktfreigaben oder Stopps.</p>
</section>
<script>
(function(){
 const byId=id=>document.getElementById(id);
 const fmt=iso=>{const d=new Date(iso);return Number.isNaN(d.getTime())?'unbekannt':d.toLocaleString('de-CH',{timeZone:'Europe/Zurich',dateStyle:'short',timeStyle:'medium'});};
 function leverageTimeLabel(item){
  if(item.leverageSourceAt)return fmt(item.leverageSourceAt)+' (eigene Emittenten-Quellenzeit)';
  const observation=item.leverageObservation;
  if(observation?.kind==='shared-issuer-observation'&&observation.current)
   return fmt(observation.at)+' (✓ Serienregel erfüllt: gemeinsamer SG-Zeitbezug, keine separate Original-Hebelzeit)';
  if(observation?.kind==='calculated-gearing')
   return 'nur errechneter Hebel · eigene Emittenten-Hebelzeit nicht nachgewiesen';
  return 'nicht aktuell nachgewiesen';
 }
 function mount(){
  const product=byId('bob-view-products'),problems=byId('bob-view-problems');
  if(product)product.append(byId('bobProductAudit'));
  if(problems)problems.append(byId('bobProductAuditProblem'));
  else {const main=document.querySelector('main');if(main)main.append(byId('bobProductAuditProblem'));}
 }
 function render(r){
  const update=()=>renderReport(r);
  return window.BobDegiro?.preserveReadingPosition?window.BobDegiro.preserveReadingPosition(update):update();
 }
 function renderReport(r){
  const status=byId('bobProductAuditStatus'),updated=byId('bobProductAuditUpdated'),out=byId('bobProductAuditItems');
  const problem=byId('bobProductAuditProblemCount'),details=byId('bobProductAuditProblemItems');
  const opened=new Map([...out.children].map(el=>[el.dataset.isin,el.open]));
  out.replaceChildren();details.replaceChildren();
  const good=r.status==='ok',items=Array.isArray(r.items)?r.items:[],incomplete=Number.isInteger(r.incomplete)?r.incomplete:null;
  if(r.status==='waiting-for-screenshot'){
   status.textContent='Keine aktuelle DEGIRO-Screenshotliste auf dem Hintergrundserver bestätigt.';
  }else if(r.status==='checking-new-list'){
   status.textContent='Neue Liste erkannt · erneute Quellenprüfung läuft. Vorherige Prüfwerte sind ungültig.';
  }else if(r.status==='stale'){
   status.textContent='⚠️ Der Prüfbericht ist veraltet. Keine aktuelle Produktbestätigung.';
  }else if(good){
   status.textContent=items.length+' Produkte geprüft · '+incomplete+' mit fehlenden oder veralteten Werten · '+(r.terminated||0)+' beendet · Hintergrundüberwachung';
  }else{
   status.textContent='Prüfung derzeit nicht erreichbar; aktuelle Produktnachweise fehlen.';
  }
  status.className='small '+(good&&incomplete===0?'ok':'bad');
  updated.textContent='Letzte Hintergrundprüfung (Zürich): '+(r.lastCheckedAt?fmt(r.lastCheckedAt):'noch nicht bestätigt')+' · Listenstand: '+(r.listUploadedAt?fmt(r.listUploadedAt):'nicht bestätigt');
  const help=good?items.filter(i=>i.needsKiHelp):[];
  window.BobProductAuditHelpCount=help.length;
  window.BobProblems?.badge?.(window.BobProblemsArchiveCount??null);
  problem.textContent=!good?'Produktüberwachung nicht aktuell · Prüfstatus unbestätigt':(help.length+' Produkte benötigen noch KI-Hilfe · '+incomplete+' insgesamt unvollständig · '+(r.terminated||0)+' beendet (kein Datenfehler)');
  for(const item of items){
   const node=document.createElement('details'),summary=document.createElement('summary');
   node.dataset.isin=item.isin;node.dataset.productIsin=item.isin;node.open=opened.get(item.isin)===true;
   const healthy=item.state==='issuer-evidence-complete';
   const ended=item.state==='terminated';
   summary.textContent=(ended?'⛔ ':healthy?'✓ ':'⚠ ') +(item.isin||'ISIN unbekannt')+' · '+(ended?'Beendet laut Emittent · gesperrt':healthy?'Produktnachweise vorhanden':'Fehlende Nachweise: '+(item.missing||[]).length);
   const list=document.createElement('p');list.style.whiteSpace='pre-line';
   list.textContent=(item.messages||[]).join('\n')+'\nPrüfungen in Folge: '+(item.consecutiveChecks||0)+' · Nächster Schritt: '+item.autoRecovery+
        '\nGeldkurszeit: '+(item.quoteSourceAt?fmt(item.quoteSourceAt):'nicht nachgewiesen')+
        ' · Hebelzeit: '+leverageTimeLabel(item)+
        (item.brokerVenueEvidence?'\n✓ DEGIRO-Handelsplatz am Screenshot bestätigt: '+item.brokerVenueEvidence.venue+' · '+item.brokerVenueEvidence.observedMinute.replace('T',' ')+' · gültig bis '+fmt(item.brokerVenueEvidence.validUntil):'')+
        (item.venueAction?'\nHandelsplatzprüfung: '+item.issuerVenue+' · '+item.venueAction:'')+
        (item.identityEvidence==='source-matched'?'\n✓ ISIN und Richtung automatisch mit der Produktquelle abgeglichen.':'')+
        (item.dataQuoteSource?'\nKursnachweis: '+item.dataQuoteSource+(item.dataQuoteKind==='market-observation'?' · beobachtetes Geld/Brief, keine DEGIRO-Ausführungszusage':''):'')+
        (item.lastRecoveredAt?'\nAutomatisch wiederhergestellte Nachweise: '+(item.recoveredFields||[]).join(', ')+' · '+fmt(item.lastRecoveredAt):'')+
        '\nKeine automatische DEGIRO-Handelsfreigabe.';
   node.append(summary,list);
   if(item.issuerVenue&&!item.brokerVenueEvidence){
    const form=document.createElement('form');
    const heading=document.createElement('b');heading.textContent='Falls Bob das Kursdatenbild nicht eindeutig erkennt: Handelsplatz bestätigen';form.append(heading);
    function input(label,type,name,value=''){
     const wrap=document.createElement('label');wrap.textContent=label+' ';
     const field=document.createElement('input');field.type=type;field.name=name;field.value=value;field.required=true;
     wrap.append(field);form.append(wrap,document.createElement('br'));return field;
    }
    const venue=input('Handelsplatz','text','venue','Societe Generale OTC');venue.readOnly=true;
    const currency=input('Produktwährung','text','currency','CHF');currency.readOnly=true;
    const observed=input('Datum und Uhrzeit im Bild (Schweiz)','datetime-local','observedMinute');
    const reference=input('Bildname oder Bildreferenz','text','imageReference');reference.maxLength=200;
    const reviewed=input('ISIN und Handelsplatz am Original geprüft','checkbox','reviewed');
    const button=document.createElement('button');button.type='submit';button.textContent='Handelsplatznachweis speichern';form.append(button);
    const message=document.createElement('p');message.setAttribute('role','status');form.append(message);
    form.addEventListener('submit',async event=>{
     event.preventDefault();button.disabled=true;
     try{
      const response=await fetch('/api/degiro/venue',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({isin:item.isin,venue:venue.value,currency:currency.value,observedMinute:observed.value,imageReference:reference.value,reviewed:reviewed.checked})});
      const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error||'Speichern fehlgeschlagen');
      message.textContent=result.message+' · gültig bis '+fmt(result.evidence.validUntil)+'. Die Hintergrundprüfung übernimmt den Nachweis im nächsten Zyklus.';
     }catch(error){message.textContent=error.message;}finally{button.disabled=false;}
    });
    node.append(form);
   }
   const obs=Array.isArray(item.sourceObservations)?item.sourceObservations:[];
   const comparison=document.createElement('div');comparison.className='small';
   const title=document.createElement('b');title.textContent='Quellenvergleich (keine Handelsfreigabe):';
   comparison.append(title);
   if(!obs.length){
     const empty=document.createElement('p');empty.textContent='Noch kein zweiter datierter Kursnachweis verfügbar. Bob erfindet keine Quellzeit.';comparison.append(empty);
   }
   for(const q of obs){
     const p=document.createElement('p');
     p.textContent=(q.current?'Zeitaktuell':'Veraltet')+' · '+q.label+' · '+q.source+
       ' · '+q.bid+' / '+q.ask+' '+q.currency+
       ' · Geld: '+fmt(q.bidAt)+' · Brief: '+fmt(q.askAt)+
       ' · '+q.note;
     comparison.append(p);
   }
   const links=Array.isArray(item.researchLinks)?item.researchLinks:[];
   for(const candidate of links){
     if(candidate.mode!=='manual-only'||!/^https:\/\/(?:www\.)?onvista\.de\//.test(candidate.url))continue;
     const p=document.createElement('p');
     const a=document.createElement('a');a.href=candidate.url;a.target='_blank';a.rel='noopener noreferrer';
     a.textContent=candidate.name+' (manuell öffnen)';
     p.append(a,document.createTextNode(' · '+candidate.note));comparison.append(p);
   }
   node.append(comparison);
   const check=item.marketCrossCheck;
   if(check&&typeof check==='object'){
     const p=document.createElement('p');p.className='small';
     const reasons=Array.isArray(check.reasons)?check.reasons:[];
     const number=x=>typeof x==='number'&&Number.isFinite(x)?x.toLocaleString('de-CH',{maximumFractionDigits:4}):'unbekannt';
     p.textContent='Automatischer Börsen-/SG-Kursvergleich: '+
       (check.checked?'Zeitlicher Abgleich mit separater ISIN und Handelsplatz möglich · Preisabweichung '+
         number(check.deviationPct)+' % · maximaler Zeitversatz '+number(check.timeSkewSeconds)+' s':'noch nicht vollständig belegbar')+
       '. '+reasons.join(' ')+' Kein Zugriff auf DEGIRO-Orderkurse; keine Ausführungszusage.';
     node.append(p);
   }
   if(item.isin==='DE000FG8NHQ3'&&item.issuerVenue==='Swiss DOTS (CHF)'){
     const link=document.createElement('a');
     link.href='https://www.swissquote.com/de-ch/private/trade/products/swiss-dots';
     link.target='_blank';link.rel='noopener noreferrer';
     link.textContent='Swissquote: Handelsplatz und Zugangsweg prüfen';
     node.append(link);
   }
   out.append(node);
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
  if(busy||window.BobSession?.expired?.()||byId('bobProductAuditItems')?.contains(document.activeElement))return;busy=true;
  const ctl=new AbortController(), timer=setTimeout(()=>ctl.abort(),10000);
  try{
   const response=await fetch('/api/degiro/audit',{cache:'no-store',credentials:'same-origin',signal:ctl.signal});
   if(!response.ok)throw Error('unavailable');
   const report=await response.json();
   if(!byId('bobProductAuditItems')?.contains(document.activeElement))render(report);
  }catch(_){render({status:'unavailable',items:[]});}
  finally{clearTimeout(timer);busy=false;}
 }
 function init(){mount();refresh();setInterval(()=>{if(document.visibilityState!=='hidden')refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
</script>'''
