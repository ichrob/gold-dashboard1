/* Unified DEGIRO product visibility: local CSV depot + saved screenshot watchlist + Bob audit.
 * Never a DEGIRO account connection, broker quote, or permission to trade.
 */
(function(root){
'use strict';
const SCANNER_KEY='bobDegiroProductsV2';
const MAX_ITEMS=10000;
function validIsin(isin){
 if(typeof isin!=='string'||!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;
 const digits=isin.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));
 let check=0;
 [...digits].reverse().forEach((c,i)=>{const n=Number(c)*(i%2?2:1);check+=Math.floor(n/10)+n%10;});
 return check%10===0;
}
function readWatchlist(storage){
 try{
  const raw=storage?.getItem(SCANNER_KEY);
  if(!raw||raw.length>3_000_000)return [];
  const data=JSON.parse(raw);
  if(data?.version!==2||!Array.isArray(data.products))return [];
  return data.products.slice(0,MAX_ITEMS).filter(p=>p&&validIsin(p.isin)).map(p=>({
   isin:p.isin,name:typeof p.name==='string'?p.name.slice(0,180):'',
   direction:['LONG','SHORT'].includes(p.direction)?p.direction:'',
   origin:'screenshot',listUploadedAt:typeof data.listUploadedAt==='string'?data.listUploadedAt:null
  }));
 }catch(_){return [];}
}
// Bounded local evidence archive. Historical listing is never current broker tradeability.
const HISTORY_KEY='bobDegiroIsinEvidenceHistoryV1';
function updateEvidenceHistory(storage,products,observedAt,now=Date.now()){
 const at=safeTime(observedAt);
 if(!at||Date.parse(at)>now||!storage?.getItem||!storage?.setItem)return {saved:false,reason:'missing trusted observation time or storage'};
 let previous=[];
 try{const raw=storage.getItem(HISTORY_KEY);if(raw&&raw.length<=3000000){const data=JSON.parse(raw);if(data?.version===1&&Array.isArray(data.items))previous=data.items;}}catch(_){}
 const byId=new Map();
 for(const old of previous.slice(0,MAX_ITEMS))if(validIsin(old?.isin)&&safeTime(old?.lastSeenAt))byId.set(old.isin,{isin:old.isin,lastSeenAt:old.lastSeenAt,source:'DEGIRO screenshot/list',brokerTradeable:false});
 for(const p of (Array.isArray(products)?products:[]).slice(0,MAX_ITEMS)){
  if(!validIsin(p?.isin))continue;
  const old=byId.get(p.isin);
  if(!old||Date.parse(old.lastSeenAt)<=Date.parse(at))byId.set(p.isin,{isin:p.isin,lastSeenAt:at,source:'DEGIRO screenshot/list',brokerTradeable:false});
 }
 const items=Array.from(byId.values()).sort((a,b)=>Date.parse(b.lastSeenAt)-Date.parse(a.lastSeenAt)).slice(0,MAX_ITEMS);
 try{storage.setItem(HISTORY_KEY,JSON.stringify({version:1,items}));return {saved:true,items};}
 catch(_){return {saved:false,reason:'storage write failed'};}
}
function safeTime(value){
 if(typeof value!=='string'||!/(?:Z|[+-]\d{2}:\d{2})$/i.test(value))return null;
 const t=Date.parse(value);
 return Number.isFinite(t)?new Date(t).toISOString():null;
}
function numericPrice(value){
 if(typeof value==='number'&&Number.isFinite(value)&&value>=0)return value;
 if(typeof value==='string'&&/^\d+(?:\.\d+)?$/.test(value)){
  const n=Number(value);return Number.isFinite(n)?n:null;
 }
 return null;
}
function quoteObservation(item,now){
 const q=item?.quote;
 if(!q||q.isin!==item.isin)return null;
 const bid=numericPrice(q.bid),ask=numericPrice(q.ask);
 const bidAt=safeTime(q.bidAt)||safeTime(q.quoteAt);
 const askAt=safeTime(q.askAt)||safeTime(q.quoteAt);
 if(bid===null||ask===null||bid>ask||!bidAt||!askAt)return null;
 // The older original component time governs freshness; never invent an ask clock.
 const at=new Date(Math.min(Date.parse(bidAt),Date.parse(askAt))).toISOString();
 const age=(now-Date.parse(at))/1000;
 return {bid,ask,currency:typeof q.currency==='string'?q.currency.slice(0,3):'',
   at,source:typeof q.source==='string'?q.source.slice(0,120):'Emittentenvergleich',
   fresh:age>=0&&age<=90,ageSeconds:age,researchOnly:true,degiroExecutable:false};
}
function auditQuote(info,now,reportStatus){
 if(!Array.isArray(info?.sourceObservations))return null;
 const quotes=info.sourceObservations.slice(0,30).flatMap(source=>{
  if(!source||source.degiroExecutable===true||source.researchOnly===false)return [];
  const quote={
   isin:info.isin,bid:source.bid,ask:source.ask,
   bidAt:source.bidAt,askAt:source.askAt,quoteAt:null,
   currency:source.currency,source:source.source||source.label
  };
  const observed=quoteObservation({isin:info.isin,quote},now);
  if(!observed)return [];
  return [{...observed,fresh:observed.fresh&&reportStatus==='ok',
   auditBased:true,degiroExecutable:false,researchOnly:true}];
 });
 return quotes.sort((a,b)=>Date.parse(b.at)-Date.parse(a.at))[0]||null;
}
function safeAudit(report){
 if(!report||!Array.isArray(report.items))return {items:[],status:'unavailable',checkedAt:null};
 const status=['ok','partial','stale'].includes(report.status)?report.status:'unavailable';
 const checkedAt=safeTime(report.lastCheckedAt)||safeTime(report.checkedAt)||safeTime(report.observedAt);
 return {items:report.items.slice(0,MAX_ITEMS),status,checkedAt};
}
function combine(depot,watchlist,audit,visibleQuotes=[],now=Date.now()){
 const indexed=new Map();
 const ensure=isin=>{
  if(!validIsin(isin))return null;
  if(!indexed.has(isin))indexed.set(isin,{
   isin,name:isin,quantity:null,currency:'',csvValue:'',csvPrice:'',inDepot:false,
   inWatchlist:false,inAudit:false,direction:'',productKind:'unverified',
   quote:null,sourceStatus:'',quoteSourceAt:null,auditStatus:'',tradeApproved:false,
   degiroConnected:false,executableQuote:false,rankingEligible:false
  });
  return indexed.get(isin);
 };
 if(depot&&Array.isArray(depot.records)){
  for(const d of depot.records.slice(0,MAX_ITEMS)){
   const x=ensure(d.isin);if(!x)continue;
   x.inDepot=true;x.name=String(d.name||d.product||d.isin).slice(0,180);
   x.quantity=(d.quantity!==null&&d.quantity!==undefined&&String(d.quantity).trim()!==''&&Number.isFinite(Number(d.quantity)))?Number(d.quantity):null;
   x.currency=String(d.currency||'').slice(0,3);
   x.csvPrice=String(d.price||'').slice(0,60);
   x.csvValue=String(d.value||'').slice(0,60);
   x.productKind=d.type==='factor'?'factor':x.productKind;
  }
 }
 if(Array.isArray(watchlist)){
  for(const w of watchlist.slice(0,MAX_ITEMS)){
   const x=ensure(w?.isin);if(!x)continue;
   x.inWatchlist=true;
   if((!x.inDepot||x.name===x.isin)&&w.name)x.name=String(w.name).slice(0,180);
   if(['LONG','SHORT'].includes(w.direction))x.direction=w.direction;
  }
 }
 const a=safeAudit(audit);
 for(const info of a.items){
  const x=ensure(info?.isin);if(!x)continue;
  x.inAudit=true;
  x.auditStatus=a.status;
  x.sourceStatus=typeof info.state==='string'?info.state.slice(0,80):'';
  x.quoteSourceAt=safeTime(info.quoteSourceAt);
  if(!x.direction&&['LONG','SHORT'].includes(info.direction))x.direction=info.direction;
  if(!x.inDepot&&!x.inWatchlist&&typeof info.name==='string')x.name=info.name.slice(0,180);
  const observation=auditQuote(info,now,a.status);
  if(observation&&(!x.quote||Date.parse(observation.at)>Date.parse(x.quote.at)))x.quote=observation;
 }
 if(Array.isArray(visibleQuotes)){
  for(const data of visibleQuotes){
   const x=indexed.get(data?.isin);if(!x)continue;
   const observation=quoteObservation(data,now);
   if(observation&&(!x.quote||Date.parse(observation.at)>=Date.parse(x.quote.at)))x.quote=observation;
  }
 }
 for(const x of indexed.values()){
  if(/\bfaktor\b|\bfactor\b|constant leverage|konstant.?hebel/i.test(x.name))x.productKind='factor';
  const contract=root.BobProductEvidence||(typeof module==='object'&&module.exports&&typeof require==='function'
   ?require('./product_evidence_contract.js'):null);
  if(contract?.fromCombined)x.evidence=contract.fromCombined(x,now);
 }
 return Array.from(indexed.values()).sort((a,b)=>
  Number(b.inWatchlist)-Number(a.inWatchlist)||
  Number(b.inDepot)-Number(a.inDepot)||a.isin.localeCompare(b.isin));
}
function summary(items,audit){
 return {unique:items.length,depot:items.filter(x=>x.inDepot).length,
  watch:items.filter(x=>x.inWatchlist||x.inAudit).length,
  auditStatus:safeAudit(audit).status,
  currentObserved:items.filter(x=>x.quote?.fresh).length,
  degiroConnected:false,accountSynced:false};
}
function el(doc,tag,cls,label){
 const n=doc.createElement(tag);
 if(cls)n.className=cls;
 if(label!==undefined)n.textContent=String(label);
 return n;
}
function showMoney(value,currency){
 return String(value)+ (currency?' '+currency:'');
}
function formatAt(value){
 return new Date(value).toLocaleString('de-CH',{timeZone:'Europe/Zurich'});
}
function zurichQuotePhase(now=Date.now()){
 const parts=new Intl.DateTimeFormat('en-US',{
  timeZone:'Europe/Zurich',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'
 }).formatToParts(new Date(now));
 const find=type=>parts.find(p=>p.type===type)?.value;
 const weekday=find('weekday');
 if(weekday==='Sat'||weekday==='Sun')return 'weekend';
 const minute=Number(find('hour'))*60+Number(find('minute'));
 if(minute>=450&&minute<480)return 'preparation';
 if(minute>=480&&minute<1320)return 'trading';
 return 'night';
}
function quotePhaseMessage(phase,reportStatus){
 if(phase==='preparation')return '07:30–08:00 Zürich: read-only Vorprüfung der Emittentenquellen geplant. Noch keine Handelsfreigabe; Quellen können geschlossen sein.';
 if(phase==='trading')return reportStatus==='stale'||reportStatus==='unavailable'
  ?'08:00–22:00 Zürich: Hintergrundprüfung vorgesehen, aber aktueller Produktprüfbericht fehlt. Quellen-/Dienststatus unter Probleme kontrollieren.'
  :'08:00–22:00 Zürich: automatische Produktprüfung läuft planmäßig, soweit der Emittent datierte Kurse bereitstellt.';
 if(phase==='weekend')return 'Wochenende: keine reguläre Produktprüfung; nächster geplanter Vorlauf werktags ab 07:30 Zürich.';
 return 'Außerhalb der Produktprüfzeit: nächster geplanter Vorlauf werktags ab 07:30, reguläre Prüfung ab 08:00 Zürich.';
}
function mount(){
 const doc=root.document,host=doc.getElementById('bob-view-products');
 if(!host||doc.getElementById('dgCombinedProducts'))return;
 const panel=el(doc,'details','card');panel.id='dgCombinedProducts';panel.style.padding='14px';
 panel.style.minWidth='0';panel.style.maxWidth='100%';panel.style.boxSizing='border-box';
 const style=el(doc,'style');style.textContent=[
 '#dgCombinedProducts{overflow-wrap:anywhere}',
 '#dgCombinedProducts .dg-unified-cards{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}',
 '#dgCombinedProducts .dg-unified-card{padding:12px;border:1px solid #cbd5e1;border-radius:12px;min-width:0}',
 '#dgCombinedProducts .dg-unified-card h4{font-size:15px;margin:0 0 8px;line-height:1.4;overflow-wrap:anywhere}',
 '#dgCombinedProducts .dg-unified-card p{font-size:13px;margin:6px 0;overflow-wrap:anywhere}',
 '#dgCombinedProducts .dg-isin{font-family:monospace;font-size:14px;user-select:text}',
 '#dgCombinedProducts .dg-unified-meta{font-size:13px;line-height:1.6}',
 '#dgCombinedProducts .dg-unified-subtle{font-size:12px;opacity:.82;line-height:1.5}',
 '#dgCombinedProducts .dg-unified-actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}',
 '#dgCombinedProducts .dg-depot-missing{border:1px solid #b9c8d8;border-radius:12px;padding:12px;margin:12px 0}',
 '#dgCombinedProducts .dg-depot-missing p{font-size:14px;line-height:1.55;margin:6px 0}',
 '#dgCombinedProducts .dg-depot-missing button{width:100%;font-weight:650;padding:10px;background:#1677ff;color:white;border:0;border-radius:10px}',
 '#dgCombinedProducts button,#dgCombinedProducts select,#dgCombinedProducts input{min-height:42px;max-width:100%}',
 '#dgCombinedProducts .dg-unified-filter{max-width:100%;width:100%;padding:8px;margin:5px 0 12px}',
 '@media(min-width:900px){#dgCombinedProducts .dg-unified-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}'
 ].join('\n');panel.append(style);
 const heading=el(doc,'summary','','Alle DEGIRO-Produkte · Depot & Beobachtung');
 heading.style.cssText='cursor:pointer;font-weight:700;min-height:44px;display:list-item;align-content:center';
 panel.append(heading);
 panel.append(el(doc,'p','dg-unified-subtle',
  'Gemeinsame ISIN-Übersicht aus deinem Depot-CSV, deinen gespeicherten DEGIRO-Listenbildern und Bobs privatem Prüfbericht. Kein vollständiger DEGIRO-Katalog und kein Kontozugriff.'));
 const status=el(doc,'p','dg-unified-meta','Gespeicherte Produkte werden zusammengeführt …');
 status.id='dgUnifiedSummary';status.setAttribute('role','status');panel.append(status);
 const depotMissing=el(doc,'section','dg-depot-missing');
 depotMissing.id='dgUnifiedDepotMissing';depotMissing.hidden=true;
 depotMissing.append(el(doc,'strong','','Depot-CSV noch nicht gespeichert'));
 depotMissing.append(el(doc,'p','',
  'Die Beobachtungsliste ist vorhanden, aber in diesem Browser fehlt eine gespeicherte Portfolio-CSV. Ein früherer einmaliger CSV-Lesetest wurde nicht automatisch in die neue dauerhafte Depotliste übernommen.'));
 depotMissing.append(el(doc,'p','',
  'Für deine gehaltenen Produkte die bereits heruntergeladene Portfolio.csv unter Mehr → DEGIRO einmal erneut einlesen. Die Goldproduktliste bleibt erhalten.'));
 const importBtn=el(doc,'button','','Depot-CSV jetzt einlesen');
 importBtn.id='dgUnifiedImportCsv';importBtn.type='button';importBtn.dataset.view='degiro';
 depotMissing.append(importBtn);panel.append(depotMissing);
 const sync=el(doc,'p','dg-unified-subtle',
  'Automatisch: Prüfbericht etwa alle 30 Sekunden abrufen, solange Bob geöffnet ist; Emittenten- und Vergleichskurse nutzen Bobs vorhandene Quellenaktualisierung. Nicht: Live-Abgleich mit DEGIRO-Konto oder ausführbare Brokerkurse.');
 sync.id='dgUnifiedSync';panel.append(sync);
 const controls=el(doc,'div','dg-unified-actions');
 const refresh=el(doc,'button','','Jetzt prüfen');refresh.type='button';refresh.id='dgUnifiedRefresh';controls.append(refresh);
 const openScreen=el(doc,'button','','Gold-Hebelproduktliste öffnen');openScreen.type='button';controls.append(openScreen);
 openScreen.addEventListener('click',()=>{const d=doc.getElementById('dgSavedProductsSummary');if(d){d.parentElement.open=true;d.scrollIntoView({block:'start',behavior:'smooth'});}});
 panel.append(controls);
 const filter=el(doc,'select','dg-unified-filter');filter.id='dgUnifiedFilter';
 for(const [value,label] of [['all','Alle Produkte'],['watch','Beobachtungsliste'],['depot','Im Depot'],['fresh','Aktuelle Vergleichsbeobachtung']]){
  const option=el(doc,'option','',label);option.value=value;filter.append(option);
 }
 panel.append(filter);
 const search=el(doc,'input','dg-unified-filter');search.id='dgUnifiedSearch';search.type='search';
 search.placeholder='ISIN oder Produktname suchen';search.setAttribute('aria-label','DEGIRO-Produkte durchsuchen');
 panel.append(search);
 const list=el(doc,'div','dg-unified-cards');list.id='dgUnifiedCards';panel.append(list);
 const more=el(doc,'button','','Weitere Produkte anzeigen');more.type='button';more.hidden=true;
 panel.append(more);
 panel.append(el(doc,'p','dg-unified-subtle',
  'Quellen- oder Prüfungstimestamp ersetzt niemals einen Broker-Ausführungsnachweis. CSV-Schlusskurse bleiben historische Werte. Faktorprodukte sind keine Kandidaten für Bobs Gold-Knock-out-Top-3.'));
 host.append(panel);
 let audit={status:'unavailable',items:[]},items=[],shown=0,busy=false,lastUpdate=0;
 function watchRows(){
  let saved=[];try{
   saved=readWatchlist(root.localStorage);
   // Only archive the original import timestamp, never the 30-second repaint time.
   const at=saved[0]?.listUploadedAt;
   if(at&&saved.every(p=>p.listUploadedAt===at))updateEvidenceHistory(root.localStorage,saved,at);
  }catch(_){}
  return saved;
 }
 function depotRows(){
  try{return root.BobDegiroPortfolio?.load?.(root.localStorage)||null;}catch(_){return null;}
 }
 function quoteRows(){
  try{return root.BobDegiro?.tradeTestProducts?.()||[];}catch(_){return [];}
 }
 function filtered(){
  const query=search.value.trim().toLowerCase(),mode=filter.value;
  return items.filter(x=>(mode==='all'||(mode==='watch'&&(x.inWatchlist||x.inAudit))||
   (mode==='depot'&&x.inDepot)||(mode==='fresh'&&x.quote?.fresh))&&
   (!query||x.isin.toLowerCase().includes(query)||x.name.toLowerCase().includes(query)));
 }
 function drawCard(x){
  const card=el(doc,'article','dg-unified-card');
  card.append(el(doc,'h4','',x.name));
  card.append(el(doc,'div','dg-isin',x.isin));
  const origins=[x.inDepot?'Depot-CSV':null,x.inWatchlist?'DEGIRO-Screenshotliste':null,x.inAudit?'Bob-Prüfbericht':null].filter(Boolean);
  card.append(el(doc,'p','dg-unified-meta','Quelle: '+origins.join(' · ')));
  if(x.inDepot){
   card.append(el(doc,'p','','Bestand laut CSV: '+x.quantity+' Stück'+
    (x.currency?' · '+x.currency:'')+' · Schlusskurs '+showMoney(x.csvPrice||'—',x.currency)));
  }else card.append(el(doc,'p','','Nicht als Depotposition im letzten CSV nachgewiesen.'));
  if(x.direction)card.append(el(doc,'p','','Beobachtete Richtung: '+x.direction));
  if(x.productKind==='factor')card.append(el(doc,'p','','Faktorprodukt · aus der Gold-Knock-out-Auswahl ausgeschlossen.'));
  if(x.quote){
   const q=x.quote;
   card.append(el(doc,'p','dg-unified-meta',
    (q.fresh?'Datierte Emittenten-/Vergleichsbeobachtung':'Veraltete Emittenten-/Vergleichsbeobachtung')+
    ': Geld '+showMoney(q.bid,q.currency)+', Brief '+showMoney(q.ask,q.currency)));
   card.append(el(doc,'p','dg-unified-subtle',q.source+' · Originalzeit '+formatAt(q.at)+
    ' · kein DEGIRO-Ausführungskurs'));
  }else if(x.quoteSourceAt){
   card.append(el(doc,'p','dg-unified-subtle',
    'Bob-Prüfbeobachtung vom '+formatAt(x.quoteSourceAt)+
    ' (Kursdaten hier nicht bestätigt; kein DEGIRO-Ausführungskurs).'));
  }else card.append(el(doc,'p','dg-unified-subtle','Keine aktuelle, datierte Vergleichsquote verfügbar.'));
  if(x.inAudit&&x.auditStatus!=='ok')card.append(el(doc,'p','dg-unified-subtle',
   'Bob-Prüfbericht '+(x.auditStatus==='stale'?'veraltet':x.auditStatus==='partial'?'nur teilweise geprüft':'momentan nicht erreichbar')+'.'));
  if(x.evidence){
   card.append(el(doc,'p','dg-unified-subtle',
    'Getrennte Identitätsquellen: '+x.evidence.identity.text+
    '. Ausführbarer Brokerkurs: '+x.evidence.broker.text+'.'));
  }
  card.append(el(doc,'p','dg-unified-subtle','Handelsfreigabe über DEGIRO: nicht bestätigt.'));
  return card;
 }
 function paint(reset=false,loadMore=false){
  items=combine(depotRows(),watchRows(),audit,quoteRows(),Date.now());
  const s=summary(items,audit);
  depotMissing.hidden=s.depot>0;
  status.textContent=s.unique+' verschiedene Produkte · '+s.depot+' im Depot-CSV · '+
   s.watch+' in Beobachtung/Prüfbericht'+
   ' · '+s.currentObserved+' zeitnahe Vergleichsbeobachtungen.';
  const lastRealCheck=safeAudit(audit).checkedAt;
  sync.textContent='Bob-Bericht im Browser abgerufen: '+
   (lastUpdate?formatAt(new Date(lastUpdate).toISOString()):'noch nicht bestätigt')+
   '. Letzte tatsächliche serverseitige Produktprüfung: '+
   (lastRealCheck?formatAt(lastRealCheck):'nicht nachgewiesen')+
   '. Status: '+(s.auditStatus==='ok'?'aktuell geprüft':s.auditStatus==='stale'?'Prüfbericht veraltet':s.auditStatus==='partial'?'teilweise geprüft':'nicht erreichbar')+
   '. '+quotePhaseMessage(zurichQuotePhase(),s.auditStatus)+
   ' Keine DEGIRO-Konto-API und kein Live-Depotabgleich.';
  if(reset)shown=0;
  const visible=filtered();
  const count=Math.min(loadMore?shown+30:Math.max(shown,30),visible.length);
  list.replaceChildren();
  for(const x of visible.slice(0,count))list.append(drawCard(x));
  shown=count;
  more.hidden=count>=visible.length;
  more.textContent='Weitere Produkte anzeigen ('+(visible.length-count)+')';
  if(!visible.length)list.append(el(doc,'p','dg-unified-subtle',
   'Keine passenden Produkte. Prüfe unter Produkte die gespeicherte Gold-Liste oder lade unter Mehr → DEGIRO eine CSV hoch.'));
 }
 function requestAudit(){
  if(busy||doc.hidden)return Promise.resolve();
  busy=true;refresh.disabled=true;
  const ctl=new AbortController(),timeout=setTimeout(()=>ctl.abort(),9000);
  const request=root.BobProductAuditReadPool?.read?
   root.BobProductAuditReadPool.read().then(data=>({ok:true,json:async()=>data})):
   root.fetch('/api/degiro/audit',{cache:'no-store',credentials:'same-origin',signal:ctl.signal});
  return request
   .then(async response=>{
    if(!response.ok)throw Error('Bob-Prüfbericht HTTP '+response.status);
    const payload=safeAudit(await response.json());
    audit=payload;
    lastUpdate=Date.now();
   })
   .catch(()=>{audit={...audit,status:'unavailable'};})
   .finally(()=>{clearTimeout(timeout);busy=false;refresh.disabled=false;paint();});
 }
 refresh.addEventListener('click',()=>{paint();requestAudit();});
 filter.addEventListener('change',()=>paint(true));
 search.addEventListener('input',()=>paint(true));
 more.addEventListener('click',()=>paint(false,true));
 // Data is not transferred to DEGIRO. This uses Bob's existing private audit endpoint.
 root.BobDegiroAllProducts.rebuild=()=>paint();
 root.BobDegiroAllProducts.refresh=()=>{paint();return requestAudit();};
 paint();requestAudit();
 setInterval(()=>{if(!doc.hidden){paint();requestAudit();}},30000);
 doc.addEventListener('visibilitychange',()=>{if(!doc.hidden){paint();requestAudit();}});
 root.addEventListener('storage',event=>{
  if([SCANNER_KEY,root.BobDegiroPortfolio?.KEY].includes(event.key))paint();
 });
 setTimeout(()=>paint(),2000);
}
const api={validIsin,readWatchlist,updateEvidenceHistory,safeTime,numericPrice,quoteObservation,auditQuote,safeAudit,combine,summary,zurichQuotePhase,quotePhaseMessage,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
root.BobDegiroAllProducts=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);
else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
