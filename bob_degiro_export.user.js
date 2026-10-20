// ==UserScript==
// @name         Bob DEGIRO Export-Brücke
// @namespace    https://bob-private-scanner.onrender.com/
// @version      1.0.0
// @description  Übergibt ausgewählte DEGIRO-Portfolioexporte an Bob. Keine Anmeldung oder Orders.
// @match        https://trader.degiro.nl/*
// @match        https://bob-private-scanner.onrender.com/*
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
const ARM='bob-export-arm-v1',QUEUE='bob-export-pending-v1';
const TTL=10*60*1000,MAX=2_000_000;
const isBob=location.origin===BOB,isBroker=location.origin===BROKER;
if(!isBob&&!isBroker)return;
const now=()=>Date.now();
let busy=false;
function armed(){const t=GM_getValue(ARM,0);return Number.isFinite(t)&&t>now()&&t<=now()+TTL+5000;}
function note(text){
 let el=document.getElementById('bob-export-bridge-note');
 if(!el){el=document.createElement('div');el.id='bob-export-bridge-note';el.setAttribute('role','status');
  el.style.cssText='position:fixed;bottom:18px;left:12px;right:12px;z-index:2147483647;padding:14px;border-radius:12px;background:#10263b;color:white;font:15px/1.5 sans-serif;box-shadow:0 3px 18px #0005;overflow-wrap:anywhere';
  document.documentElement.append(el);}
 el.textContent=text;
}
function post(type,extra={}){window.postMessage({type,...extra},BOB);}
function safeExportUrl(anchor){
 if(!anchor||anchor.tagName!=='A')return null;
 try{
  const u=new URL(anchor.href,location.href),filename=anchor.getAttribute('download')||'';
  if(u.protocol==='blob:'&&u.origin===BROKER)return u.href;
  if(u.origin!==BROKER||u.protocol!=='https:'||u.username||u.password)return null;
  const csv=/\.csv$/i.test(filename)||/\.csv$/i.test(u.pathname)||['format','type'].some(k=>u.searchParams.get(k)?.toLowerCase()==='csv');
  // Only an existing export link selected by the page/user. Never invent endpoints.
  if(!csv||!/^\/reporting\//.test(u.pathname))return null;
  return u.href;
 }catch(_){return null;}
}
async function readExport(url){
 const response=await fetch(url,{method:'GET',credentials:'same-origin',redirect:'error',cache:'no-store'});
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
}
async function capture(anchor){
 const url=safeExportUrl(anchor);if(!url||!armed()||busy)return;
 busy=true;note('Bob prüft den Portfolioexport …');
 try{
  const report=await readExport(url);
  if(!armed())throw Error('Übernahme abgelaufen. In Bob erneut aktivieren.');
  const id=crypto.randomUUID();
  GM_setValue(QUEUE,{id,createdAt:now(),expiresAt:now()+TTL,report});
  note('Export für Bob bereit. Bob im selben Firefox öffnen; Übernahme dort aktivieren.');
 }catch(err){note('Bob: '+(err.message||'Export konnte nicht übernommen werden.'));}
 finally{busy=false;}
}
if(isBroker){
 document.addEventListener('click',event=>{const anchor=event.target?.closest?.('a');if(anchor)capture(anchor);},true);
 // Some download libraries dispatch clicks on detached anchors. This hook sees
 // only export links; it does not read requests, cookies, passwords or page state.
 const original=HTMLAnchorElement.prototype.click;
 HTMLAnchorElement.prototype.click=function(){capture(this);return original.apply(this,arguments);};
 return;
}
let pendingId=null;
function offer(){
 post('BOB_EXPORT_HELPER_READY');
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
 if(d.type==='BOB_EXPORT_PROBE')post('BOB_EXPORT_HELPER_READY');
 if(d.type==='BOB_EXPORT_ARM'){
  if(!Number.isFinite(d.until)||d.until<=now()||d.until>now()+TTL+5000)return;
  GM_setValue(ARM,d.until);pendingId=null;post('BOB_EXPORT_ARMED');offer();
 }
 if(d.type==='BOB_EXPORT_DISARM'){GM_deleteValue(ARM);GM_deleteValue(QUEUE);pendingId=null;}
 if(d.type==='BOB_EXPORT_RESULT'&&d.id===pendingId){
  const value=GM_getValue(QUEUE,null);
  if(value?.id===d.id)GM_deleteValue(QUEUE);
  pendingId=null;
 }
});
GM_addValueChangeListener(QUEUE,()=>offer());
GM_addValueChangeListener(ARM,()=>offer());
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',offer);else offer();
})();

})();
