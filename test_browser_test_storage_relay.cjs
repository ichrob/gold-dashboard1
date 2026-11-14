'use strict';
const assert=require('node:assert/strict');
const {createStorageRelay}=require('./browser_test_storage_relay.cjs');

(async()=>{
 const events=[];
 let relay;
 const bob={name:'bob',async evaluate(_fn,args){
  events.push(`bob:${args.key}:${args.remove}`);
  if(args.key==='queue'&&!args.remove)relay.write(bob,'queue',null,true);
 }};
 const broker={name:'broker',async evaluate(_fn,args){
  events.push(`broker:${args.key}:${args.remove}`);
 }};
 relay=createStorageRelay(()=>[bob,broker]);

 const persisted={id:'reload',createdAt:1};
 assert.equal(relay.seed('queue',persisted),undefined,
  'persisted manager state is staged without a cross-tab delivery');
 assert.deepEqual(relay.values.queue,persisted);
 assert.deepEqual(events,[],'seeding reload state must not notify the unloading page');
 relay.seed('queue',null,true);

 const queueWrite=relay.write(broker,'queue',{id:'one'});
 const statusWrite=relay.write(broker,'status',{state:'staged'});
 assert.equal(queueWrite,undefined,'storage binding must not wait on cross-tab evaluation');
 assert.equal(statusWrite,undefined,'parallel storage writes stay non-blocking');
 await relay.flush();

 assert.deepEqual(events,[
  'bob:queue:false',
  'bob:status:false',
  'broker:queue:true'
 ],'reentrant result cleanup is delivered after already queued writes');
 assert.equal(relay.values.queue,undefined);
 assert.deepEqual(relay.values.status,{state:'staged'});
 // #1712 negative: an active Bob tab rejects cross-tab delivery. This MUST
 // fail flush with sanitized metadata, not look like an accepted export.
 let rejectActive=true,seen=0;
 const liveBob={isClosed:()=>false,async evaluate(){
  seen++;
  if(rejectActive)throw Error('PRIVATE-CSV-CONTENT must never enter test metadata');
 }};
 const source={async evaluate(){}};
 const negative=createStorageRelay(()=>[liveBob,source],{
  roleOf:p=>p===liveBob?'bob':'broker'
 });
 negative.write(source,'queue',{privateField:'PRIVATE-CSV-CONTENT'});
 await assert.rejects(negative.flush(),error=>{
  assert.equal(error.code,'SYNTHETIC_RELAY_DELIVERY_FAILED');
  assert.deepEqual(error.details,[{phase:'cross-tab-delivery',targetRole:'bob',errorClass:'Error'}]);
  assert(!JSON.stringify(error).includes('PRIVATE-CSV-CONTENT'));
  return true;
 });
 assert.equal(negative.status().deliveryFailures,1);
 // A reported failure must not poison the ordered queue forever.
 rejectActive=false;
 negative.write(source,'status',{state:'staged'});
 await negative.flush();
 assert.equal(seen,2);

 // Closing a tab after it was scheduled is different from a live rejected
 // page.evaluate; treat the former as a normal navigation/teardown.
 const closed={isClosed:()=>true,async evaluate(){
  throw Error('Target closed during reload');
 }};
 const closedRelay=createStorageRelay(()=>[closed,source]);
 closedRelay.write(source,'queue',{id:'close'});
 await closedRelay.flush();
 assert.equal(closedRelay.status().deliveryFailures,0);
 assert.equal(closedRelay.status().closedTargets,1);

 console.log('Synthetic userscript storage relay: non-blocking ordered delivery passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
