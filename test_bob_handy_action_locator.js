'use strict';
// Bob-Handy opens an explicitly chosen button immediately without pinning it
// over the bottom of the screen or moving its real event handler.
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('Bob.html','utf8');
const begin=html.indexOf('  // Bob-Handy action locator:');
const end=html.indexOf('  function show(key,focus=true){',begin);
assert(begin>=0&&end>begin,'Explicit stable-ID Bob-Handy action locator exists');
const code=html.slice(begin,end);
assert(code.includes("const handyActionTargets=Object.freeze({problems:'bobMobileHelpShare'})"));
assert(code.includes("target.scrollIntoView({behavior:'instant',block:'start'})"));
assert(code.includes("if(parent.tagName==='DETAILS')parent.open=true"));
assert(code.includes("document.addEventListener(gesture,cancel"));
assert(!code.includes('.click()')&&!code.includes('navigator.share')&&!code.includes('fetch('),
  'Finding a button cannot execute it or export information');
assert(!html.includes('bobPrimaryActionDock'), 'No action dock must remain');
assert(!html.includes('.bob-primary-action-dock'), 'No bottom-fixed action CSS must remain');
assert(!html.includes('showPinnedAction(key)'), 'No bottom-fixed action triggered on tab switches');
assert(html.includes('  stabilizeHandyActionEntry();\n  openRequestedGoldProducts();'),
  'Direct-entry alignment runs during page initialization');
assert(html.includes('   stabilizeHandyActionEntry();\n  });'),
  'Repeated explicit hash navigation can locate the action again');
function caseFor(search,hash,opts={}){
 const gestures={},callbacks=[],timeouts=[];
 let timerId=0;
 const calls=[];
 const panel={hidden:!!opts.hidden,tagName:'SECTION'};
 const disclosure={tagName:'DETAILS',open:false,parentElement:panel};
 const movedContainer={tagName:'DIV',parentElement:disclosure};
 const target={tagName:'BUTTON',isConnected:opts.connected!==false,parentElement:movedContainer,
  scrollIntoView:options=>calls.push(options)};
 const document={
  addEventListener:(kind,listener)=>{(gestures[kind]??=[]).push(listener)},
  removeEventListener:(kind,listener)=>{gestures[kind]=(gestures[kind]||[]).filter(x=>x!==listener)}
 };
 const history={scrollRestoration:'auto'};
 const context={URLSearchParams,location:{search,hash},panels:{problems:panel},document,history,
   byId:id=>id==='bobMobileHelpShare'?(opts.missing?null:target):null,
   requestAnimationFrame:f=>callbacks.push(f),
   setTimeout:(f,ms)=>{const t={id:++timerId,f,ms,cancelled:false};timeouts.push(t);return t},
   clearTimeout:t=>{t.cancelled=true}
 };
 vm.createContext(context);
 vm.runInContext(code+'\nglobalThis.locate=stabilizeHandyActionEntry;',context);
 return {run:()=>context.locate(),frames:()=>{while(callbacks.length)callbacks.shift()()},
   later:()=>{for(const t of [...timeouts])if(!t.cancelled)t.f()},
   gesture:kind=>{for(const f of [...(gestures[kind]||[])])f()},
   calls,disclosure,target,history,timeouts};
}
{
 const c=caseFor('?view=problems&bobvisit=500','#problems');
 assert.equal(c.run(),true);
 assert.equal(c.disclosure.open,true,'Redesigned collapsed card opens to show selected button');
 assert.equal(c.history.scrollRestoration,'manual');
 c.frames();c.later();
 assert(c.calls.length>=3,'Explicit entry handles slow Chrome restoration');
 assert(c.calls.every(x=>x.block==='start'&&x.behavior==='instant'));
 assert(c.timeouts.every(t=>t.cancelled),'Retries stop after layout settles');
}
{
 const c=caseFor('?view=problems','#problems');
 c.run();c.frames();
 const before=c.calls.length;
 c.gesture('touchstart');c.later();
 assert.equal(c.calls.length,before,'User manual scrolling cancels future jumps');
}
{
 const c=caseFor('?view=problems','#problems',{hidden:true});
 assert.equal(c.run(),false);
 c.frames();c.later();
 assert.equal(c.calls.length,0,'Hidden view never scrolls');
}
{
 const c=caseFor('?view=problems','#problems',{missing:true});
 assert.equal(c.run(),false,'Never pretend success if action ID was removed');
}
for(const [search,hash] of [
 ['?view=products','#problems'],['','#problems'],
 ['?view=problems','#overview'],['?view=problems&trade=true','#problems-wrong']
]){
 const c=caseFor(search,hash);
 assert.equal(c.run(),false,'Only matching allowlisted handoff may scroll');
 c.frames();c.later();
 assert.equal(c.calls.length,0);
 assert.equal(c.history.scrollRestoration,'auto');
}
console.log('Bob-Handy action locator: top-of-view jump, design reordering, collapsed cards, user-scroll cancel, no floating bar or auto-click passed');
