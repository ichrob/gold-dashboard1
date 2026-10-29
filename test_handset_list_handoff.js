'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('degiro_assistant.js','utf8');
const importer=src.slice(src.indexOf(' let handsetListBusy=false;'),src.indexOf(" window.addEventListener('hashchange',importHandsetList);"));
const pending=src.slice(src.indexOf(' const retryPendingList=async()=>{'),src.indexOf(' setTimeout(()=>retryPendingList().catch'));
(async()=>{
 const id='0123456789abcdef'.repeat(2),timers=[],events=[],stages=[];let requests=0,cleared='';
 const upload={disabled:true,dispatchEvent(e){events.push(e.type)}};
 const ctx={handsetRetryTimer:null,handsetImportId:'',listUploadMode:'',stagedListImages:[],URL,Date,Uint8Array,atob,Event,Error,upload,uploadStatus:{},setTimeout(fn){timers.push(fn);return timers.length},clearTimeout(){},
 handsetBatchId:()=>id,handsetReceipt:s=>stages.push(s),
 location:{href:'https://bob.example/?handset-list='+id+'#overview'},
 history:{replaceState(a,b,url){cleared=url}},document:{hidden:false,querySelector(){return {click(){events.push('products')}}}},
 DataTransfer:class{constructor(){this.files=[];this.items={add:f=>this.files.push(f)}}},
 File:class{constructor(data,name,options){Object.assign(this,{data,name},options)}},
 fetch:async url=>{requests++;assert.equal(url,'/api/android-list/latest?batchId='+id);return {ok:true,json:async()=>({batch:{batchId:id,images:[{at:new Date().toISOString(),png:'aGVsbG8='}]}})}}};
 vm.createContext(ctx);await vm.runInContext(importer+';importHandsetList()',ctx);
 assert.equal(requests,0);assert.equal(timers.length,1,'busy uploader must schedule a retry');
 upload.disabled=false;await timers.shift()();
 assert.equal(requests,1);assert.equal(upload.files.length,1);assert.equal(cleared,'/');
 assert.deepEqual(stages,['fetching','images-ready']);assert(events.includes('change'));
 // A newly delivered series takes precedence over stale pending screenshots.
 ctx.loadPendingDegiroList=()=>{throw Error('old pending images must not be read')};
 assert.equal(await vm.runInContext(pending+';retryPendingList()',ctx),false);
 console.log('Handset import retries busy uploader and takes priority over old pending images');
})().catch(e=>{console.error(e);process.exit(1)});
