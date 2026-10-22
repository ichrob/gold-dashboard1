'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict'),vm=require('node:vm');
const code=fs.readFileSync('degiro_assistant.js','utf8');
function extract(start,end){
 const i=code.indexOf(start),j=code.indexOf(end,i+start.length);
 assert(i>=0&&j>i, 'Missing source function: '+start);
 return code.slice(i,j);
}
const inject=extract('async function inject(){','if(typeof document!=="undefined")');
const restorePos=inject.indexOf('await restoreListArchive();');
const hydratePos=inject.indexOf('restoreProductRows(applyResearchedTerms(restoredProducts));');
const readyPos=inject.indexOf('productRowsReady=true;');
const statusPos=inject.indexOf("b.querySelector('#dgCentralStatus').textContent=");
const renderPos=inject.indexOf(' rankUI();\n restoreServerCorrection().then(committed=>');
assert(restorePos>=0&&hydratePos>restorePos&&readyPos>hydratePos);
assert(statusPos>readyPos&&renderPos>statusPos,'Local rows render before the optional server sync');
assert(!inject.includes('await restoreServerCorrection();'), 'Remote correction must never block local products');
const correction=extract('async function restoreServerCorrection(){','function mountListCorrection(');
assert(correction.includes('signal:controller.signal'));
assert(correction.includes('setTimeout(()=>controller.abort(),8000)'));
assert(correction.includes('restoreProductRows(applyResearchedTerms(loadIdentities()))'));
assert(correction.includes('return committed'));
const archive=extract('function archiveTransaction(mode,action){','function showListArchive(){');
assert(archive.includes("mode==='readonly'?setTimeout"));
assert(archive.includes(':null;'), 'Writes must not time out ambiguously');
const restore=extract('async function restoreListArchive(){','const IDENTITY_KEY=');
assert(restore.includes('productStorageBlocked=true'), 'Unavailable archive must block destructive cache overwrites');
const store=extract('function writeStoredProducts(items){','function saveIdentities(){');
const existingGeneration='2026-10-21T06:39:49.626Z';
const values=new Map([['bobDegiroProductsV2',JSON.stringify({version:2,products:[{isin:'DE000FG14AV8'}],listUploadedAt:existingGeneration})]]);
const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};
const safeContext={localStorage:storage,console};
const safeWriter=vm.runInNewContext([
 'let productStorageBlocked=false,productArchivePayload="",productStorageMessage="",listArchive=null;',
 'const PRODUCT_STORE_KEY="bobDegiroProductsV2",IDENTITY_KEY="bobDegiroIdentitiesV1";',
 'const cleanStoredProduct=x=>x;',
 store,
 'writeStoredProducts;'
].join('\n'),safeContext);
assert.equal(safeWriter([{isin:'DE000FG14AV8',name:'Gold SHORT',direction:'SHORT'}]),true);
assert.equal(JSON.parse(values.get('bobDegiroProductsV2')).listUploadedAt,existingGeneration,
 'Opening on another day or browser cannot fabricate/reset list observation date');
(async()=>{
  let ticks=0,requested=0;
  const fake={
   indexedDB:{open:()=>{requested++;return {};}},
   setTimeout:fn=>{ticks++;setImmediate(fn);return ticks;},
   clearTimeout:()=>{}
  };
  const archiveFn=vm.runInNewContext(archive+'\narchiveTransaction;',fake);
  await assert.rejects(archiveFn('readonly',()=>{}),/antwortet nicht/);
  assert.equal(requested,1);
  assert.equal(ticks,1,'Only readonly operations should install the bounded fallback');
  console.log('DEGIRO list restore: local-first, bounded read/network, preserve upload date and protect stored list.');
})().catch(e=>{console.error(e);process.exitCode=1;});
