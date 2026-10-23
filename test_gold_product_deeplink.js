'use strict';
// Lightweight regression of the exact mobile deep-link helper from Bob.html.
const fs=require('node:fs');
const assert=require('node:assert/strict');
const html=fs.readFileSync('Bob.html','utf8');
const dg=fs.readFileSync('degiro_assistant.js','utf8');
const first=html.indexOf('  let goldDeepLinkRevealed=false;');
const last=html.indexOf("  window.addEventListener('hashchange',()=>",first);
const alternativeEnd=html.indexOf("  window.addEventListener('hashchange',()=>{",first);
const end=last>=0?last:alternativeEnd;
assert(first>0&&end>first,'Mobile direct-product helper must exist');
const extracted=html.slice(first,end);
assert(extracted.includes("getElementById('dgSavedProductsSummary')"));
assert(html.includes('  openRequestedGoldProducts();'),'Initial page must open the requested accordion');
assert(html.includes("   openRequestedGoldProducts();"),'Hashchange must support opening the target');
assert(dg.includes('id="dgSavedProductsSummary"')&&dg.includes('Gold-Hebelprodukte'),
       'Must target an existing Gold-Hebelprodukte summary');
function fixture({search='?view=products',hash='#products',hidden=false,hasSummary=true,inside=true}={}){
  let scrolls=0;
  const details={open:false};
  const summary={isConnected:true,closest:tag=>tag==='details'?details:null,
    scrollIntoView:opts=>{assert.equal(opts.block,'start');scrolls++;}};
  const doc={getElementById:id=>id==='dgSavedProductsSummary'&&hasSummary?summary:null,
    addEventListener:()=>{},removeEventListener:()=>{}};
  const panel={hidden,contains:el=>inside&&el===details};
  const location={search,hash};
  const history={scrollRestoration:'auto'};
  const {revealGoldLeveragedProducts,openRequestedGoldProducts}=new Function(
      'document','panels','location','requestAnimationFrame','URLSearchParams',
      'history','setTimeout','clearTimeout',
      extracted+'\nreturn {revealGoldLeveragedProducts,openRequestedGoldProducts};'
    )(doc,{products:panel},location,fn=>fn(),URLSearchParams,history,()=>1,()=>{});
  // Re-aligning the start in two layout frames is intentional, not duplicate navigation.
  return {details,summary,get scrolls(){return scrolls;},
    revealGoldLeveragedProducts,openRequestedGoldProducts,panel,doc};
}
const direct=fixture();
assert.equal(direct.openRequestedGoldProducts(),true);
assert.equal(direct.details.open,true,'Voice target must expand real Gold-Hebelprodukte details');
assert(direct.scrolls>=1,'Voice target should be brought into view after layout frames');
assert.equal(direct.openRequestedGoldProducts(),false,'Must not loop or toggle closed');
assert.equal(direct.details.open,true);
assert.equal(fixture({search:''}).openRequestedGoldProducts(),false,
             'Manual navigation must preserve old collapsed state');
assert.equal(fixture({search:'?view=trade'}).openRequestedGoldProducts(),false);
assert.equal(fixture({hash:'#trade'}).openRequestedGoldProducts(),false);
assert.equal(fixture({hidden:true}).openRequestedGoldProducts(),false);
assert.equal(fixture({hasSummary:false}).openRequestedGoldProducts(),false);
assert.equal(fixture({inside:false}).openRequestedGoldProducts(),false,
             'Never open a similarly named element in a different section');
console.log('Bob voice Gold-Hebelprodukte direct-link: opens real accordion, scrolls, preserves manual navigation.');
