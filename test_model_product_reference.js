'use strict';
const assert=require('node:assert/strict');
const {calculate}=require('./model_product_reference.js');
const now=Date.parse('2026-11-16T14:00:00Z'), at=new Date(now-10000).toISOString();
const ref=new Date(now-180000).toISOString();
function fixture(direction='LONG'){
 const sign=direction==='LONG'?1:-1,ko=direction==='LONG'?3900:4500;
 const plan={available:true,direction,entry:4200,stop:4200-sign*30,
   target:4200+sign*60,atr:10,at};
 const quote={isin:'DE000FG14AV8',currency:'EUR',productVerified:true,
   metadata:{status:1,underlyingType:'SPOT',direction,currency:'EUR'},
   productModel:{isin:'DE000FG14AV8',verifiedSimpleTurbo:true,underlying:'XAU/USD',
     direction,ko,strike:ko,ratio:.1,tradingEndAt:new Date(now+3600000).toISOString()},
   calculatedProduct:{kind:'calculated-turbo',available:true,currency:'EUR',direction,
     bidEur:20,askEur:20.1,goldUsd:4200,usdEur:.9,ratio:.1,strikeUsd:ko,
     priceAt:at,goldAt:at,fxDataAt:at,fxEffectiveAt:at,calculatedAt:at,
     referenceAt:ref,validation:{ready:false}}};
 const spots={xaus:4200,is_genuine_xauusd_spot:true,spot_price_as_of:at,
   usd_eur_meta:{rate:.9,fetchedAt:at}};
 return {quote,plan,spots,now};
}
for(const direction of ['LONG','SHORT']){
 const x=fixture(direction),copy=JSON.stringify(x),out=calculate(x);
 assert.equal(out.available,true,direction+': '+out.reason);
 assert.equal(out.mode,'anchored-estimate');
 assert.equal(out.simulationPlanningUsable,true);
 assert.equal(out.simulationFillAllowed,false);
 assert.equal(out.executable,false);
 assert.equal(out.entryApproved,false);
 assert.equal(out.copyAllowed,false);
 assert.equal(out.modelEntry,20.1);
 assert(Math.abs(out.modelStop-17.3)<1e-8);
 assert(Math.abs(out.modelTarget-25.4)<1e-8);
 assert.equal(JSON.stringify(x),copy);
 const unsupported=structuredClone(x);delete unsupported.quote.calculatedProduct;
 const contract=calculate(unsupported);
 assert.equal(contract.available,true);
 assert.equal(contract.mode,'intrinsic-only');
 assert.equal(contract.simulationFillAllowed,false);
 assert.equal(contract.modelEntry,27);
 assert.equal(contract.modelStop,24.3);
 assert.equal(contract.modelTarget,32.4);
 const stopped=structuredClone(x);stopped.quote.productModel.verifiedSimpleTurbo=false;
 assert.equal(calculate(stopped).available,false);
 const stale=structuredClone(x);stale.spots.spot_price_as_of=new Date(now-61000).toISOString();
 assert.equal(calculate(stale).available,false);
 const fxStale=structuredClone(x);fxStale.spots.usd_eur_meta.fetchedAt=new Date(now-61000).toISOString();
 assert.equal(calculate(fxStale).available,false);
 const ko=structuredClone(x);ko.plan.stop=ko.quote.productModel.ko;
 assert.equal(calculate(ko).available,false);
 const expired=structuredClone(x);expired.quote.productModel.tradingEndAt=new Date(now-1000).toISOString();
 assert.equal(calculate(expired).available,false);
 const foreign=structuredClone(x);foreign.quote.currency='CHF';foreign.quote.metadata.currency='CHF';
 assert.equal(calculate(foreign).available,false);
 const terminated=structuredClone(x);terminated.quote.state='terminated';
 assert.equal(calculate(terminated).available,false);
 const oldProjection=structuredClone(x);
 oldProjection.quote.calculatedProduct.referenceAt=new Date(now-600000).toISOString();
 assert.equal(calculate(oldProjection).mode,'intrinsic-only',
  'unvalidated anchor older than five minutes is not an accepted price');
 oldProjection.quote.calculatedProduct.validation.ready=true;
 assert.equal(calculate(oldProjection).mode,'anchored-estimate',
  'validated anchored estimates can use the existing 30m product bound');
 const changedModel=structuredClone(x);changedModel.quote.calculatedProduct.strikeUsd+=10;
 assert.equal(calculate(changedModel).mode,'intrinsic-only',
  'changed terms invalidate any previous original-quote anchor');
 const untrusted=structuredClone(x);untrusted.spots.is_genuine_xauusd_spot=false;
 assert.equal(calculate(untrusted).available,false);
}
console.log('Bounded EUR turbo model stop/target: LONG/SHORT, provenance, KO, stale, CHF, expiry, no model-order promotion passed');
