'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.env.BOB_EXPORT_CLOCK_SOURCE||'browser_bridge/runtime.js','utf8');
const capture=source.slice(source.indexOf('async function captureUrl('),source.indexOf('function capture(anchor)'));
const offer=source.slice(source.indexOf('function offer(){'),source.indexOf("window.addEventListener('message',event=>"));
(async()=>{
 let clock=1000000;const values={},messages=[];let deletes=0;
 const context={now:()=>clock++,TTL:600000,VERSION:'synthetic',QUEUE:'queue',busy:false,pendingId:null,
  armed:()=>true,crypto:{randomUUID:()=> 'synthetic-export'},
  GM_setValue:(key,value)=>{values[key]=value;},
  GM_getValue:(key,fallback)=>values[key]||fallback,
  GM_deleteValue:key=>{delete values[key];deletes++;},
  brokerStatus:()=>{},note:()=>{},post:type=>messages.push(type),setTimeout:()=>{}};
 vm.createContext(context);vm.runInContext(capture+'\n'+offer,context);
 await context.captureUrl('synthetic-selected-export',async()=>({kind:'portfolio'}));
 assert.equal(values.queue.expiresAt-values.queue.createdAt,600000,
  'Two changing clock reads must not create an overlong export envelope');
 context.offer();assert(messages.includes('BOB_EXPORT_OFFER'));
 assert.equal(deletes,0);
 const accepted=values.queue;
 context.pendingId=null;values.queue={...accepted,expiresAt:accepted.expiresAt+1};
 context.offer();assert.equal(deletes,1,'Overlong TTL remains rejected');
 values.queue={...accepted,expiresAt:clock-1};context.offer();
 assert.equal(deletes,2,'Expired exports remain rejected');
 console.log('Export clock: forced millisecond tick accepted; overlong and expired envelopes rejected');
})().catch(error=>{console.error(error);process.exitCode=1;});
