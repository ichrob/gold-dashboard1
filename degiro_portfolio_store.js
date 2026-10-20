/* User-confirmed DEGIRO CSV depot snapshot in Bob. Local-only, no broker sessions, no orders. */
(function(root){
'use strict';
const KEY='bob.degiro.csv.depot.v1';
const VERSION=1;
const MAX_ITEMS=10000;
const label='DEGIRO-Depotprodukte (CSV)';
function validIsin(value){
 if(typeof value!=='string'||!/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(value))return false;
 const digits=value.replace(/[A-Z]/g,c=>String(c.charCodeAt(0)-55));
 let checksum=0;
 [...digits].reverse().forEach((c,i)=>{const n=Number(c)*(i%2?2:1);checksum+=Math.floor(n/10)+n%10;});
 return checksum%10===0;
}
function cleanText(value,max=160){return String(value||'').trim().slice(0,max);}
function classifyName(name){
 return /\bfaktor\b|\bfactor\b|constant leverage|konstant.?hebel/i.test(name)?'factor':'unverified';
}
function prepare(data,importedAt){
 if(!data||data.kind!=='portfolio')throw Error('Nur ein DEGIRO-Portfolioexport darf Depotbestände ersetzen. Transaktionsdateien bleiben eine separate Auswertung.');
 if(!Array.isArray(data.records)||!data.records.length||data.records.length>MAX_ITEMS)throw Error('Keine gültigen Depotprodukte oder zu viele Zeilen.');
 if(!Array.isArray(data.cashBalances)||data.cashBalances.length>100)throw Error('Ungültige Bargeldzeilen.');
 const seen=new Set();
 const products=data.records.map(row=>{
  const isin=cleanText(row.isin,12).toUpperCase();
  if(!validIsin(isin))throw Error('Ungültige ISIN im Depotimport.');
  if(seen.has(isin))throw Error('Doppelte ISIN im Depotexport – bitte die Datei überprüfen.');
  seen.add(isin);
  const quantity=Number(row.quantity);
  if(!Number.isFinite(quantity)||Math.abs(quantity)>1e10)throw Error('Ungültige Stückzahl im Depotimport.');
  const name=cleanText(row.product||row.name);
  return {isin,name,quantity,currency:cleanText(row.currency,3).toUpperCase(),
   price:cleanText(row.price,48),value:cleanText(row.value,48),
   accountValue:cleanText(row.accountValue,48),type:classifyName(name),
   tradeApproved:false};
 });
 const cashBalances=data.cashBalances.map(row=>{
  const currency=cleanText(row.currency,3).toUpperCase();
  const amount=Number(row.amount),accountValue=row.accountValue===null?null:Number(row.accountValue);
  if(!/^[A-Z]{3}$/.test(currency)||!Number.isFinite(amount)||(accountValue!==null&&!Number.isFinite(accountValue)))throw Error('Ungültige Bargeldzeile.');
  return {currency,amount,accountValue};
 });
 const timestamp=new Date(importedAt);
 if(!Number.isFinite(timestamp.getTime()))throw Error('Ungültige Importzeit.');
 return {version:VERSION,kind:'portfolio',source:'Manueller DEGIRO-CSV-Export',
  importedAt:timestamp.toISOString(),accountCurrency:cleanText(data.accountCurrency,3).toUpperCase(),
  records:products,cashBalances,invalidRows:[],
  realtime:false,brokerVerified:false,ordersEnabled:false,
  rankingEligible:false,liveAccountConnected:false};
}
function safeStorage(storage){if(!storage||typeof storage.getItem!=='function'||typeof storage.setItem!=='function')throw Error('Lokaler Datenspeicher nicht verfügbar.');return storage;}
function load(storage){
 const raw=safeStorage(storage).getItem(KEY);if(!raw)return null;
 try{
  if(raw.length>3_000_000)return null;
  const parsed=JSON.parse(raw);
  if(parsed?.version!==VERSION||parsed.kind!=='portfolio'||parsed.brokerVerified!==false||
     parsed.ordersEnabled!==false||parsed.rankingEligible!==false||
     parsed.liveAccountConnected!==false||!Array.isArray(parsed.records)||
     !Array.isArray(parsed.cashBalances))return null;
  const rebuilt=prepare(parsed,parsed.importedAt);
  if(rebuilt.records.length!==parsed.records.length)return null;
  return rebuilt;
 }catch(_){return null;}
}
function save(storage,data,importedAt=new Date().toISOString()){
 const store=safeStorage(storage),snapshot=prepare(data,importedAt);
 store.setItem(KEY,JSON.stringify(snapshot));
 const verified=load(store);
 if(!verified||verified.importedAt!==snapshot.importedAt||
    verified.records.length!==snapshot.records.length)throw Error('Speichern konnte nicht bestätigt werden.');
 return verified;
}
function clear(storage){
 const store=safeStorage(storage);
 store.removeItem(KEY);
 if(store.getItem(KEY)!==null)throw Error('Löschen konnte nicht bestätigt werden.');
}
function el(doc,tag,cls,text){
 const x=doc.createElement(tag);if(cls)x.className=cls;
 if(text!==undefined)x.textContent=String(text);
 return x;
}
function textValue(value){return String(value??'').trim()||'—';}
function mount(){
 const doc=root.document,productsView=doc.getElementById('bob-view-products');
 if(!productsView||doc.getElementById('dgStoredPortfolio'))return;
 const wrapper=el(doc,'section','card');
 wrapper.id='dgStoredPortfolio';
 wrapper.style.padding='14px';
 wrapper.style.maxWidth='100%';
 wrapper.style.minWidth='0';
 wrapper.style.boxSizing='border-box';
 const style=el(doc,'style');
 style.textContent=[
 '#dgStoredPortfolio{overflow-wrap:anywhere}',
 '#dgStoredPortfolio .dg-holding{padding:12px;margin:10px 0;border:1px solid #cbd5e1;border-radius:10px;min-width:0}',
 '#dgStoredPortfolio .dg-holding h4{font-size:15px;line-height:1.45;margin:0 0 7px}',
 '#dgStoredPortfolio .dg-holding-meta{font-size:14px;line-height:1.65;overflow-wrap:anywhere}',
 '#dgStoredPortfolio .dg-holding-isin{font-family:monospace;font-size:14px;user-select:text;overflow-wrap:anywhere}',
 '#dgStoredPortfolio .dg-note{font-size:13px;line-height:1.5;opacity:.85}',
 '#dgStoredPortfolio .dg-holding-status{font-size:13px;margin-top:5px}',
 '#dgStoredPortfolio button{min-height:40px;margin:6px 0;max-width:100%}'
 ].join('\n');
 wrapper.append(style,el(doc,'h3','',label));
 const summary=el(doc,'p','dg-note','Noch keine DEGIRO-Depotprodukte gespeichert.');
 summary.id='dgStoredPortfolioStatus';summary.setAttribute('role','status');wrapper.append(summary);
 const details=el(doc,'details');
 details.id='dgStoredPortfolioDetails';details.open=true;
 details.append(el(doc,'summary','','Gespeicherte Depotprodukte anzeigen'));
 const list=el(doc,'div');list.id='dgStoredPortfolioList';details.append(list);
 wrapper.append(details);
 const reminder=el(doc,'p','dg-note','Nur CSV-Momentaufnahme. Nicht automatisch aktualisiert. Gold-Knock-out-Top-3 und Handelsfreigaben bleiben unabhängig.');
 wrapper.append(reminder);
 productsView.prepend(wrapper);
 let current=null,shown=0;
 function render(){
  list.replaceChildren();shown=0;
  try{current=load(root.localStorage);}catch(_){current=null;}
  if(!current){
   summary.textContent='Noch keine DEGIRO-Depotprodukte übernommen. Unter Mehr → DEGIRO eine Portfolio-CSV einlesen.';
   details.hidden=true;return;
  }
  details.hidden=false;
  summary.textContent='✓ '+current.records.length+' Produkte und '+current.cashBalances.length+
   ' Bargeldpositionen gespeichert · Import: '+new Date(current.importedAt).toLocaleString('de-CH')+
   ' · Stand der Kurse: ausschließlich CSV, kein Livekurs.';
  showNext();
 }
 function showNext(){
  if(!current)return;
  list.querySelector('[data-show-more]')?.remove();
  const count=Math.min(shown+30,current.records.length);
  for(let i=shown;i<count;i++){
   const row=current.records[i],card=el(doc,'article','dg-holding');
   card.append(el(doc,'h4','',row.name||'Unbenanntes Wertpapier'));
   card.append(el(doc,'div','dg-holding-isin',row.isin));
   card.append(el(doc,'div','dg-holding-meta','Bestand: '+row.quantity+' Stück · '+textValue(row.currency)));
   card.append(el(doc,'div','dg-holding-meta','Schlusskurs: '+textValue(row.price)+
      ' · Exportwert: '+textValue(row.value)+' '+textValue(row.currency)));
   if(row.accountValue && current.accountCurrency){
    card.append(el(doc,'div','dg-holding-meta','Wert in '+current.accountCurrency+': '+row.accountValue));
   }
   card.append(el(doc,'div','dg-holding-status',
    row.type==='factor'?'Faktorprodukt · nicht für Gold-Knock-out-Top-3 zugelassen':
     'Produktart und Handelbarkeit nicht bestätigt · keine automatische Freigabe'));
   list.append(card);
  }
  shown=count;
  if(shown<current.records.length){
   const more=el(doc,'button','','Weitere Produkte anzeigen ('+(current.records.length-shown)+')');
   more.type='button';more.dataset.showMore='true';
   more.addEventListener('click',showNext);list.append(more);
  }
 }
 function refresh(){render();}
 render();
 root.BobDegiroPortfolio.refresh=refresh;
}
const api={KEY,VERSION,validIsin,classifyName,prepare,load,save,clear,mount};
if(typeof module==='object'&&module.exports)module.exports=api;
root.BobDegiroPortfolio=api;
if(!root.document)return;
if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',mount);else mount();
})(typeof globalThis!=='undefined'?globalThis:this);
