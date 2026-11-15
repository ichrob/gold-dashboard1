'use strict';

// Synthetic Playwright-only manager relay. Never log values, CSVs, keys, page
// URLs, or exception messages: they may contain private broker information.
function createStorageRelay(pages, options={}){
 const values={};
 let delivery=Promise.resolve(),reported=0;
 const failures=[];
 let closedTargets=0;
 const roleOf=options.roleOf || (()=>'synthetic-target');
 const requiredTarget=options.requiredTarget || (()=>true);
 function seed(key,value,remove=false){
  if(remove)delete values[key];else values[key]=value;
 }
 function write(sourcePage,key,value,remove=false){
  seed(key,value,remove);
  // Keep the asynchronous producer non-blocking. Awaiting another page here
  // can deadlock Playwright exposed bindings when that page writes an ACK.
  delivery=delivery.then(()=>Promise.all(pages().filter(page=>page!==sourcePage).map(async page=>{
   try{
    await page.evaluate(({key,value,remove})=>window.gmRemote(key,value,remove),
     {key,value,remove});
   }catch(error){
    if(typeof page.isClosed==='function' && page.isClosed()){
     closedTargets++;
    }else if(requiredTarget(page)){
     // The previous catch(()=>{}) misreported an active Bob tab's rejected
     // delivery as a successful flush, leading to an opaque 12-s timeout.
     failures.push({phase:'cross-tab-delivery',
       targetRole:roleOf(page),errorClass:typeof error?.name==='string'
        ?error.name:'Error'});
    }
   }
  })));
 }
 async function flush(){
  let pending;
  do{pending=delivery;await pending;}while(pending!==delivery);
  if(failures.length>reported){
   const fresh=failures.slice(reported);
   reported=failures.length;
   const failure=new Error('Synthetic relay delivery failed: '+JSON.stringify(fresh));
   failure.code='SYNTHETIC_RELAY_DELIVERY_FAILED';
   failure.details=fresh;
   throw failure;
  }
 }
 function status(){
  return {deliveryFailures:failures.length,closedTargets};
 }
 return {values,seed,write,flush,status};
}

module.exports={createStorageRelay};
