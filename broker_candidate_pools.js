/* Separate issuer research from DEGIRO listing evidence.
 * Never automatically mutates screenshot product lists, rankings or broker orders.
 */
(function(root){
'use strict';
const KEY='bobIssuerResearchCandidatesV1';
const MAX_LOCAL=160;
const MAX_CATALOG=100;
const MAX_BYTES=120000;
function isValidISIN(isin){
 if(typeof isin!=='string'||!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;
 const numbers=isin.replace(/[A-Z]/g,ch=>String(ch.charCodeAt(0)-55));
 let sum=0;
 [...numbers].reverse().forEach((ch,i)=>{
  const n=Number(ch)*(i%2?2:1);
  sum+=Math.floor(n/10)+n%10;
 });
 return sum%10===0;
}
function text(value,max=160){return typeof value==='string'?value.trim().slice(0,max):'';}
function validClock(value){
 if(typeof value!=='string'||!/(?:Z|[+-]\d\d:\d\d)$/i.test(value))return null;
 const n=Date.parse(value);
 return Number.isFinite(n)?n:null;
}
function localMinute(now){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich',
  year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',
  hourCycle:'h23'}).formatToParts(new Date(now));
 const part=t=>parts.find(p=>p.type===t)?.value;
 return part('year')+'-'+part('month')+'-'+part('day')+'T'+part('hour')+':'+part('minute');
}
function verifiedBrokerProof(isin,record,report,watchlist,now=Date.now()){
 if(!isValidISIN(isin)||!record||typeof record!=='object'||!report||
    report.status!=='ok'||!Array.isArray(report.items))return false;
 const reportTime=validClock(report.lastCheckedAt);
 if(reportTime===null||!Number.isFinite(now)||now-reportTime<0||now-reportTime>180000)return false;
 const item=report.items.find(p=>p?.isin===isin);
 const evidence=item?.brokerVenueEvidence;
 if(!evidence||evidence.isin!==isin||evidence.broker!=='DEGIRO'||
    evidence.listingConfirmed!==true||evidence.executionConfirmed!==false||
    evidence.timezone!=='Europe/Zurich'||evidence.timePrecision!=='minute'||
    !['owner-reviewed-screenshot','automatic-detail-screenshot'].includes(evidence.kind)||
    !['EUR','CHF'].includes(evidence.currency)||
    !text(evidence.venue,100)||!text(evidence.imageReference,200)||
    !text(evidence.listUploadedAt,70)||!text(report.listUploadedAt,70)||
    evidence.listUploadedAt!==report.listUploadedAt)return false;
 // Confirm the exact current screenshot-list generation, not just a similarly
 // named historic product, an issuer catalogue flag, or a CSV portfolio row.
 if(!Array.isArray(watchlist)||!watchlist.some(p=>
     p?.isin===isin && p.listUploadedAt===evidence.listUploadedAt))return false;
 if(evidence.kind==='owner-reviewed-screenshot' &&
    evidence.venue!=='Societe Generale OTC')return false;
 if(evidence.kind==='automatic-detail-screenshot' &&
    evidence.venue.trim().toLowerCase().match(/^(?:unknown|unbekannt|[-—])$/))return false;
 if(typeof evidence.observedMinute!=='string'||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(evidence.observedMinute))return false;
 const until=validClock(evidence.validUntil);
 if(until===null||!Number.isFinite(now)||now>=until)return false;
 const currentMinute=localMinute(now);
 // The evidence date is today in Zurich, and it cannot lie in the future.
 if(evidence.observedMinute.slice(0,10)!==currentMinute.slice(0,10)||
    evidence.observedMinute>currentMinute)return false;
 if(localMinute(until).slice(0,16)!==evidence.observedMinute.slice(0,10)+'T22:00')return false;
 return true;
}
function normalizeCatalog(data){
 const items=Array.isArray(data?.candidates)?data.candidates.slice(0,MAX_CATALOG):[];
 const map=new Map();
 for(const row of items){
  const isin=text(row?.isin,12).toUpperCase();
  if(!isValidISIN(isin)||map.has(isin))continue;
  // Historic issuer seeds are not new issues, nor a current DEGIRO catalogue.
  map.set(isin,{
   isin,name:text(row.name,160)||isin,
   direction:['LONG','SHORT'].includes(row.direction)?row.direction:'',
   origin:'historical-issuer-candidate',
   issuerVerified:row.issuerVerified===true && row.issuerStatus==='verified',
   checkedAt:validClock(data.lastScanAt)?data.lastScanAt:null,
   listingConfirmed:false,brokerStatus:'unverified',
   source:'Historische ISIN + Emittentenrecherche'
  });
 }
 return Array.from(map.values());
}
function normalizeManual(items){
 if(!Array.isArray(items))return [];
 const map=new Map();
 for(const row of items.slice(0,MAX_LOCAL)){
  const isin=text(row?.isin,12).toUpperCase();
  if(!isValidISIN(isin)||map.has(isin))continue;
  map.set(isin,{isin,origin:'manual-candidate',name:text(row.name,160)||isin,
   addedAt:validClock(row.addedAt)?row.addedAt:null,
   issuerVerified:false,listingConfirmed:false,brokerStatus:'unverified'});
 }
 return [...map.values()];
}
function readLocal(storage){
 try{
  const raw=storage?.getItem(KEY);
  if(!raw||raw.length>MAX_BYTES)return [];
  const data=JSON.parse(raw);
  return data?.version===1?normalizeManual(data.items):[];
 }catch(_){return [];}
}
function saveLocal(storage,items){
 if(!storage||typeof storage.setItem!=='function')throw Error('Lokaler Speicher nicht erreichbar');
 const normalized=normalizeManual(items);
 storage.setItem(KEY,JSON.stringify({version:1,items:normalized}));
 const check=readLocal(storage);
 if(check.length!==normalized.length)throw Error('Broker-Rechercheliste konnte nicht überprüft werden');
 return check;
}
function queueManual(storage,isin,at=new Date().toISOString()){
 isin=text(isin,12).toUpperCase();
 if(!isValidISIN(isin))throw Error('Bitte eine gültige 12-stellige ISIN eingeben');
 const items=readLocal(storage);
 if(items.some(x=>x.isin===isin))return items;
 if(items.length>=MAX_LOCAL)throw Error('Rechercheliste ist voll; zuerst alte Einträge entfernen');
 return saveLocal(storage,[...items,{isin,name:isin,addedAt:at,origin:'manual-candidate'}]);
}
function removeLocal(storage,isin){
 return saveLocal(storage,readLocal(storage).filter(p=>p.isin!==isin));
}
function researchUniverse(local,catalog,known=[],audit=null,now=Date.now()){
 const list=new Map();
 for(const p of normalizeCatalog(catalog))list.set(p.isin,p);
 for(const p of normalizeManual(local))list.set(p.isin,{
  ...list.get(p.isin),...p,
  issuerVerified:list.get(p.isin)?.issuerVerified===true
 });
 const confirmed=[],unverified=[];
 const active=Array.isArray(known)?known:[];
 for(const entry of list.values()){
  // A backend attestation from a current DEGIRO screenshot is the sole path
  // to the DEGIRO-confirmed group. Source claims like degiroListed:true,
  // manual toggles, issuer quotes and previous reports are never proof.
  const listed=verifiedBrokerProof(entry.isin,entry,audit,active,now);
  const row={...entry,degiroListed:listed,degiroTradeApproved:false,
    brokerApiConnected:false,ibkrStatus:'not-checked',igStatus:'not-checked',
    executableQuoteVerified:false,addToDegiroRankings:false};
  if(listed)confirmed.push(row);
  else unverified.push(row);
 }
 return {confirmed,unverified,total:list.size,automaticDegiroAdditions:0};
}
function el(doc,tag,cls,value){
 const element=doc.createElement(tag);
 if(cls)element.className=cls;
 if(value!==undefined)element.textContent=String(value);
 return element;
}
function mount(){
 const doc=root.document;
 const future=doc.getElementById('bob-view-future');
 const products=doc.getElementById('bob-view-products');
 if(!future||!products||doc.getElementById('bobIssuerResearch'))return;
 const research=el(doc,'section','card');
 research.id='bobIssuerResearch';research.style.padding='14px';
 research.style.minWidth='0';research.style.overflowWrap='anywhere';
 const style=el(doc,'style');style.textContent=[
  '#bobIssuerResearch .broker-research-row,#bobNewDegiroConfirmed .broker-research-row{border:1px solid #d2dae5;border-radius:12px;padding:12px;margin:10px 0;overflow-wrap:anywhere}',
  '#bobIssuerResearch .broker-research-small,#bobNewDegiroConfirmed .broker-research-small{font-size:13px;line-height:1.5;opacity:.85}',
  '#bobIssuerResearch button,#bobIssuerResearch input{min-height:44px;max-width:100%;margin:5px 0}',
  '#bobIssuerResearch input{width:100%;padding:10px}',
  '#bobIssuerResearch .broker-research-isin{font-family:monospace;font-size:14px;user-select:text}',
  '#bobIssuerResearch .broker-research-rows{min-width:0}'
 ].join('\n');
 research.append(style);
 research.append(el(doc,'h3','','Emittenten-Recherche · zukünftige Broker'));
 research.append(el(doc,'p','broker-research-small',
  'Eigene Warteliste für neue und historische Emittentenprodukte. Solange ihre DEGIRO-Listung nicht aktuell durch einen passenden DEGIRO-Screenshot nachgewiesen ist, kommen sie NICHT in die bestätigte DEGIRO-Liste oder Top 3. IBKR und IG bleiben ebenfalls ungeprüft.'));
 const intro=el(doc,'p','broker-research-small','Emittentenübersicht: wird geprüft');
 intro.id='bobBrokerResearchStatus';intro.setAttribute('role','status');
 research.append(intro);
 const form=el(doc,'form');form.id='bobBrokerResearchForm';
 const label=el(doc,'label','','Neue ISIN für brokerübergreifende Recherche erfassen');label.htmlFor='bobBrokerResearchInput';form.append(label);
 const input=el(doc,'input');input.id='bobBrokerResearchInput';input.maxLength=12;
 input.placeholder='z. B. DE000…';input.setAttribute('aria-label','Emittenten-ISIN');form.append(input);
 const add=el(doc,'button','','In Rechercheliste vormerken');add.type='submit';form.append(add);
 research.append(form);
 const feedback=el(doc,'p','broker-research-small','');feedback.id='bobBrokerResearchFeedback';
 feedback.setAttribute('role','status');research.append(feedback);
 const refresh=el(doc,'button','','Emittenten-Recherche aktualisieren');refresh.type='button';refresh.id='bobBrokerResearchRefresh';research.append(refresh);
 const result=el(doc,'div','broker-research-rows');result.id='bobBrokerResearchRows';
 research.append(result);
 research.append(el(doc,'p','broker-research-small',
  'Die bestehende automatische Emittentenübersicht prüft bislang historische ISINs. Sie ist KEIN vollständiger Neuemissionen-Feed. Neue, unabhängig gefundene Emittentenprodukte können hier getrennt geprüft werden; automatische DEGIRO-Listung wird niemals angenommen.'));
 future.append(research);
 const confirmed=el(doc,'section','card');
 confirmed.id='bobNewDegiroConfirmed';confirmed.style.padding='14px';
 confirmed.style.minWidth='0';confirmed.style.overflowWrap='anywhere';
 confirmed.append(el(doc,'h3','','Neue Produkte · DEGIRO-Nachweis erforderlich'));
 const verifiedStatus=el(doc,'p','broker-research-small',
  'Keine neuen Produkte mit aktuell bestätigter DEGIRO-Listung.');
 verifiedStatus.id='bobDegiroCandidateStatus';verifiedStatus.setAttribute('role','status');confirmed.append(verifiedStatus);
 const confirmedRows=el(doc,'div');confirmedRows.id='bobDegiroConfirmedRows';confirmed.append(confirmedRows);
 confirmed.append(el(doc,'p','broker-research-small',
  'Nur ein aktueller ISIN-gebundener Nachweis aus einem geprüften DEGIRO-Produktdetail mit Handelsplatz und Datum zählt. Ein Emittentenkurs, historische Liste oder CSV-Kontoauszug allein reicht nicht. Ein bestätigter Listungsnachweis ist noch keine Orderfreigabe.'));
 products.prepend(confirmed);
 let catalog={candidates:[]},audit=null,busy=false,lastPoll=0;
 function watchlist(){
  try{return root.BobDegiroAllProducts?.readWatchlist?.(root.localStorage)||[];}
  catch(_){return [];}
 }
 function drawRows(target,rows,isVerified){
  target.replaceChildren();
  const visible=rows.slice(0,60);
  for(const item of visible){
   const card=el(doc,'article','broker-research-row');
   card.append(el(doc,'strong','',item.name||item.isin));
   card.append(el(doc,'div','broker-research-isin',item.isin));
   card.append(el(doc,'p','broker-research-small',
    isVerified?'DEGIRO-Listung aktuell mit Produktdetail-Screenshot nachgewiesen; kein ausführbarer DEGIRO-Kurs.':
    'DEGIRO: nicht aktuell nachgewiesen · IBKR: nicht geprüft · IG: nicht geprüft.'));
   card.append(el(doc,'p','broker-research-small',
    'Herkunft: '+(item.origin==='manual-candidate'?'manuell vorgemerkt':
      'historischer Emittentenkandidat')+
    (item.issuerVerified?' · Emittent bestätigt':' · Emittentenidentität offen')));
   if(item.origin==='manual-candidate'&&!isVerified){
    const del=el(doc,'button','','Aus Rechercheliste entfernen');
    del.type='button';del.addEventListener('click',()=>{
     try{removeLocal(root.localStorage,item.isin);feedback.textContent='ISIN aus Rechercheliste entfernt.';render();}
     catch(err){feedback.textContent=err.message;}
    });
    card.append(del);
   }
   target.append(card);
  }
  if(rows.length>60)target.append(el(doc,'p','broker-research-small',
   'Es werden 60 von '+rows.length+' Rechercheinträgen angezeigt.'));
 }
 function render(){
  const resultSet=researchUniverse(readLocal(root.localStorage),catalog,watchlist(),audit);
  intro.textContent=resultSet.unverified.length+' Emittentenprodukte ohne bestätigte DEGIRO-Listung · '+
    resultSet.confirmed.length+' aktuell gelistete Kandidaten · '+
    'automatisch in aktive DEGIRO-Auswahl übernommen: 0.';
  verifiedStatus.textContent=resultSet.confirmed.length?
    resultSet.confirmed.length+' Produkt(e) mit aktuellem DEGIRO-Screenshotnachweis; keine Handelsfreigabe.':
    'Keine neuen Produkte mit aktuell bestätigter DEGIRO-Listung.';
  drawRows(result,resultSet.unverified,false);
  drawRows(confirmedRows,resultSet.confirmed,true);
 }
 async function poll(){
  if(busy||doc.hidden)return;
  busy=true;refresh.disabled=true;
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),10000);
  try{
   const [catalogResponse,auditResponse]=await Promise.all([
    root.fetch('/api/degiro/candidates',{credentials:'same-origin',cache:'no-store',signal:abort.signal}),
    root.fetch('/api/degiro/audit',{credentials:'same-origin',cache:'no-store',signal:abort.signal})
   ]);
   if(!catalogResponse.ok||!auditResponse.ok)throw Error('Bobs private Recherche momentan nicht erreichbar');
   const nextCatalog=await catalogResponse.json();
   const nextAudit=await auditResponse.json();
   if(!Array.isArray(nextCatalog?.candidates)||!Array.isArray(nextAudit?.items))
    throw Error('Ungültiger Recherchebericht');
   catalog=nextCatalog;audit=nextAudit;lastPoll=Date.now();
   feedback.textContent='Rechercheliste aktualisiert · keine automatische DEGIRO-Aufnahme.';
  }catch(err){
   feedback.textContent='Quellenaktualisierung derzeit nicht bestätigt. Gespeicherte Recherche bleibt erhalten.';
   // Old audit data cannot serve as a fresh proof.
   audit=null;
  }finally{
   clearTimeout(timeout);busy=false;refresh.disabled=false;render();
  }
 }
 form.addEventListener('submit',event=>{
  event.preventDefault();
  try{
   queueManual(root.localStorage,input.value);
   input.value='';
   feedback.textContent='ISIN separat vorgemerkt. Weder DEGIRO-Listung noch Broker-Handelbarkeit bestätigt.';
   render();
  }catch(err){feedback.textContent=err.message;}
 });
 refresh.addEventListener('click',poll);
 root.addEventListener('storage',event=>{if([KEY,'bobDegiroProductsV2'].includes(event.key))render();});
 doc.addEventListener('visibilitychange',()=>{if(!doc.hidden){render();if(Date.now()-lastPoll>300000)poll();}});
 render();poll();
 setInterval(()=>{if(!doc.hidden&&Date.now()-lastPoll>=600000)poll();else if(!doc.hidden)render();},60000);
}
const api={KEY,isValidISIN,validClock,localMinute,verifiedBrokerProof,
 normalizeCatalog,normalizeManual,readLocal,saveLocal,queueManual,removeLocal,researchUniverse,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
root.BobBrokerResearch=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);
else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
