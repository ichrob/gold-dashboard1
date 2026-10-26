const fs=require('fs'),vm=require('vm'),assert=require('assert');
const records=new Map(),storage=new Map();let fail=false;let now=Date.parse("2026-10-05T19:59:59Z");
class Clock extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
const indexedDB={open(){const r={};queueMicrotask(()=>{r.result={close(){},transaction(){const tx={};const staged=new Map(records);tx.objectStore=()=>({get(k){const r={result:records.get(k)};queueMicrotask(()=>r.onsuccess?.());return r},delete(k){staged.delete(k);return {}},put(v,k){staged.set(k,structuredClone(v));return {result:k}}});setImmediate(()=>{if(fail){tx.error=Error('quota');tx.onabort();}else{records.clear();for(const [k,v]of staged)records.set(k,v);tx.oncomplete();}});return tx;}};r.onsuccess();});return r;}};
let responseData,fetchRead;
function restart(){const ctx={Date:Clock,fetch:async()=>{if(fetchRead)return fetchRead();return {ok:true,json:async()=>responseData}},window:{BobDegiroAllProducts:require('./degiro_all_products')},indexedDB,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},navigator:{},document:undefined};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={restoreServerCorrection,rankUI,'),ctx);ctx.document={getElementById:()=>null,querySelector:()=>null};return ctx.window.BobDegiro;}

(async()=>{
 const isin='DE000FC1CHB7',stamp=new Date(now).toISOString();
 let b=restart();
 // Refresh before initialization must not touch DOM or persist empty fields.
 b.rankUI();assert.equal(storage.size,0);
 await b.saveListArchive([{name:'list.jpg',bytes:'original'}],[{isin,direction:'LONG'}]);
 storage.set('bobDegiroProductsV2',JSON.stringify({version:2,products:[],listUploadedAt:stamp}));
 records.set('products',storage.get('bobDegiroProductsV2'));
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,isin,'Original archive recovers an empty cache');
 b.saveIdentities();
 assert.equal(b.loadIdentities().length,1);
 records.clear();storage.clear();b=restart();
 responseData={ok:true,corrected:false,listUploadedAt:stamp,products:[{isin,name:'SG Gold Call',direction:'LONG'}]};
 await b.restoreServerCorrection();
 assert.equal(b.loadIdentities()[0].isin,isin,'Ordinary server list restores without corrected flag');
 assert.equal(records.get('list').storedAt,stamp);
 assert.equal(b.loadIdentities()[0].isinConfirmed,false);
 // A different local generation must never be replaced.
 now+=1000;await b.saveListArchive([{name:'new.jpg'}],[{isin:'DE000FG4JXV7'}]);
 const history=JSON.parse(storage.get('bobDegiroIsinEvidenceHistoryV1')).items;
 assert(history.some(x=>x.isin===isin&&x.lastSeenAt===stamp),'Import boundary preserves original list without a repaint');
 assert(history.some(x=>x.isin==='DE000FG4JXV7'&&x.lastSeenAt===new Date(now).toISOString()));
 assert(history.every(x=>x.brokerTradeable===false));
 await b.restoreServerCorrection();
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,'DE000FG4JXV7');
 // An upload during a pending server response wins.
 records.clear();storage.clear();b=restart();let finish;
 fetchRead=()=>new Promise(r=>{finish=r});
 const pending=b.restoreServerCorrection();
 now+=1000;await b.saveListArchive([{name:'latest.jpg'}],[{isin:'DE000FG4JXV7'}]);
 finish({ok:true,json:async()=>responseData});await pending;
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,'DE000FG4JXV7');
 const server=fs.readFileSync('server.py','utf8');
 const policies=[...server.matchAll(/img-src ([^;]+);/g)];
 assert.equal(policies.length,3);
 assert(policies.every(x=>x[1].includes('blob:')),'Every page permits local image previews');
 console.log('Startup guard, empty cache recovery, server restore, generation races and image CSP passed');
})().catch(e=>{console.error(e);process.exit(1)});
