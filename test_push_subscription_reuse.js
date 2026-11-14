'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync('push_manager.js','utf8');
const begin=script.indexOf('  async function registerServerPush(reg){');
const end=script.indexOf('  async function enable(){',begin);
assert(begin>0&&end>begin);
const functionSource=script.slice(begin,end);
function fixture(existingKey,opts={}){
 const key=new Uint8Array([3,29,51,77,108]);
 let serverCalls=[],unsubscribes=0,subscribes=0;
 const existing={
   endpoint:'https://push.test/existing',
   ...(existingKey===null?{}:{options:{applicationServerKey:existingKey}}),
   toJSON:()=>({endpoint:'https://push.test/existing',keys:{synthetic:true}}),
   async unsubscribe(){unsubscribes++;return true;}
 };
 const fresh={
   endpoint:'https://push.test/replacement',
   options:{applicationServerKey:key.buffer},
   toJSON:()=>({endpoint:'https://push.test/replacement',keys:{synthetic:true}})
 };
 const manager={
   async getSubscription(){return opts.noExisting?null:existing;},
   async subscribe(options){
     subscribes++;
     assert.equal(options.userVisibleOnly,true);
     assert.deepEqual([...options.applicationServerKey],[...key]);
     return fresh;
   }
 };
 const ctx={
   Uint8Array,JSON,Error,Boolean,PUSH_API:'/api/push',
   b64ToBytes:()=>key,
   fetch:async (url,body)=>{
     serverCalls.push({url,body});
     if(url.endsWith('/vapid-public-key')){
       return {ok:opts.keyFailure!==true,async json(){return {publicKey:'synthetic-vapid'}}};
     }
     if(url.endsWith('/subscribe'))return {ok:opts.subscribeFailure!==true};
     return {ok:true};
   }
 };
 vm.createContext(ctx);
 vm.runInContext(functionSource,ctx,{filename:'push-subscription.js'});
 return {run:()=>ctx.registerServerPush({pushManager:manager}),
         calls:()=>serverCalls,metrics:()=>({unsubscribes,subscribes})};
}
(async()=>{
 const match=fixture(new Uint8Array([3,29,51,77,108]).buffer);
 assert.equal(await match.run(),true);
 assert.deepEqual(match.metrics(),{unsubscribes:0,subscribes:0});
 assert.deepEqual(match.calls().map(x=>x.url),[
  '/api/push/vapid-public-key','/api/push/subscribe']);
 const body=JSON.parse(match.calls().at(-1).body.body);
 assert.equal(body.subscription.endpoint,'https://push.test/existing');

 const changed=fixture(new Uint8Array([9,9,9,9,9]).buffer);
 assert.equal(await changed.run(),true);
 assert.deepEqual(changed.metrics(),{unsubscribes:1,subscribes:1});
 assert.deepEqual(changed.calls().map(x=>x.url),[
  '/api/push/vapid-public-key','/api/push/unsubscribe','/api/push/subscribe']);
 assert.equal(JSON.parse(changed.calls().at(-1).body.body).subscription.endpoint,
   'https://push.test/replacement');

 const legacy=fixture(null);
 assert.equal(await legacy.run(),true);
 assert.deepEqual(legacy.metrics(),{unsubscribes:1,subscribes:1});

 const fresh=fixture(null,{noExisting:true});
 assert.equal(await fresh.run(),true);
 assert.deepEqual(fresh.metrics(),{unsubscribes:0,subscribes:1});

 const rejected=fixture(new Uint8Array([3,29,51,77,108]).buffer,
                        {subscribeFailure:true});
 assert.equal(await rejected.run(),false,'Must not claim server registration on 503');
 assert.deepEqual(rejected.metrics(),{unsubscribes:0,subscribes:0},
   'No destructive rotation on a failed idempotent refresh');

 const missingKey=fixture(new Uint8Array([3,29,51,77,108]).buffer,{keyFailure:true});
 assert.equal(await missingKey.run(),false);
 assert.deepEqual(missingKey.metrics(),{unsubscribes:0,subscribes:0});
 console.log('Push subscription: reuse VAPID match, rotate mismatch/legacy, fail closed on unavailable server.');
})().catch(e=>{console.error(e);process.exitCode=1;});
