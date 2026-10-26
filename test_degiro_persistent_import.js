'use strict';
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const {File}=require('node:buffer');
const {webcrypto}=require('node:crypto');
const db=new Map();
const indexedDB={open(){
 const request={};
 queueMicrotask(()=>{
  request.result={close(){},transaction(){
   const tx={};
   tx.objectStore=()=>({
    get(key){const r={result:db.get(key)};queueMicrotask(()=>tx.oncomplete());return r;},
    put(value,key){db.set(key,value);const r={result:key};queueMicrotask(()=>tx.oncomplete());return r;},
    delete(key){db.delete(key);const r={result:undefined};queueMicrotask(()=>tx.oncomplete());return r;}
   });return tx;
  }};
  request.onsuccess();
 });
 return request;
}};
const ctx={window:{},indexedDB,crypto:webcrypto,File,Date,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro;
(async()=>{
 const raw=new File([Buffer.from('same-byte-content')],'1000075082.jpg',{type:'image/jpeg'});
 assert.equal(await b.savePendingDegiroList([raw]),true);
 assert.equal(db.has('pending-degiro-list'),true);
 const restored=await b.loadPendingDegiroList();
 assert.equal(restored.length,1);
 assert.equal(restored[0].name,raw.name);
 assert.equal(restored[0].size,raw.size);
 assert((await b.degiroFileDiagnostic(restored[0])).includes('SHA-256'));
 assert.equal(await b.recognizeReviewedDegiroOriginal(restored[0]),null,'unknown file must never gain evidence');
 const stale=await b.loadPendingDegiroList(Date.parse('2000-01-01T12:00:00Z'));
 assert.equal(stale,null,'pending photos do not become a fresh list in later days');
 await b.clearPendingDegiroList();
 assert.equal(await b.loadPendingDegiroList(),null);
 assert.equal(db.has('pending-degiro-list'),false);
 const huge={name:'too-large.jpg',size:12000001,arrayBuffer:async()=>new ArrayBuffer(0)};
 assert.equal(await b.savePendingDegiroList([huge]),false);
 const html=fs.readFileSync('Bob.html','utf8');
 assert(html.includes('/degiro_assistant.js?v=20261026-mini-daily-ocr-v1'),'browser loads new importer URL');
 console.log('Android pending DEGIRO images survive restart, retain original bytes, stale data blocked, safe fallback, browser cache-bust.');
})().catch(error=>{console.error(error);process.exitCode=1;});
