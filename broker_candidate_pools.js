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
    !['Societe Generale OTC','BNP OTC','BNP Paribas OTC'].includes(evidence.venue))return false;
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
function standaloneImageProof(isin,proofs,now=Date.now()){
 if(!isValidISIN(isin)||!proofs||proofs.status!=='ok'||!Array.isArray(proofs.items))return null;
 const receipt=validClock(proofs.checkedAt);
 if(receipt===null||now<receipt-5000||now-receipt>180000)return null;
 const p=proofs.items.find(x=>x?.isin===isin);
 if(!p||p.kind!=='user-uploaded-detail-ocr'||
    p.origin!=='user-uploaded-degiro-detail-image'||
    p.broker!=='DEGIRO'||p.isin!==isin||
    p.listingConfirmed!==true||p.executionConfirmed!==false||
    p.isExecutableQuote!==false||p.tradeApproved!==false||
    p.rankingsEligible!==false||p.brokerDisplayObserved!==true||
    p.timezone!=='Europe/Zurich'||p.timePrecision!=='minute'||
    !['EUR','CHF'].includes(p.currency)||
    !text(p.venue,100)||!text(p.imageSha256,64).match(/^[a-f0-9]{64}$/)||
    !Number.isInteger(p.imageBytes)||p.imageBytes<1024||p.imageBytes>12000000||
    !['image/png','image/jpeg','image/webp'].includes(p.imageMime))return null;
 const t=validClock(p.observedAt),until=validClock(p.validUntil);
 if(t===null||until===null||now<t||now>=until)return null;
 const local=localMinute(now);
 if(typeof p.observedMinute!=='string'||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(p.observedMinute)||
    p.observedMinute.slice(0,10)!==local.slice(0,10)||
    p.observedMinute>local||
    localMinute(until).slice(0,16)!==local.slice(0,10)+'T22:00')return null;
 return p;
}
function screenshotPayload(source,file,sha256){
 if(!source||!isValidISIN(source.isin)||
    source.source!=='DEGIRO-Produktdetail'||
    source.brokerDisplayConfirmed!==true||
    source.isExecutableQuote!==false||
    source.orderSubmitted!==false||
    source.orderWindowVerified!==false||
    source.executionGuaranteed!==false||
    !text(source.venue,100)||/^(?:unbekannt|unknown|[-—])$/i.test(source.venue.trim())||
    !['EUR','CHF'].includes(source.currency)||
    typeof source.sourceTime!=='string'||
    !/^\d{2}[./]\d{2}[./]\d{4} \d{2}:\d{2}(?::\d{2})?$/.test(source.sourceTime)||
    !file||!Number.isInteger(file.size)||file.size<1024||file.size>12000000||
    !['image/png','image/jpeg','image/webp'].includes(file.type)||
    typeof sha256!=='string'||!/^[a-f0-9]{64}$/.test(sha256)){
  throw Error('DEGIRO-Bildnachweis unvollständig: ISIN, Börse, Währung und Originalzeit prüfen');
 }
 const bid=source.bid??null,ask=source.ask??null;
 if((bid===null)!==(ask===null)||
    (bid!==null&&(!(bid>0)||!(ask>=bid))))throw Error('Geld-/Briefwerte widersprechen sich');
 return {isin:source.isin,venue:source.venue,currency:source.currency,
  sourceTime:source.sourceTime,source:source.source,
  brokerDisplayConfirmed:true,isExecutableQuote:false,orderWindowVerified:false,
  orderSubmitted:false,executionGuaranteed:false,imageSha256:sha256,
  imageBytes:file.size,imageMime:file.type,bid,ask};
}
function imageISIN(textValue,context){
 const tokens=(String(textValue||'').toUpperCase().match(/\b[A-Z]{2}[A-Z0-9]{10}\b/g)||[]);
 const ids=[...new Set(tokens.map(token=>{
  const normalized=context?.normalizeOcrIsin?.(token,textValue);
  return normalized?.isin||token;
 }).filter(isValidISIN))];
 if(ids.length!==1)throw Error('DEGIRO-Bild: keine eindeutige ISIN gefunden; bitte Produktdetail erneut aufnehmen');
 return ids[0];
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
   issuerComparison:(row.issuerComparison?.sourceRole==='issuer-comparison-only'
                     && row.issuerComparison?.isin===isin)?row.issuerComparison:null,
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
function researchUniverse(local,catalog,known=[],audit=null,now=Date.now(),proofs=null){
 const list=new Map();
 for(const p of normalizeCatalog(catalog))list.set(p.isin,p);
 for(const p of normalizeManual(local))list.set(p.isin,{
  ...list.get(p.isin),...p,
  issuerVerified:list.get(p.isin)?.issuerVerified===true
 });
 // Independently confirmed single-image proofs are kept on the private
 // server and can restore their candidate identity on another signed-in device.
 if(proofs?.status==='ok'&&Array.isArray(proofs.items)){
  for(const p of proofs.items.slice(0,120)){
   if(!isValidISIN(p?.isin)||list.has(p.isin))continue;
   list.set(p.isin,{isin:p.isin,name:p.isin,
    origin:'user-uploaded-screenshot',issuerVerified:false,
    listingConfirmed:false,brokerStatus:'unverified'});
  }
 }
 const confirmed=[],unverified=[];
 const active=Array.isArray(known)?known:[];
 for(const entry of list.values()){
  // A backend attestation from a current DEGIRO screenshot is the sole path
  // to the DEGIRO-confirmed group. Source claims like degiroListed:true,
  // manual toggles, issuer quotes and previous reports are never proof.
  const currentManualImage=standaloneImageProof(entry.isin,proofs,now);
  const listed=!!currentManualImage||verifiedBrokerProof(entry.isin,entry,audit,active,now);
  const row={...entry,degiroListed:listed,
    listingProofSource:currentManualImage?'user-image':listed?'list-audit':null,
    listingProofAt:currentManualImage?.observedAt||null,
    degiroTradeApproved:false,
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
  '#bobIssuerResearch input{width:100%;padding:10px;box-sizing:border-box}',
  '#bobIssuerResearch .broker-research-isin{font-family:monospace;font-size:14px;user-select:text}',
  '#bobIssuerResearch .broker-research-rows{min-width:0}',
  '#bobIssuerResearch .broker-image-action{width:100%;padding:10px;border-radius:10px;font-weight:600}',
  '#bobIssuerResearch .broker-image-hint{padding:10px;border:1px solid #cbd5e1;border-radius:10px}',
  '#bobIssuerResearch .broker-image-input[hidden]{display:none}'
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
 const imageHint=el(doc,'p','broker-research-small broker-image-hint',
  'Ein DEGIRO-Produktdetailbild genügt, wenn ISIN, Börse, Währung und datierte Kursdaten im selben Bild lesbar sind. Bob liest es auf diesem Gerät aus; nur geprüfte Belegfelder und ein Bild-Fingerabdruck gehen an Bobs privaten Server. Originalbild, Kontodaten und OCR-Volltext bleiben auf diesem Gerät.');
 research.append(imageHint);
 const globalUpload=el(doc,'button','broker-image-action','↑ Neues DEGIRO-Produktbild hochladen');
 globalUpload.type='button';globalUpload.id='bobBrokerCandidateUpload';research.append(globalUpload);
 const imageInput=el(doc,'input','broker-image-input');
 imageInput.id='bobBrokerCandidateFile';imageInput.type='file';
 imageInput.accept='image/png,image/jpeg,image/webp';imageInput.hidden=true;
 imageInput.setAttribute('aria-label','DEGIRO-Produktdetailbild auswählen');
 research.append(imageInput);
 const imageStatus=el(doc,'p','broker-research-small','');
 imageStatus.id='bobBrokerCandidateImageStatus';imageStatus.setAttribute('role','status');
 imageStatus.setAttribute('aria-live','polite');research.append(imageStatus);
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
 products.append(confirmed);
 let catalog={candidates:[]},audit=null,proofs=null,busy=false,lastPoll=0;
 let imageBusy=false,imageExpected=null;
 const issuerReadouts=new Map();
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
    isVerified?'DEGIRO-Produktanzeige aus aktuellem Bild nachgewiesen · kein ausführbarer Brokerkurs oder Handelssignal.':
    'DEGIRO: nicht aktuell nachgewiesen · IBKR: nicht geprüft · IG: nicht geprüft.'));
   const issuer=issuerReadouts.get(item.isin);
   if(issuer)card.append(el(doc,'p','broker-research-small',issuer));
   const comparison=item.issuerComparison;
   if(comparison){
    const at=validClock(comparison.bidAt),askAt=validClock(comparison.askAt);
    const fresh=at!==null&&askAt!==null&&Date.now()>=Math.max(at,askAt)
      &&Date.now()-Math.min(at,askAt)<=90000;
    const label=fresh?'Zeitnaher Emittenten-Vergleich':'Historischer Emittenten-Vergleich';
    card.append(el(doc,'p','broker-research-small',label+': '+
      comparison.bid+' / '+comparison.ask+' '+comparison.currency+
      ' · Original Geld/Brief '+new Date(at).toLocaleString('de-CH')+' / '+
      new Date(askAt).toLocaleString('de-CH')+
      ' · KEIN ausführbarer DEGIRO-Kurs.'));
   }
   const chooseImage=el(doc,'button','broker-image-action',
     isVerified?'Bild nur bei Änderung erneut aufnehmen':'DEGIRO-Produktbild zuordnen');
   chooseImage.type='button';chooseImage.dataset.candidateIsin=item.isin;
   chooseImage.addEventListener('click',()=>chooseImageFor(item.isin));
   card.append(chooseImage);
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
  const resultSet=researchUniverse(readLocal(root.localStorage),catalog,watchlist(),audit,Date.now(),proofs);
  intro.textContent=resultSet.unverified.length+' Emittentenprodukte ohne bestätigte DEGIRO-Listung · '+
    resultSet.confirmed.length+' aktuell gelistete Kandidaten · '+
    'automatisch in aktive DEGIRO-Auswahl übernommen: 0.';
  const researchRanks=catalog?.researchTop3;
  if(researchRanks?.status==='insufficient-original-evidence')
   intro.textContent+=' Forschungs-Top-3 noch nicht vollständig belegbar (KO-Abstand/Hebel/Finanzierungskosten).';
  else if(Array.isArray(researchRanks?.entries)&&researchRanks.entries.length)
   intro.textContent+=' '+researchRanks.entries.length+' getrennt gereihte Forschungs-Kandidaten, KEINE Handelsfreigabe.';
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
   const [catalogResponse,auditResponse,proofResponse]=await Promise.all([
    root.fetch('/api/degiro/candidates',{credentials:'same-origin',cache:'no-store',signal:abort.signal}),
    root.fetch('/api/degiro/audit',{credentials:'same-origin',cache:'no-store',signal:abort.signal}),
    root.fetch('/api/degiro/candidate-proofs',{credentials:'same-origin',cache:'no-store',signal:abort.signal})
   ]);
   if(!catalogResponse.ok||!auditResponse.ok)throw Error('Bobs private Recherche momentan nicht erreichbar');
   const nextCatalog=await catalogResponse.json();
   const nextAudit=await auditResponse.json();
   const nextProofs=proofResponse.ok?await proofResponse.json():null;
   if(!Array.isArray(nextCatalog?.candidates)||!Array.isArray(nextAudit?.items))
    throw Error('Ungültiger Recherchebericht');
   catalog=nextCatalog;audit=nextAudit;
   proofs=nextProofs?.status==='ok'&&Array.isArray(nextProofs.items)?nextProofs:null;
   lastPoll=Date.now();
   feedback.textContent=proofs?'Rechercheliste aktualisiert · keine automatische Handelsfreigabe.':
    'Emittenten-Recherche aktualisiert, aber privater Bildnachweisspeicher nicht erreichbar: keine neue DEGIRO-Bestätigung.';
  }catch(err){
   feedback.textContent='Quellenaktualisierung derzeit nicht bestätigt. Gespeicherte Recherche bleibt erhalten.';
   // Old audit data cannot serve as a fresh proof.
   audit=null;proofs=null;
  }finally{
   clearTimeout(timeout);busy=false;refresh.disabled=false;render();
  }
 }
 function chooseImageFor(isin=null){
  if(imageBusy){imageStatus.textContent='Bildprüfung läuft bereits. Bitte kurz warten.';return;}
  imageExpected=isin;
  imageInput.value='';
  imageInput.click();
 }
 async function refreshIssuerAfterUpload(isin){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),12000);
  try{
   const response=await root.fetch('/api/degiro/enrich?isin='+encodeURIComponent(isin),{
    credentials:'same-origin',cache:'no-store',signal:ctl.signal});
   if(!response.ok)throw Error('Status '+response.status);
   const data=await response.json();
   if(data?.isin!==isin)throw Error('ISIN widerspricht der Emittentenantwort');
   const meta=data.metadata||{};
   const verified=data.productVerified===true;
   const underlying=meta.underlyingType==='SPOT'&&
    ['XAU/USD','Gold','Gold Spot'].includes(meta.underlying);
   const factor=meta.type==='FACTOR';
   issuerReadouts.set(isin,verified
    ?'Emittentenrecherche: Identität bestätigt · '+(factor?'Faktorprodukt · keine Gold-Knock-out-Auswahl':
      underlying?'Gold-Spot-Basiswert erkannt':'Basiswert noch nicht als Gold-Spot bestätigt')+
      ' · Handelsfreigabe separat.'
    :'Emittentenrecherche: Daten noch nicht eindeutig bestätigt; DEGIRO-Bildnachweis bleibt separat.');
  }catch(_){
   issuerReadouts.set(isin,'Emittentenrecherche derzeit nicht verfügbar. Der Bildnachweis wurde separat gespeichert.');
  }finally{clearTimeout(timer);render();}
 }
 async function processImageFile(file,expected){
  if(imageBusy)return;
  imageBusy=true;globalUpload.disabled=true;
  const original=imageInput.value;
  try{
   if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type)||
      file.size<1024||file.size>12000000)
    throw Error('Bitte PNG, JPEG oder WebP (maximal 12 MB) auswählen.');
   const scanner=root.BobDegiro;
   if(typeof scanner?.recognizeOcr!=='function'||
      typeof scanner?.parseDegiroDisplayedQuote!=='function')
    throw Error('Bob-Bilderkennung ist noch nicht bereit. Bitte die Seite neu öffnen.');
   imageStatus.textContent='DEGIRO-Bild wird lokal gelesen. ISIN und Handelsplatz werden geprüft …';
   const ocr=await scanner.recognizeOcr(file,'bobBrokerCandidateImageStatus',true,expected||'');
   const raw=ocr?.data?.text;
   if(!raw||typeof raw!=='string')throw Error('Das Bild enthält keine zuverlässig lesbaren Produktdetails.');
   const isin=imageISIN(raw,scanner);
   if(expected&&isin!==expected)throw Error('Die Bild-ISIN stimmt nicht mit dem gewählten Produkt überein. Keine Aufnahme.');
   const parsed=scanner.parseDegiroDisplayedQuote(raw,isin,false)||
                scanner.parseDegiroDisplayedQuote(raw,isin,true);
   if(!parsed)throw Error('Im selben DEGIRO-Bild müssen ISIN, Börse, Währung und datierte Kursdaten erkennbar sein.');
   // The only image material retained is a local byte fingerprint.
   // Neither screenshot bytes nor OCR body are POSTed to the server.
   const bytes=await file.arrayBuffer();
   const digest=[...new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes))]
    .map(n=>n.toString(16).padStart(2,'0')).join('');
   const payload=screenshotPayload(parsed,{size:file.size,type:file.type},digest);
   imageStatus.textContent='Produkt '+isin+' erkannt. Nur Belegdaten werden sicher gespeichert …';
   const response=await root.fetch('/api/degiro/candidate-proof',{
    method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)
   });
   let receipt={};try{receipt=await response.json();}catch(_){}
   if(!response.ok||receipt?.ok!==true||receipt.evidence?.isin!==isin)
    throw Error(text(receipt?.error,160)||'Privater Nachweisspeicher derzeit nicht erreichbar.');
   try{queueManual(root.localStorage,isin);}catch(_){
    // A verified server observation remains visible independently of this
    // device's local candidate queue; never pretend local storage succeeded.
   }
   await poll();
   imageStatus.textContent='✓ DEGIRO-Produktdetail für '+isin+
    ' aus dem Bild erkannt und zeitlich geprüft. Listungsbeobachtung gespeichert bis heute 22:00 Uhr Zürich. Keine Handelsfreigabe.';
   refreshIssuerAfterUpload(isin).catch(()=>{});
  }catch(err){
   imageStatus.textContent='⚠️ '+text(err?.message,250)+
    ' Der Kandidat bleibt in der brokerübergreifenden Recherche; keine DEGIRO-Freigabe.';
  }finally{
   imageInput.value='';imageExpected=null;imageBusy=false;globalUpload.disabled=false;
  }
 }
 globalUpload.addEventListener('click',()=>chooseImageFor());
 imageInput.addEventListener('change',()=>{
  const file=imageInput.files?.[0],expected=imageExpected;
  if(file)processImageFile(file,expected);
 });
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
const api={KEY,isValidISIN,validClock,localMinute,verifiedBrokerProof,standaloneImageProof,screenshotPayload,imageISIN,
 normalizeCatalog,normalizeManual,readLocal,saveLocal,queueManual,removeLocal,researchUniverse,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
root.BobBrokerResearch=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);
else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
