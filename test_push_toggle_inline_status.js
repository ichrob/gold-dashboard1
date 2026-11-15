'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('Bob.html','utf8');
const begin=html.indexOf('function pushToggleHint(kind,message,success=false){');
const end=html.indexOf('async function closeTrade(){',begin);
assert(begin>0&&end>begin);
for(const id of ['generalPushInlineStatus','tradePushInlineStatus']) {
 assert(html.includes('id="'+id+'" class="small" role="status" aria-live="polite" hidden'));
}
assert.equal((html.match(/id="generalPushBtn"/g)||[]).length,1);
const source=html.slice(begin,end);
function setup({permission='granted',registered=true,serverRegistered=true,
               registrationOK=true,syncOK=true}={}){
 const button=()=>({disabled:false,attributes:{},setAttribute(k,v){this.attributes[k]=v;},
                    removeAttribute(k){delete this.attributes[k];}});
 const elements={generalPushBtn:button(),tradePushBtn:button(),
   generalPushInlineStatus:{hidden:true,textContent:'',className:'small'},
   tradePushInlineStatus:{hidden:true,textContent:'',className:'small'},
   pushStatus:{textContent:''},bobTradePushSyncStatus:{textContent:''}};
 let writes=0,registrations=0;
 const context={window:{Notification:{}},Notification:{permission},
   pushState:{registered,serverRegistered,general:false,trade:false},
   $:key=>elements[key],renderPush(){},async syncPushPreferences(){return syncOK;},
   async registerNotifications(){
    registrations++;
    if(!registrationOK){elements.pushStatus.textContent='❌ Benachrichtigungen nicht freigegeben.';return false;}
    context.pushState={...context.pushState,registered:true,serverRegistered:true};
    return true;
   },
   BobPush:{set(kind,enabled){writes++;context.pushState={...context.pushState,[kind]:enabled};return context.pushState;}}
 };
 vm.createContext(context);
 vm.runInContext(source,context,{filename:'Bob-push-toggle.js'});
 return {context,elements,counts:()=>({writes,registrations})};
}
(async()=>{
 let t=setup({permission:'denied',registered:false,serverRegistered:false});
 await t.context.togglePush('general');
 assert.equal(t.context.pushState.general,false);
 assert.equal(t.counts().writes,0);
 assert.equal(t.elements.generalPushInlineStatus.hidden,false);
 assert.match(t.elements.generalPushInlineStatus.textContent,/blockiert/);
 assert.equal(t.elements.generalPushBtn.disabled,false);

 t=setup({permission:'default',registered:false,serverRegistered:false,registrationOK:false});
 await t.context.togglePush('general');
 assert.equal(t.context.pushState.general,false);
 assert.equal(t.counts().writes,0);
 assert.match(t.elements.generalPushInlineStatus.textContent,/nicht freigegeben/);

 t=setup({permission:'granted',registered:false,serverRegistered:false,registrationOK:false});
 await t.context.togglePush('general');
 assert.equal(t.context.pushState.general,false);
 assert.match(t.elements.generalPushInlineStatus.textContent,/nicht freigegeben/);

 t=setup({permission:'granted',registered:false,serverRegistered:false});
 await t.context.togglePush('general');
 assert.equal(t.counts().registrations,1);
 assert.equal(t.context.pushState.general,true);
 assert.match(t.elements.generalPushInlineStatus.textContent,/am Server bestätigt/);
 assert.equal(t.elements.generalPushBtn.disabled,false);
 await t.context.togglePush('general');
 assert.equal(t.context.pushState.general,false);
 assert.equal(t.counts().registrations,1);
 assert.match(t.elements.generalPushInlineStatus.textContent,/Aus.*Server bestätigt/);

 t=setup({permission:'granted',syncOK:false});
 await t.context.togglePush('general');
 assert.equal(t.context.pushState.general,true);
 assert.match(t.elements.generalPushInlineStatus.textContent,/Server hat dies nicht bestätigt/);
 assert.doesNotMatch(t.elements.generalPushInlineStatus.textContent,/am Server bestätigt/);

 t=setup({permission:'granted'});
 await t.context.togglePush('trade');
 assert.equal(t.context.pushState.trade,true);
 assert.equal(t.elements.tradePushInlineStatus.hidden,false);
 assert.equal(t.elements.generalPushInlineStatus.hidden,true);
 assert.match(t.elements.tradePushInlineStatus.textContent,/Trade-Warnungen/);

 t=setup({permission:'denied',registered:true,serverRegistered:true});
 t.context.pushState.general=true;
 await t.context.togglePush('general');
 assert.equal(t.context.pushState.general,false,'Disabling remains possible even when permission is revoked');
 console.log('Push toggle: denied, rejected, missing server registration, sync warning, success/off and direct accessible feedback OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
