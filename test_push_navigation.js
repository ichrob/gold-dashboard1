'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
async function click(windows,url,action='') {
 const handlers={},opened=[],navigated=[],focused=[];
 const self={location:{origin:'https://bob.example'},addEventListener:(k,v)=>handlers[k]=v};
 const clients={matchAll:async()=>windows.map(path=>({url:'https://bob.example'+path,
  navigate:async target=>{navigated.push(target);return {focus:async()=>focused.push(path)};},
  focus:async()=>focused.push(path)})),openWindow:async target=>opened.push(target)};
 vm.runInNewContext(fs.readFileSync('sw.js','utf8'),{self,clients,URL,Date,Promise,Number,String,JSON,Boolean,console});
 let wait;
 handlers.notificationclick({action,notification:{data:{url},close(){}},waitUntil:p=>wait=p});
 await wait;return {opened,navigated,focused};
}
(async()=>{
 assert.deepEqual((await click(['/zentrale/'],'/#products')).opened,['/#products']);
 assert.deepEqual((await click(['/zentrale/','/'],'/#trade')).navigated,['/#trade']);
 assert.deepEqual((await click(['/'],'/#risk')).focused,['/']);
 assert.deepEqual((await click([],'https://foreign.example/')).opened,['/']);
 assert.deepEqual((await click([],'/#trade','receipt-confirm')).opened,[]);
 console.log('Push navigation: passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
