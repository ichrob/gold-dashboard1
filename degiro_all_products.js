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
 const at=safeTime(q.bidAt)||safeTime(q.askAt)||safeTime(q.quoteAt);
 if(bid===null||ask===null||bid>ask||!at)return null;
 const age=(now-Date.parse(at))/1000;
 return {bid,ask,currency:typeof q.currency==='string'?q.currency.slice(0,3):'',
   at,source:typeof q.source==='string'?q.source.slice(0,120):'Emittentenvergleich',
   fresh:age>=0&&age<=90,ageSeconds:age,researchOnly:true,degiroExecutable:false};
}
function safeAudit(report){
 if(!report||!Array.isArray(report.items))return {items:[],status:'unavailable',checkedAt:null};
 const status=['ok','partial','stale'].includes(report.status)?report.status:'unavailable';
 const checkedAt=safeTime(report.lastCheckedAt)||safeTime(report.observedAt);
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
 }
 if(Array.isArray(visibleQuotes)){
  for(const data of visibleQuotes){
   const x=indexed.get(data?.isin);if(!x)continue;
   const observation=quoteObservation(data,now);
   if(observation)x.quote=observation;
  }
 }
 for(const x of indexed.values()){
  if(/\bfaktor\b|\bfactor\b|constant leverage|konstant.?hebel/i.test(x.name))x.productKind='factor';
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
function mount(){
 const doc=root.document,host=doc.getElementById('bob-view-products');
 if(!host||doc.getElementById('dgCombinedProducts'))return;
 const panel=el(doc,'section','card');panel.id='dgCombinedProducts';panel.style.padding='14px';
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
 '#dgCombinedProducts button,#dgCombinedProducts select,#dgCombinedProducts input{min-height:42px;max-width:100%}',
 '#dgCombinedProducts .dg-unified-filter{max-width:100%;width:100%;padding:8px;margin:5px 0 12px}',
 '@media(min-width:900px){#dgCombinedProducts .dg-unified-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}'
 ].join('\n');panel.append(style);
 panel.append(el(doc,'h3','','Alle DEGIRO-Produkte · Depot & Beobachtung'));
 panel.append(el(doc,'p','dg-unified-subtle',
  'Gemeinsame ISIN-Übersicht aus deinem Depot-CSV, deinen gespeicherten DEGIRO-Listenbildern und Bobs privatem Prüfbericht. Kein vollständiger DEGIRO-Katalog und kein Kontozugriff.'));
 const status=el(doc,'p','dg-unified-meta','Gespeicherte Produkte werden zusammengeführt …');
 status.id='dgUnifiedSummary';status.setAttribute('role','status');panel.append(status);
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
 host.prepend(panel);
 let audit={status:'unavailable',items:[]},items=[],shown=0,busy=false,lastUpdate=0;
 function watchRows(){
  let saved=[];try{saved=readWatchlist(root.localStorage);}catch(_){}
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
  card.append(el(doc,'p','dg-unified-subtle','Handelsfreigabe über DEGIRO: nicht bestätigt.'));
  return card;
 }
 function paint(reset=true){
  items=combine(depotRows(),watchRows(),audit,quoteRows(),Date.now());
  const s=summary(items,audit);
  status.textContent=s.unique+' verschiedene Produkte · '+s.depot+' im Depot-CSV · '+
   s.watch+' in Beobachtung/Prüfbericht'+
   ' · '+s.currentObserved+' zeitnahe Vergleichsbeobachtungen.';
  sync.textContent='Automatischer Bob-Berichtsabruf alle 30 s bei offener App; letzter Abruf: '+
   (lastUpdate?formatAt(new Date(lastUpdate).toISOString()):'noch nicht bestätigt')+
   '. Berichtstatus: '+(s.auditStatus==='ok'?'ok':s.auditStatus==='stale'?'veraltet':s.auditStatus==='partial'?'teilweise':'nicht erreichbar')+
   '. Keine DEGIRO-Konto-API und kein Live-Depotabgleich.';
  if(reset)shown=0;
  const visible=filtered();
  const count=Math.min((reset?30:shown+30),visible.length);
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
  return root.fetch('/api/degiro/audit',{cache:'no-store',credentials:'same-origin',signal:ctl.signal})
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
 filter.addEventListener('change',()=>paint());
 search.addEventListener('input',()=>paint());
 more.addEventListener('click',()=>paint(false));
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
const api={validIsin,readWatchlist,safeTime,numericPrice,quoteObservation,safeAudit,combine,summary,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
root.BobDegiroAllProducts=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);
else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
