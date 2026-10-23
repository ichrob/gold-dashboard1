'use strict';
// A voice deep link must show the TOP of Gold-Hebelprodukte, even if Android's
// browser restored the last-product scroll position. Do not fight user scroll.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('  function stabilizeGoldDeepLinkScroll(target){');
const end=html.indexOf('  function openRequestedGoldProducts(){',start);
assert(start>=0&&end>start,'Explicit Gold voice landing stabilization exists');
assert.match(html.slice(end,end+850),/stabilizeGoldDeepLinkScroll\(target\|\|summary\)/);
function fixture(search,hash,hidden=false){
 const callbacks=[],timeouts=[],events={};
 const history={scrollRestoration:'auto'};
 const panel={hidden};
 const calls=[];
 const target={isConnected:true,scrollIntoView:opts=>calls.push(opts)};
 const document={
  addEventListener:(type,callback)=>{(events[type]??=[]).push(callback)},
  removeEventListener:(type,callback)=>{events[type]=(events[type]||[]).filter(f=>f!==callback)}
 };
 const context={URLSearchParams,location:{search,hash},history,
  panels:{products:panel},document,
  requestAnimationFrame:callback=>{callbacks.push(callback)},
  setTimeout:(callback)=>{const item={callback,cancelled:false};timeouts.push(item);return item},
  clearTimeout:(item)=>{item.cancelled=true}
 };
 const fn=vm.runInNewContext(html.slice(start,end)+'\nstabilizeGoldDeepLinkScroll',context);
 return {fn,target,calls,history,events,panel,callbacks,timeouts,
  frames:()=>{while(callbacks.length)callbacks.shift()();},
  delayed:()=>{for(const t of [...timeouts])if(!t.cancelled)t.callback()},
  gesture:type=>{for(const f of [...(events[type]||[])])f()},
 };
}
{
 const v=fixture('?view=products&bobvisit=123','#products');
 assert.equal(v.fn(v.target),true);
 assert.equal(v.history.scrollRestoration,'manual');
 v.frames();
 v.delayed();
 assert(v.calls.length>=3,'Original list position re-anchored after layout settling');
 assert(v.calls.every(x=>x.block==='start'&&x.behavior==='instant'));
 assert.equal(v.timeouts.every(t=>t.cancelled),true,'Timers stop after entry settles');
}
{
 const v=fixture('?view=products','#products');
 v.fn(v.target);v.frames();
 const previous=v.calls.length;
 v.gesture('touchstart');v.delayed();
 assert.equal(v.calls.length,previous,'An active touch must cancel delayed scroll jumps');
}
{
 const v=fixture('?view=products','#products',true);
 v.fn(v.target);v.frames();v.delayed();
 assert.equal(v.calls.length,0,'Hidden product panel is never forcibly scrolled');
}
for(const [search,hash] of [['?view=overview','#overview'],
 ['?view=products','#simulation'],['','#products']]){
 const v=fixture(search,hash);
 assert.equal(v.fn(v.target),false);
 v.frames();v.delayed();
 assert.equal(v.calls.length,0);
 assert.equal(v.history.scrollRestoration,'auto');
}
console.log('Gold deep-link: align start after restore; no user-scroll override; normal views unchanged');
