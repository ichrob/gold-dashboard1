const fs=require('fs'),vm=require('vm'),assert=require('assert');
const records=new Map(),storage=new Map();let fail=false;let now=Date.parse("2026-10-05T19:59:59Z");
class Clock extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
const indexedDB={open(){const r={};queueMicrotask(()=>{r.result={close(){},transaction(){const tx={};const staged=new Map(records);tx.objectStore=()=>({get(k){const r={result:records.get(k)};queueMicrotask(()=>r.onsuccess?.());return r},delete(k){staged.delete(k);return {}},put(v,k){staged.set(k,structuredClone(v));return {result:k}}});setImmediate(()=>{if(fail){tx.error=Error('quota');tx.onabort();}else{records.clear();for(const [k,v]of staged)records.set(k,v);tx.oncomplete();}});return tx;}};r.onsuccess();});return r;}};
function restart(){const ctx={Date:Clock,window:{},indexedDB,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},navigator:{},document:undefined};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);ctx.document={getElementById:()=>null};return ctx.window.BobDegiro;}
(async()=>{
 let b=restart();
 const oldIsin='DE000FG4JXV7',newIsin='DE000FC1CHB7';
 await b.saveListArchive([{name:'list.jpg',bytes:'original'}],[{isin:oldIsin,price:24.82}]);
 const firstTime=records.get('list').storedAt;
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].price,24.82);
 assert.equal(records.get('list').files[0].blob.bytes,'original');
 b.writeStoredProducts([{isin:oldIsin,price:25.5}]);await new Promise(r=>setImmediate(()=>setImmediate(r)));
 storage.clear();b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].price,25.5);
 // Quota/IDB failure MUST keep previous list and values.
 fail=true;
 await assert.rejects(()=>b.saveListArchive([{name:'replacement.jpg'}],[{isin:newIsin,price:1}]));
 assert.equal(records.get('list').files[0].name,'list.jpg');
 assert.equal(JSON.parse(records.get('products')).products[0].price,25.5);
 fail=false;
 now=Date.parse('2026-10-05T20:00:00Z'); // 22:00 Zurich
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,oldIsin);
 assert(records.has('list'),'A saved list must survive the former 22:00 cutoff');
 now=Date.parse('2026-10-06T06:00:00Z');
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,oldIsin,'Old list remains until successful replacement');
 assert.equal(records.get('list').storedAt,firstTime,'Source observation time is not refreshed');
 assert(!b.listExpired('2026-10-05'),'Product identities must remain on following days');
 assert(!b.listExpired('2026-12-01',Date.parse('2026-12-01T21:00:00Z')),'Winter evenings do not expire lists');
 // A new screenshot *replaces* rather than merging old products, evidence, and images.
 now=Date.parse('2026-10-06T06:01:00Z');
 await b.saveListArchive([{name:'new-list.jpg',bytes:'current'}],[{isin:newIsin,price:11.1}]);
 b=restart();await b.restoreListArchive();
 const items=b.loadIdentities();
 assert.equal(items.length,1);
 assert.equal(items[0].isin,newIsin);
 assert.equal(items[0].price,11.1);
 assert.equal(records.get('list').files.length,1);
 assert.equal(records.get('list').files[0].name,'new-list.jpg');
 assert(!JSON.stringify(records.get('products')).includes(oldIsin),'Old ISIN must not survive replacement');
 assert.notEqual(records.get('list').storedAt,firstTime);
 now=Date.parse('2026-10-10T14:00:00Z');
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,newIsin,'List survives weekend');
 await assert.rejects(()=>b.saveListArchive([{name:'blank'}],[]));
 assert.equal(b.loadIdentities()[0].isin,newIsin,'An invalid OCR result must preserve the active list');

 // Automatic reread of the retained original repairs only invalid identities.
 const uncertain={isin:'DEOOOPJONB98',name:'BNP GOLD Unlimited Long SL 4004.1466 STR',direction:'LONG'};
 const valid={isin:newIsin,name:'SG Gold Call',direction:'LONG',price:11.1,snapshot:{isin:newIsin,sourceTime:'2026-10-14T06:20:00Z'}};
 now=Date.parse('2026-10-14T06:20:00Z');
 await b.saveListArchive([{name:'current.jpg',bytes:'original'}],[valid,uncertain]);
 const originalTime=records.get('list').storedAt;
 b=restart();await b.restoreListArchive();
 const reread='SG Gold Call '+newIsin+'\nBNP GOLD Unlimited Long SL 4004.1466 STR 4004.1466 R 10 | DE000PJ9NB98';
 const repaired=await b.recoverArchivedList(async()=>({data:{text:reread}}));
 assert.equal(repaired.corrected,1);
 assert.equal(repaired.rows.length,2);
 assert.equal(repaired.rows[0].snapshot.sourceTime,valid.snapshot.sourceTime);
 assert.equal(records.get('list').storedAt,originalTime);
 assert.equal(records.get('list').files[0].blob.bytes,'original');
 assert.equal(repaired.rows[1].isin,'DE000PJ9NB98');
 assert.equal(repaired.rows[1].isinConfirmed,false);
 assert.equal(await b.recoverArchivedList(async()=>{throw Error('must not repeat')}),null);
 // No repair may remove known IDs, or overwrite a replacement upload.
 await b.saveListArchive([{name:'uncertain.jpg'}],[valid,uncertain]);
 b=restart();await b.restoreListArchive();
 assert.equal(await b.recoverArchivedList(async()=>({data:{text:reread.replace(newIsin,oldIsin)}})),null);
 b=restart();await b.restoreListArchive();
 let finish;
 const pending=b.recoverArchivedList(()=>new Promise(resolve=>{finish=resolve}));
 now+=1000;
 await b.saveListArchive([{name:'replacement.jpg'}],[{isin:oldIsin}]);
 finish({data:{text:reread}});
 assert.equal(await pending,null);
 assert.equal(records.get('list').files[0].name,'replacement.jpg');
 b=restart();await b.restoreListArchive();
 assert.equal(b.loadIdentities()[0].isin,oldIsin);
 console.log('Automatic retained-list recovery: identity, timestamps, provenance and concurrent replacement passed');
 console.log('Persistent DEGIRO list: midnight, weekend, atomic replacement, and failure preservation passed');
})().catch(e=>{console.error(e);process.exit(1)});
