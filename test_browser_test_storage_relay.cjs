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
 console.log('Synthetic userscript storage relay: non-blocking ordered delivery passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
