// ==UserScript==
// @name         Bob DEGIRO Export-Brücke
// @namespace    https://bob-private-scanner.onrender.com/
// @version      1.1.0
// @description  Übergibt ausgewählte DEGIRO-Portfolioexporte an Bob. Keine Anmeldung oder Orders.
// @match        https://trader.degiro.nl/*
// @match        https://bob-private-scanner.onrender.com/*
// @grant        unsafeWindow
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @grant        GM_addValueChangeListener
// @run-at       document-start
// @inject-into  page
// @noframes
// @license      MIT
// ==/UserScript==

(function(){
"use strict";
function parseRows(text){
 if(typeof text!=='string'||text.length>2_000_000)throw Error('Datei ist leer oder über 2 MB groß.');
 text=text.replace(/^\uFEFF/,'');
 const first=(text.split(/\r?\n/).slice(0,12).find(line=>/ISIN/i.test(line))||text.split(/\r?\n/,1)[0]||'');
 const delimiter=[';',',','\t'].map(d=>({d,n:(first.match(new RegExp(d==='\t'?'\\t':d===';'?';':',','g'))||[]).length})).sort((a,b)=>b.n-a.n)[0];
 if(!delimiter||!delimiter.n)throw Error('Kein CSV-Trennzeichen gefunden.');
 const rows=[],row=[];let cell='',quoted=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(quoted){
   if(ch==='"'&&text[i+1]==='"'){cell+='"';i++;}
   else if(ch==='"')quoted=false;
   else cell+=ch;
  }else if(ch==='"'){if(cell.trim())throw Error('Ungültige CSV-Anführungszeichen.');quoted=true;}
  else if(ch===delimiter.d){row.push(cell.trim());cell='';}
  else if(ch==='\n'||ch==='\r'){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(cell.trim());cell='';if(row.some(Boolean))rows.push(row.slice());row.length=0;}
  else cell+=ch;
  if(rows.length>10001)throw Error('Maximal 10.000 Zeilen pro Datei.');
 }
 if(quoted)throw Error('Nicht geschlossene Anführungszeichen.');
 row.push(cell.trim());if(row.some(Boolean))rows.push(row);
 if(rows.length<2)throw Error('Keine Datensätze gefunden.');
 return rows;
}
function normalize(s){return String(s||'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/g,'');}
function getIndex(headers,aliases){const wanted=new Set(aliases.map(normalize));return headers.findIndex(x=>wanted.has(normalize(x)));}
function readReport(text,options={}){
 const rows=parseRows(text);let start=-1,indexes;
 for(let i=0;i<Math.min(rows.length,12);i++){
  const h=rows[i];const isin=getIndex(h,['ISIN','ISIN-Code','ISIN Code','Symbol/ISIN','Symbol / ISIN','Symbol / ISIN-Code']);
  const qty=getIndex(h,['Anzahl','Stückzahl','Stuckzahl','Quantity','Stücke','Stucke','Anzahl Stück','Number','Aantal']);
  if(isin>=0&&qty>=0){start=i;indexes={isin,qty};break;}
 }
 if(start<0)throw Error('Kein unterstützter DEGIRO-Bericht: Spalten ISIN und Anzahl/Quantity fehlen.');
 const h=rows[start], ix={
  ...indexes,
  name:getIndex(h,['Produkt','Product','Produktname','Product Name','Name','Beschreibung','Description']),
  currency:getIndex(h,['Währung','Wahrung','Currency','Valuta']),
  price:getIndex(h,['Kurs','Preis','Price','Schlusskurs','Schlußkurs','Closing price']),
  value:getIndex(h,['Wert','Market value','Marktwert','Value','Gesamtwert','Total value']),
  side:getIndex(h,['Kauf/Verkauf','Buy/Sell','Buy / Sell','Transaktion','Type','Art']),
  date:getIndex(h,['Datum','Date','Handelsdatum','Trade date'])
 };
 const kind=(ix.side>=0||ix.date>=0)?'transactions':'portfolio';
 // DEGIRO Swiss exports split "Wert" across currency + unlabeled amount,
 // followed by a separate "Wert in CHF" conversion column.
 const splitCurrencyValue=kind==='portfolio' && ix.currency<0 && ix.value>=0 &&
   ix.value+1<h.length && !String(h[ix.value+1]||'').trim() &&
   h.some(label=>/^wert in [A-Z]{3}$/i.test(String(label||'').trim()));
 if(splitCurrencyValue){ix.currency=ix.value;ix.value+=1;}
 const accountValueHeader=h.findIndex(label=>/^wert in [A-Z]{3}$/i.test(String(label||'').trim()));
 const accountCurrency=accountValueHeader>=0?String(h[accountValueHeader]).trim().slice(-3).toUpperCase():null;
 const records=[],invalid=[],cashBalances=[];
 for(let i=start+1;i<rows.length;i++){
  const row=rows[i],isin=(row[ix.isin]||'').trim().toUpperCase();
  if(options.strict&&row.length!==h.length){invalid.push(i+1);continue;}
  if(!isin){
   // Cash rows lack an ISIN; keep them separate from security holdings.
   if(splitCurrencyValue && /^CASH\b/i.test(String(row[ix.name]||''))){
    const currency=cell(row,ix.currency),amount=parseNumber(row[ix.value]),
          accountValue=accountValueHeader>=0?parseNumber(row[accountValueHeader]):null;
    if(/^[A-Z]{3}$/.test(currency)&&amount!==null){
     cashBalances.push({currency,amount,accountValue,accountCurrency});
     if(options.strict&&accountValueHeader>=0&&String(row[accountValueHeader]||'').trim()&&accountValue===null)invalid.push(i+1);
    }else if(options.strict)invalid.push(i+1);
   }else if(options.strict&&row.some(Boolean))invalid.push(i+1);
   continue;
  }
  if(!validISIN(isin)){invalid.push(i+1);continue;}
  const rawQty=(row[ix.qty]||'').trim();
  const qty=parseNumber(rawQty);
  if(qty===null){invalid.push(i+1);continue;}
  records.push({isin,quantity:qty,product:cell(row,ix.name),currency:cell(row,ix.currency),price:cell(row,ix.price),value:cell(row,ix.value),accountValue:accountValueHeader>=0?cell(row,accountValueHeader):'',side:cell(row,ix.side),date:cell(row,ix.date)});
 }
 if(!records.length)throw Error('Keine gültigen ISIN- und Mengenzeilen im Export gefunden.');
 return {kind,records,cashBalances,accountCurrency,invalidRows:invalid,source:'DEGIRO export (user-provided)',realtime:false,brokerVerified:false,ordersEnabled:false};
}
function validISIN(isin){
 if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(isin))return false;
 const digits=isin.replace(/[A-Z]/g,ch=>String(ch.charCodeAt(0)-55));
 let sum=0;[...digits].reverse().forEach((ch,i)=>{const n=Number(ch)*(i%2?2:1);sum+=Math.floor(n/10)+n%10;});
 return sum%10===0;
}
function cell(row,idx){return idx<0?'':String(row[idx]||'').trim().slice(0,120);}
function parseNumber(raw){
 let s=String(raw).replace(/\s/g,'').replace(/\u00a0/g,'');
 if(!s||!/^[+-]?[\d.,]+$/.test(s))return null;
 const comma=s.lastIndexOf(','),dot=s.lastIndexOf('.');
 if(comma>=0&&dot>=0)s=comma>dot?s.replace(/\./g,'').replace(',','.'):s.replace(/,/g,'');
 else if(comma>=0)s=s.replace(',','.');
 else if((s.match(/\./g)||[]).length>1)s=s.replace(/\./g,'');
 const v=Number(s);return Number.isFinite(v)&&Math.abs(v)<1e10?v:null;
}


/* Source bundled with Bob's CSV parser. No logins, API wrappers or orders. */
(function(){
'use strict';
const BROKER='https://trader.degiro.nl',BOB='https://bob-private-scanner.onrender.com';
const ARM='bob-export-arm-v1',QUEUE='bob-export-pending-v1',STATUS='bob-export-status-v1',VERSION='1.1.0';
const TTL=10*60*1000,MAX=2_000_000;
const isBob=location.origin===BOB,isBroker=location.origin===BROKER;
if(!isBob&&!isBroker)return;
const now=()=>Date.now();
let busy=false;
const page=typeof unsafeWindow==='undefined'?window:unsafeWindow;
// Use the page's real globals, not a userscript-manager window wrapper.
const nativeFetch=page.fetch.bind(page);
let brokerState='ready';
function brokerStatus(state=brokerState){
 brokerState=state;GM_setValue(STATUS,{state,at:now(),version:VERSION});
}
function armed(){const t=GM_getValue(ARM,0);return Number.isFinite(t)&&t>now()&&t<=now()+TTL+5000;}
function note(text){
 let el=document.getElementById('bob-export-bridge-note');
 if(!el){el=document.createElement('div');el.id='bob-export-bridge-note';el.setAttribute('role','status');
  el.style.cssText='position:fixed;bottom:18px;left:12px;right:12px;z-index:2147483647;padding:14px;border-radius:12px;background:#10263b;color:white;font:15px/1.5 sans-serif;box-shadow:0 3px 18px #0005;overflow-wrap:anywhere';
  document.documentElement.append(el);}
 el.textContent=text;
}
function post(type,extra={}){window.postMessage({type,...extra},BOB);}
function safeUrl(value,filename=''){
 try{
  const u=new URL(String(value),location.href);
  if(u.protocol==='blob:'&&u.origin===BROKER)return u.href;
  if(u.origin!==BROKER||u.protocol!=='https:'||u.username||u.password)return null;
  const csv=/\.csv$/i.test(filename)||/(?:\.csv|\/csv)\/?$/i.test(u.pathname)||['format','type'].some(k=>u.searchParams.get(k)?.toLowerCase()==='csv');
  // Only an existing export link selected by the page/user. Never invent endpoints.
  if(!csv||!/^\/reporting\//.test(u.pathname))return null;
  return u.href;
 }catch(_){return null;}
}
function safeExportUrl(anchor){return anchor?.tagName==='A'?safeUrl(anchor.href,anchor.getAttribute('download')||''):null;}
async function readExport(url){
 const controller=new page.AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
 try{
 const response=await nativeFetch(url,{method:'GET',credentials:'same-origin',redirect:'error',cache:'no-store',signal:controller.signal});
 if(!response.ok)throw Error('Export nicht erreichbar');
 const reader=response.body?.getReader();let text;
 if(reader){
  const decoder=new TextDecoder();let bytes=0;const parts=[];
  try{while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>MAX)throw Error('Export größer als 2 MB');parts.push(decoder.decode(value,{stream:true}));}parts.push(decoder.decode());text=parts.join('');}
  finally{await reader.cancel().catch(()=>{});}
 }else{text=await response.text();if(text.length>MAX)throw Error('Export größer als 2 MB');}
 const report=readReport(text,{strict:true});
 if(report.kind!=='portfolio')throw Error('Bitte Portfolio-CSV exportieren, keine Transaktionsliste.');
 if(report.invalidRows.length)throw Error('Export enthält ungültige Zeilen; bisheriger Bob-Depotstand bleibt erhalten.');
 // Validate duplicates and quantities before staging. No raw CSV/URLs/session data stored.
 const seen=new Set();for(const row of report.records){if(seen.has(row.isin))throw Error('Doppelte ISIN im Export.');seen.add(row.isin);}
 return report;
 }finally{clearTimeout(timeout);}
}
async function captureUrl(url){
 if(!url||!armed()||busy)return;
 busy=true;brokerStatus('reading');note('Bob prüft den Portfolioexport …');
 try{
  const report=await readExport(url);
  if(!armed())throw Error('Übernahme abgelaufen. In Bob erneut aktivieren.');
  const id=crypto.randomUUID();
  GM_setValue(QUEUE,{id,createdAt:now(),expiresAt:now()+TTL,report});brokerStatus('staged');
  note('Export für Bob bereit. Bob im selben Firefox öffnen; Übernahme dort aktivieren.');
 }catch(err){brokerStatus('error');note('Bob: '+(err.message||'Export konnte nicht übernommen werden.'));}
 finally{busy=false;}
}
function capture(anchor){return captureUrl(safeExportUrl(anchor));}
if(isBroker){
 const anchorProto=page.HTMLAnchorElement.prototype;
 const originalClick=anchorProto.click,originalDispatch=anchorProto.dispatchEvent;
 const forwarding=new WeakSet();
 function deferHttpExport(anchor,forward){
  const url=safeExportUrl(anchor);
  if(!url||!url.startsWith('https:')||!armed()||busy||forwarding.has(anchor))return false;
  // Firefox can cancel an in-flight copy when a same-tab download starts.
  // Read the selected CSV first (bounded to 12 seconds), then always forward
  // the original download even if the copy failed. Blob downloads stay immediate.
  forwarding.add(anchor);
  captureUrl(url).finally(()=>{try{forward();}finally{forwarding.delete(anchor);}});
  return true;
 }
 document.addEventListener('click',event=>{
  const anchor=event.target?.closest?.('a');if(!anchor||forwarding.has(anchor))return;
  if(event.cancelable&&deferHttpExport(anchor,()=>originalClick.call(anchor))){event.preventDefault();event.stopImmediatePropagation();return;}
  capture(anchor);
 },true);
 // FileSaver-style libraries dispatch a MouseEvent on a detached anchor.
 // Such events never reach document and do not call anchor.click().
 anchorProto.click=function(){
  const args=arguments;
  if(deferHttpExport(this,()=>originalClick.apply(this,args)))return;
  if(!forwarding.has(this))capture(this);
  return originalClick.apply(this,args);
 };
 anchorProto.dispatchEvent=function(event){
  const args=arguments;
  if(event?.type==='click'){
   if(deferHttpExport(this,()=>originalDispatch.apply(this,args)))return true;
   if(!forwarding.has(this))capture(this);
  }
  return originalDispatch.apply(this,args);
 };
 // Also cover a selected CSV opened in a new window, without suppressing it.
 const originalOpen=page.open;
 page.open=function(url){captureUrl(safeUrl(url));return originalOpen.apply(this,arguments);};
 function heartbeat(){if(armed())brokerStatus();}
 GM_addValueChangeListener(ARM,heartbeat);
 document.addEventListener('visibilitychange',heartbeat);
 window.addEventListener('pageshow',heartbeat);
 brokerStatus();setInterval(heartbeat,5000);

 return;
}
let pendingId=null;
function offer(){
 post('BOB_EXPORT_HELPER_READY',{version:VERSION});
 const value=GM_getValue(QUEUE,null);
 if(!value||typeof value.id!=='string'||!Number.isFinite(value.createdAt)||!Number.isFinite(value.expiresAt)||value.createdAt>now()+5000||value.createdAt<now()-TTL||value.expiresAt<=now()||value.expiresAt>value.createdAt+TTL){
  if(value)GM_deleteValue(QUEUE);return;
 }
 if(!armed()||pendingId===value.id)return;
 pendingId=value.id;
 post('BOB_EXPORT_OFFER',{id:value.id,createdAt:value.createdAt,report:value.report});
 setTimeout(()=>{if(pendingId===value.id)pendingId=null;},15000);
}
window.addEventListener('message',event=>{
 if(event.source!==window||event.origin!==BOB||!event.data)return;
 const d=event.data;
 if(d.type==='BOB_EXPORT_PROBE')post('BOB_EXPORT_HELPER_READY',{version:VERSION});
 if(d.type==='BOB_EXPORT_ARM'){
  if(!Number.isFinite(d.until)||d.until<=now()||d.until>now()+TTL+5000)return;
  GM_setValue(ARM,d.until);pendingId=null;post('BOB_EXPORT_ARMED');offer();diagnose();
 }
 if(d.type==='BOB_EXPORT_DISARM'){GM_deleteValue(ARM);GM_deleteValue(QUEUE);pendingId=null;}
 if(d.type==='BOB_EXPORT_RESULT'&&d.id===pendingId){
  const value=GM_getValue(QUEUE,null);
  if(value?.id===d.id)GM_deleteValue(QUEUE);
  pendingId=null;
 }
});
function diagnose(){
 const s=GM_getValue(STATUS,null);
 if(!s||!['ready','reading','staged','error'].includes(s.state)||s.version!==VERSION||!Number.isFinite(s.at)||s.at>now()+5000||s.at<now()-30000)return;
 post('BOB_EXPORT_BROKER_STATUS',{state:s.state,at:s.at,version:VERSION});
}
GM_addValueChangeListener(STATUS,diagnose);
GM_addValueChangeListener(QUEUE,()=>offer());
GM_addValueChangeListener(ARM,()=>offer());
function resume(){offer();diagnose();}
window.addEventListener('pageshow',resume);
window.addEventListener('focus',resume);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')resume();});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',resume);else resume();
})();

})();
