/* Shared authenticated read-only product audit fetch.
 * Deduplicates only concurrent/near-simultaneous UI reads on the same page.
 * The original audit times are untouched and never become broker approvals.
 */
(function(root){
'use strict';
function createAuditReadPool(context, options={}){
 const expiryMs=Number.isFinite(options.cacheMs)?Math.min(Math.max(options.cacheMs,0),5000):3000;
 const timeoutMs=Number.isFinite(options.timeoutMs)?Math.min(Math.max(options.timeoutMs,100),12000):10000;
 let cached=null,cacheAt=0,flight=null;
 const counters={network:0,shared:0,cached:0,failures:0};
 const copy=source=>JSON.parse(JSON.stringify(source));
 function clear(){cached=null;cacheAt=0;}
 async function fetchReport(){
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeoutMs);
  try{
   if(typeof context.fetch!=='function')throw Error('Der Berichtabruf ist nicht verfügbar');
   counters.network++;
   const response=await context.fetch('/api/degiro/audit',{
    credentials:'same-origin',cache:'no-store',signal:ctl.signal
   });
   if(!response.ok)throw Error('Prüfbericht HTTP '+response.status);
   const body=await response.json();
   if(!body||!['ok','partial','stale'].includes(body.status)||
      !Array.isArray(body.items)||body.items.length>500||
      typeof body.lastCheckedAt!=='string')
    throw Error('Privater Prüfbericht ungültig oder nicht verfügbar');
   // Only a strict original source timestamp; never set or renew checkedAt.
   const time=Date.parse(body.lastCheckedAt);
   if(!/(?:Z|[+-]\d{2}:\d{2})$/i.test(body.lastCheckedAt)||
      !Number.isFinite(time)||time>Date.now())throw Error('Originalzeit des Prüfberichts unbestätigt');
   cached=copy(body);cacheAt=Date.now();
   return copy(body);
  }catch(error){counters.failures++;clear();throw error;}
  finally{clearTimeout(timer);}
 }
 function read({force=false}={}){
  if(context.BobSession?.expired?.()===true){
   clear();return Promise.reject(Error('Anmeldung abgelaufen'));
  }
  if(flight){counters.shared++;return flight.then(copy);}
  if(!force&&cached&&Date.now()>=cacheAt&&Date.now()-cacheAt<=expiryMs){
   counters.cached++;return Promise.resolve(copy(cached));
  }
  flight=fetchReport().finally(()=>{flight=null;});
  return flight.then(copy);
 }
 function diagnostics(){
  return {...counters,inFlight:!!flight,cacheAgeMs:cached?Math.max(0,Date.now()-cacheAt):null,
   // No ISINs, product prices, credentials, private payloads or account data.
   cacheMs:expiryMs,readOnly:true,tradeable:false};
 }
 return {read,clear,diagnostics};
}
const api=createAuditReadPool(root);
root.BobProductAuditReadPool=api;
if(typeof module==='object'&&module.exports)module.exports={createAuditReadPool};
})(typeof window!=='undefined'?window:globalThis);
