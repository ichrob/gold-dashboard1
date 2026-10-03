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
