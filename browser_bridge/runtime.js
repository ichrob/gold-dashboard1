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
 const report=readReport(text);
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
