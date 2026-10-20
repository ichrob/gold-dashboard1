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
