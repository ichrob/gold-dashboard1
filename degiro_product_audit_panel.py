"""Private visualisation of server-side DEGIRO list evidence checks."""
PANEL = r'''<section id="bobProductAudit" class="card">
<p class="small">Produktprobleme sind über den privaten Bob-Lesezugang für die automatische KI-Prüfung verfügbar. Kein manuelles Teilen erforderlich.</p>
<p id="bobAuditShareHint" class="small">Produktprüfung wird geladen.</p>
<div hidden aria-hidden="true">
<button id="bobAuditShareChatGPT" type="button" style="width:100%;white-space:normal" aria-describedby="bobAuditShareHint">DEGIRO Goldhebelprodukte Probleme</button>

<p id="bobAuditShareStatus" hidden role="status" class="small"></p>
<div id="bobAuditShareActions" hidden>
<button id="bobAuditCopyText" type="button">Bericht kopieren</button>
<button id="bobAuditNativeShare" type="button">Über andere App teilen</button>
</div>
<textarea id="bobAuditShareFallback" hidden readonly aria-label="Privaten Bericht zum manuellen Kopieren" style="width:100%;min-height:140px"></textarea>
</div>
<div hidden>
<p id="bobProductAuditStatus"></p>
<p id="bobProductAuditUpdated"></p>
<div id="bobProductAuditItems"></div>
</div>
</section>
<section id="bobProductAuditProblem" class="card">
<h3>Produktprobleme · KI-Hilfe</h3>
<p id="bobProductAuditProblemCount"></p>
<div id="bobProductAuditProblemItems"></div>
</section>
<script>
(function(){
 const byId=id=>document.getElementById(id);
 let latestReport=null;
 let preparedAuditText='';
 const safe=value=>String(value??'unbekannt').replace(/[\r\n\t\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').slice(0,180);
 // Privacy boundary: user initiated only. No account, order, quote amounts,
 // raw stored screenshots, credentials or automatic outbound transmission.
 function auditTextForChatGPT(r){
  const items=Array.isArray(r?.items)?r.items:[];
  const time=value=>typeof value==='string'&&Number.isFinite(Date.parse(value))?safe(value):'nicht nachgewiesen';
  const lines=[
   'Bob – privater Gold-Hebelprodukt-Prüfbericht (vom Nutzer bewusst geteilt)',
   'Auftrag an ChatGPT: Fehlende Werte pro ISIN untersuchen, vorhandene freigegebene Datenquellen und Bob-Code prüfen, Fehler beheben. Original-Zeitstempel nicht erfinden. Keine Orders oder Handelsfreigaben.',
   'Prüfstatus: '+safe(r?.status),
   'Letzte Hintergrundprüfung: '+time(r?.lastCheckedAt),
   'DEGIRO-Listenstand: '+time(r?.listUploadedAt),
   'Produkte im Prüfbericht: '+(Number.isInteger(r?.total)?r.total:'unbekannt'),
   'Geteilte Prüfpositionen: '+items.length,
   'Davon abweichende Kartenanzeige: '+items.filter(item=>item.cardDiscrepancy===true).length,
   'Unvollständige Produkte: '+(Number.isInteger(r?.incomplete)?r.incomplete:'unbekannt'),
   'Wichtig: Bei Status stale, unavailable oder checking-new-list keine Fehler als behoben werten.'
  ];
  for(const [index,item] of items.entries()){
   const isin=typeof item.isin==='string'&&/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(item.isin)?item.isin:'nicht bestätigt';
   const missing=Array.isArray(item.missing)?item.missing.slice(0,22).map(safe):[];
   const messages=Array.isArray(item.messages)?item.messages.slice(0,22).map(safe):[];
   const lev=item.leverageObservation||{};
   lines.push(
    '',
    (index+1)+'. '+isin+' · '+safe(item.direction)+' · '+safe(item.state),
    'Fehlende Nachweise: '+(missing.length?missing.join(', '):'keine aufgelistet'),
    'Einordnung: '+(item.cardDiscrepancy===true?'Abweichende Kartenanzeige: Server meldet vollständige Analysewerte, Produktkarte meldet offene Punkte. Ursache noch prüfen; keine Handelsfreigabe.':'Offene Prüfung laut Bericht'),
    'Fehlerbeschreibung: '+(messages.length?messages.join(' | '):'keine'),
    'Hinweise aus der aktuellen Produktkarte: '+(Array.isArray(item.cardMessages)&&item.cardMessages.length?item.cardMessages.map(safe).join(' | '):'keine zusätzlichen Kartenhinweise'),
    'Automatische Quellenreparatur: '+(Array.isArray(item.sourceRecovery)&&item.sourceRecovery.length?item.sourceRecovery.map(event=>safe(event.stage)+' · '+safe(event.state)).join(' | '):'keine technische Quellenstörung gemeldet'),
    'Reparaturplan: '+(item.repairLearning?Object.values(item.repairLearning.incidents||{}).map(x=>safe(x.action)+' · '+safe(x.state)).join(' | ')||'keine offene Reparaturprüfung':'noch nicht erfasst'),
    'Quelle: '+safe(item.source),
    'Geld/Brief-Quelle: '+safe(item.dataQuoteSource),
    'Geld/Brief-Zeit: '+time(item.quoteSourceAt),
    'Emittentenhebel-Originalzeit: '+time(item.leverageSourceAt),
    'Hebel-Näherung/Zeitart: '+safe(lev.kind)+' · '+time(lev.at),
    'Historischer Referenzhebel (nicht aktuell, keine Handelsfreigabe): '+(Number.isFinite(item.leverageReference?.value)?item.leverageReference.value.toFixed(2)+'x · '+safe(item.leverageReference.kind)+' · '+time(item.leverageReference.at):'nicht verfügbar'),
    'Handelsplatz: '+safe(item.issuerVenue),
    'Konkreter nächster Schritt: '+(item.venueAction?safe(item.venueAction):item.cardDiscrepancy===true?'Datenstand und Prüflogik der Produktkarte mit dem Serverbericht abgleichen.':'Offene Nachweise anhand ihrer Originalquellen prüfen.'),
    'Nachprüfungsstand: '+(item.needsKiHelp===true?'KI-Hilfe offen':'keine bestätigte KI-Eskalation'),
    'Automatische Handelsfreigabe: '+(item.tradeApproved===true?'laut Bericht ja (unabhängig prüfen)':'nein')
   );
  }
  if(!items.length)lines.push('Keine Problemprodukte im Bericht enthalten. Bei fehlender Liste oder nicht aktueller Prüfung keine Entwarnung.');
  return lines.join('\n');
 }
 function displayedProductProblems(){
  const cards=document.querySelectorAll('#dgMissingProducts [data-product-isin]');
  return [...cards].flatMap(card=>{
   const labels=card.querySelector('[data-product-problems]')?.textContent?.trim();
   if(!labels)return [];
   const messages=[...card.querySelectorAll('[data-product-help], [data-direction-data-status], [data-product-next], [data-product-auto-check]')]
    .map(node=>node.textContent.trim()).filter(Boolean);
   return [{isin:card.dataset.productIsin,labels,messages}];
  });
 }
 function problemReport(report,local){
  const source=Array.isArray(report?.items)?report.items:[];
  const selected=new Map(source.filter(item=>item.state!=='terminated'&&
   (item.state==='incomplete'||item.needsKiHelp===true||(Array.isArray(item.missing)&&item.missing.length)))
   .map(item=>[item.isin,{...item}]));
  for(const card of local){
   const original=selected.get(card.isin)||source.find(item=>item.isin===card.isin)||{isin:card.isin,state:'local-product-problem'};
   const cardDiscrepancy=report?.status==='ok'&&['analysis-evidence-complete','issuer-evidence-complete'].includes(original.state)
    &&Array.isArray(original.missing)&&!original.missing.length&&original.needsKiHelp!==true;
   selected.set(card.isin,{...original,cardDiscrepancy,cardMessages:[card.labels,...card.messages]});
  }
  return {...(report||{status:'unavailable'}),items:[...selected.values()]};
 }
 function mobileAuditPayload(){
  const local=displayedProductProblems();
  if(!latestReport&&!local.length)return null;
  const report=problemReport(latestReport,local);
  if(!report.items.length)return null;
  return auditTextForChatGPT(report);
 }
 function handoffStatus(message){const node=byId('bobAuditShareStatus');if(node){node.textContent=message;node.hidden=false;}}
 async function copyMobileAudit(){
  const value=preparedAuditText;
  if(!value){handoffStatus('Noch keine Problemprodukte zum Teilen verfügbar. Bitte die Produktliste und den Prüfbericht laden lassen.');return;}
  try{
   if(!navigator.clipboard?.writeText)throw Error('Clipboard not available');
   await navigator.clipboard.writeText(value);
   handoffStatus('Bericht kopiert. Jetzt in ChatGPT einfügen. Es wurden keine Daten automatisch versendet.');
  }catch(_){
   // Visible, selectable fallback when clipboard access is blocked by Android.
   const target=byId('bobAuditShareFallback');if(!target)return;
   target.value=value;target.hidden=false;target.focus();target.select();
   handoffStatus('Automatisches Kopieren nicht verfügbar. Text unten markieren und kopieren, dann in ChatGPT einfügen.');
  }
 }
 async function shareMobileAudit(){
  const value=mobileAuditPayload();
  if(!value){handoffStatus('Noch keine Problemprodukte zum Teilen verfügbar. Bitte die Produktliste und den Prüfbericht laden lassen.');return;}
  // Keep the exact report visible and copyable even when Android drops shared text.
  preparedAuditText=value;
  const target=byId('bobAuditShareFallback');
  if(target){target.value=value;target.hidden=false;}
  const actions=byId('bobAuditShareActions');if(actions)actions.hidden=false;
  const share=byId('bobAuditNativeShare');if(share)share.hidden=typeof navigator.share!=='function';
  // User explicitly selected sharing: avoid copying private diagnostics
  // to the clipboard unless the fallback button is pressed.
  if(typeof navigator.share==='function')await sharePreparedAudit();
  else handoffStatus('Android-Teilen nicht verfügbar. Den Ersatzweg „Bericht kopieren“ wählen.');
 }
 async function sharePreparedAudit(){
  const value=preparedAuditText;
  if(!value)return;
  if(typeof navigator.share!=='function'){await copyMobileAudit();return;}
  try{
   await navigator.share({title:'Bob · Gold-Hebelprodukte Prüfbericht',text:value});
   handoffStatus('Teilen-Dialog geschlossen. Ob ChatGPT den Text übernommen hat, ist nicht bestätigt. Falls das Eingabefeld leer bleibt: Bericht kopieren, in ChatGPT einfügen und absenden.');
  }catch(error){
   handoffStatus(error?.name==='AbortError'?'Teilen abgebrochen. Der Bericht bleibt unten zum Kopieren bereit.':'Textübergabe fehlgeschlagen. Bitte Bericht kopieren und in ChatGPT einfügen.');
  }
 }
 const fmt=iso=>{const d=new Date(iso);return Number.isNaN(d.getTime())?'unbekannt':d.toLocaleString('de-CH',{timeZone:'Europe/Zurich',dateStyle:'short',timeStyle:'medium'});};
 function leverageTimeLabel(item){
  if(item.leverageSourceAt)return fmt(item.leverageSourceAt)+' (eigene Emittenten-Quellenzeit)';
  const observation=item.leverageObservation;
  if(observation?.kind==='shared-issuer-observation'&&observation.current)
   return fmt(observation.at)+' (✓ Serienregel erfüllt: gemeinsamer SG-Zeitbezug, keine separate Original-Hebelzeit)';
  if(observation?.kind==='calculated-gearing'&&observation.current)
   return fmt(observation.at)+' (✓ berechnet · gültiger Analysewert)';
  return 'nicht aktuell nachgewiesen';
 }
 // A previously complete *analysis* is not a new market/issuer proof.
 // This label never modifies stored evidence or trading gates.
 function productCardHeadline(reportStatus,item){
  const isin=typeof item?.isin==='string'?item.isin:'ISIN unbekannt';
  if(item?.state==='terminated')return isin+' · Produkt beendet';
  if(reportStatus!=='ok')return '⚠ '+isin+' · Historische Prüfdaten · aktuelle Quellenprüfung fehlt';
  if(['issuer-evidence-complete','analysis-evidence-complete'].includes(item?.state))
   return '✓ '+isin+' · Produktnachweise im aktuellen Prüfbericht vorhanden';
  return '⚠ '+isin+' · Fehlende Nachweise: '+(Array.isArray(item?.missing)?item.missing.length:'unbekannt');
 }
 function mount(){
  const products=byId('dgSavedProductsSummary')?.closest('details');
  const audit=byId('bobProductAudit');
  if(products&&audit)products.after(audit);
  else if(byId('bob-view-products')&&audit)byId('bob-view-products').append(audit);
  const problems=byId('bob-view-problems');
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
  // Visible warning even if detail status is hidden by mobile layout.
  const shareHint=byId('bobAuditShareHint');
  if(shareHint)shareHint.textContent=good?
   'Produktprüfung geladen. Ungelöste Befunde bleiben für die automatische KI-Prüfung verfügbar; keine Handelsfreigabe.':
   '⚠️ Produktprüfung nicht aktuell ('+String(r.status||'unavailable').slice(0,40)+'). Historische Haken und Werte sind keine neuen Originalnachweise. Die automatische KI-Prüfung muss diesen veralteten Stand berücksichtigen.';
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
  updated.textContent='Letzte Hintergrundprüfung (Zürich): '+(r.lastCheckedAt?fmt(r.lastCheckedAt):'noch nicht bestätigt')+
   ' · Listenstand: '+(r.listUploadedAt?fmt(r.listUploadedAt):'nicht bestätigt')+
   (typeof r.marketContext==='string'?' · '+r.marketContext:'');
  const help=good?items.filter(i=>i.needsKiHelp):[];
  window.BobProductAuditHelpCount=good?help.length:null;
  window.BobProblems?.badge?.(window.BobProblemsArchiveCount??null);
  problem.textContent=!good?'Produktüberwachung nicht aktuell · Prüfstatus unbestätigt':(help.length+' Produkte benötigen noch KI-Hilfe · '+incomplete+' insgesamt unvollständig · '+(r.terminated||0)+' beendet (kein Datenfehler)');
  for(const item of items){
   const node=document.createElement('details'),summary=document.createElement('summary');
   node.dataset.isin=item.isin;node.dataset.productIsin=item.isin;node.open=opened.get(item.isin)===true;
   const ended=item.state==='terminated';
   summary.textContent=productCardHeadline(r.status,item);
   // A source-confirmed terminal instrument has no live quote/leverage problem
   // to repair. Show only the ISIN and issuer-ended state, no X or extra fields.
   // "Beendet" is intentional: terminal status alone is not KO proof.
   if(ended){
    summary.textContent=(item.isin||'ISIN unbekannt')+' · Produkt beendet';
    node.append(summary);out.append(node);continue;
   }
   const list=document.createElement('p');list.style.whiteSpace='pre-line';
   list.textContent=(item.messages||[]).join('\n')+'\nPrüfungen in Folge: '+(item.consecutiveChecks||0)+' · Nächster Schritt: '+item.autoRecovery+
        '\nGeldkurszeit: '+(item.quoteSourceAt?fmt(item.quoteSourceAt):'nicht nachgewiesen')+
        ' · Hebelzeit: '+leverageTimeLabel(item)+
        (Number.isFinite(item.leverageReference?.value)&&item.leverageReference.value>0?
         '\\nHistorischer Hebel als Recherche-Referenz: '+item.leverageReference.value.toFixed(2)+'x · '+fmt(item.leverageReference.at)+
         ' · '+(item.leverageReference.kind==='historical-issuer-leverage'?'früherer Originalhebel':'historisch berechneter Näherungswert')+
         ' · ausdrücklich nicht aktuell, keine Handelsfreigabe':'')+
        (item.brokerVenueEvidence?'\n✓ DEGIRO-Handelsplatz am Screenshot bestätigt: '+item.brokerVenueEvidence.venue+' · '+item.brokerVenueEvidence.observedMinute.replace('T',' ')+' · gültig bis '+fmt(item.brokerVenueEvidence.validUntil):'')+
        (item.brokerVenueStatus?.state==='historical'?'\nFrüherer DEGIRO-Handelsplatz: '+item.brokerVenueStatus.historicalEvidence.venue+' · '+item.brokerVenueStatus.historicalEvidence.observedMinute.replace('T',' ')+'. Aktueller Nachweis weiterhin offen.':'')+
        (item.venueAction?'\nHandelsplatzprüfung: '+item.issuerVenue+' · '+item.venueAction:'')+
        (item.identityEvidence==='source-matched'?'\n✓ ISIN und Richtung automatisch mit der Produktquelle abgeglichen.':'')+
        (item.dataQuoteSource?'\nKursnachweis: '+item.dataQuoteSource+(item.dataQuoteKind==='market-observation'?' · beobachtetes Geld/Brief, keine DEGIRO-Ausführungszusage':''):'')+
        (item.lastRecoveredAt?'\nAutomatisch wiederhergestellte Nachweise: '+(item.recoveredFields||[]).join(', ')+' · '+fmt(item.lastRecoveredAt):'')+
        '\nKeine automatische DEGIRO-Handelsfreigabe.';
   const learning=item.repairLearning;
   if(learning){
    const notice=document.createElement('p');notice.className='small';
    const states={repairing:'Reparatur läuft',verifying:'Erfolg wird nachgeprüft',ready:'Keine offene Reparaturprüfung',excluded:'Keine automatische Umgehung'};
    notice.textContent='Selbstreparatur: '+(states[learning.status]||'Prüfung offen')+'. '+
     Object.values(learning.incidents||{}).map(x=>x.action+' ('+(x.state==='awaiting-evidence'?'Bestätigung fehlt':x.state==='verifying'?'Nachprüfung läuft':'erneute Prüfung')+')').join(' · ')+
     ' Bestätigte Quellenhilfen: '+Object.entries(learning.sourceSuccesses||{}).map(([source,count])=>source+': '+count).join(' · ');
    node.append(notice);
   }
   const recovery=Array.isArray(item.sourceRecovery)?item.sourceRecovery:[];
   if(recovery.length){
    const notice=document.createElement('p');notice.className='small';
    notice.textContent='Automatische Quellenreparatur: '+recovery.map(event=>
     event.stage+' · '+(event.state==='call-restored'?'Abruf funktioniert wieder; Produktnachweise werden separat geprüft':
      'Zusatzquelle gestört; andere Quellen laufen weiter · erneuter Versuch frühestens in '+event.retryAfterSeconds+' s')).join(' | ');
    node.append(notice);
   }
   const study=r.priceStudy?.[item.isin];
   if(study){
    const evaluation=document.createElement('p');
    evaluation.textContent='Kursvergleich ohne aktiven Trade · '+study.count+' Vergleiche (30 Tage) · letzte Messung: '+(study.lastAt?fmt(study.lastAt):'noch keine')+
      (Number.isFinite(study.rawMae)?' · mittlere Abweichung an '+study.validationCount+' späteren Prüfwerten: '+study.rawMae.toFixed(4)+' → '+study.correctedMae.toFixed(4)+' '+study.currency+
       ' · '+(study.status==='improved'?'Korrektur im Vergleich besser':'Korrektur verworfen'):' · sammelt passende Originalkurse')+
      ' · getrennte Modellabschnitte; reine Auswertung, keine Handelsfreigabe.';
    const correction=study.automaticCorrection;
    if(correction)evaluation.textContent+=' Automatische Modellkorrektur: '+(correction.usable?'aktiv ('+(correction.factor*100).toFixed(3)+' %)':correction.reason)+
      ' · Phase '+correction.phase+(Number.isFinite(correction.latestCorrected)?' · letzte Modellschätzung '+correction.latestRaw.toFixed(4)+' → '+correction.latestCorrected.toFixed(4)+' '+study.currency:'')+(correction.evidence?' · unabhängiger Fehler vorher/nachher '+correction.evidence.rawMaePct.toFixed(4)+' / '+correction.evidence.correctedMaePct.toFixed(4)+' %':'');
    list.append(document.createElement('br'),evaluation);
   }
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
   const report=window.BobProductAuditReadPool?.read?
    await window.BobProductAuditReadPool.read():
    await (async()=>{
     const response=await fetch('/api/degiro/audit',{cache:'no-store',credentials:'same-origin',signal:ctl.signal});
     if(!response.ok)throw Error('unavailable');
     return response.json();
    })();
   latestReport=report;
   window.BobProductAuditReport=report;
   window.BobDegiro?.refreshVenueAssessment?.();
   if(!byId('bobProductAuditItems')?.contains(document.activeElement))render(report);
  }catch(_){latestReport=null;window.BobProductAuditReport=null;render({status:'unavailable',items:[]});}
  finally{clearTimeout(timer);busy=false;}
 }
 function init(){mount();
  byId('bobAuditShareChatGPT')?.addEventListener('click',shareMobileAudit);
  byId('bobAuditCopyText')?.addEventListener('click',copyMobileAudit);
  byId('bobAuditNativeShare')?.addEventListener('click',sharePreparedAudit);
  refresh();setInterval(()=>{if(document.visibilityState!=='hidden')refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
</script>'''
