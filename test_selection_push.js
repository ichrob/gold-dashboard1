const fs=require('fs'),vm=require('vm'),assert=require('assert');
let deliveries=0;
const state={registered:true,serverRegistered:false,general:true,trade:true,activeTrade:true};
const window={addEventListener:()=>{}};
function Notification(){deliveries++;}Notification.permission='granted';
vm.runInNewContext(fs.readFileSync('push_manager.js','utf8'),{window,localStorage:{getItem:()=>JSON.stringify(state)},Notification,navigator:{}});
(async()=>{
 for(const data of [{isin:'DE000FG4JXV7'},{kind:'product-selection'},{kind:'best-trade',approved:true}]){
  assert.equal(await window.BobPush.emit('general','Bob Auswahl','fixture',data),false);
 }
 assert.equal(await window.BobPush.emit('general','Bob – bester Trade','fixture'),false);
 assert.equal(deliveries,0);
 assert(await window.BobPush.emit('general','Bob – Marktsignal','Keine Produktfreigabe',{kind:'signal-change'}));
 assert(await window.BobPush.emit('trade','Bob – Stop-Loss erreicht','fixture',{kind:'active-trade-warning'}));
 assert.equal(deliveries,2);
 console.log('Product recommendation pushes blocked; market and active-trade warnings preserved');
})().catch(e=>{console.error(e);process.exitCode=1;});

(async()=>{
 let stored={registered:true,serverRegistered:true,general:false},requests=0,workerMessages=[];
 const w={addEventListener:()=>{}},reg={active:{postMessage:x=>workerMessages.push(x)},pushManager:{getSubscription:async()=>({endpoint:'fixture'})}};
 const sandbox={window:w,Notification,navigator:{serviceWorker:{ready:Promise.resolve(reg)}},localStorage:{getItem:()=>JSON.stringify(stored),setItem:(_,s)=>stored=JSON.parse(s)},fetch:async(path)=>{assert.equal(path,'/api/push/selection');requests++;return {ok:true,json:async()=>({sent:1,approvedCount:1})};}};
 vm.runInNewContext(fs.readFileSync('push_manager.js','utf8'),sandbox);
 const flow={direction:'LONG',groups:[{scope:'XAU/USD',candidates:[{isin:'fixture'}]}],gateReasons:[]};
 assert.equal(await w.BobPush.updateSelection({},flow),false);assert.equal(requests,0);
 w.BobPush.set('general',true);
 assert(await w.BobPush.updateSelection({},flow));assert.equal(requests,1);
 assert.equal(await w.BobPush.updateSelection({},flow),false);assert.equal(requests,1);
 w.BobPush.set('general',false);
 assert.equal(await w.BobPush.updateSelection({},flow),false);assert.equal(requests,1);
 w.BobPush.set('general',true);
 let release;reg.pushManager.getSubscription=()=>new Promise(resolve=>release=resolve);
 const pending=w.BobPush.updateSelection({},flow);await new Promise(setImmediate);
 w.BobPush.set('general',false);release({endpoint:'fixture'});
 assert.equal(await pending,false);assert.equal(requests,1);
 assert(workerMessages.some(x=>x.general===false));
 console.log('Product push switch: off, on, duplicate, and off during preparation passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

(async()=>{
 const handlers={},cacheData=new Map();let displayed=0,closed=0;
 const sw={addEventListener:(k,f)=>handlers[k]=f,registration:{showNotification:async()=>displayed++,getNotifications:async()=>[{close:()=>closed++}]}};
 const cache={match:async k=>cacheData.get(k)?.clone(),put:async(k,v)=>cacheData.set(k,v)};
 vm.runInNewContext(fs.readFileSync('sw.js','utf8'),{self:sw,caches:{open:async()=>cache},Response,Date});
 async function dispatch(type,data){let done;handlers[type]({data:type==='push'?{json:()=>data}:data,waitUntil:p=>done=p});await done;}
 const message={title:'fixture',data:{kind:'product-approved',expiresAt:Date.now()+20000}};
 await dispatch('push',message);assert.equal(displayed,0);
 await dispatch('message',{type:'BOB_PUSH_PREFERENCES',general:true});
 await dispatch('push',message);assert.equal(displayed,1);
 await dispatch('push',{...message,data:{...message.data,expiresAt:Date.now()-1}});assert.equal(displayed,1);
 await dispatch('message',{type:'BOB_PUSH_PREFERENCES',general:false});
 await dispatch('push',message);assert.equal(displayed,1);assert.equal(closed,1);
 await dispatch('message',{type:'BOB_PUSH_PREFERENCES',general:true,trade:true,activeTrade:true});
 await dispatch('push',{data:{kind:'trade'}});assert.equal(displayed,2);
 await dispatch('message',{type:'BOB_PUSH_PREFERENCES',general:true,trade:true,activeTrade:false});
 await dispatch('push',{data:{kind:'trade'}});assert.equal(displayed,2);
 await dispatch('push',{data:{kind:'trade',test:true}});assert.equal(displayed,3);
 console.log('Service worker blocks queued products after switch-off and expired recommendations');
})().catch(e=>{console.error(e);process.exitCode=1;});
