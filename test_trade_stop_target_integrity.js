'use strict';
// Run Bob's actual 15m stop-target module without a UI, broker or network.
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('node:vm');
const html=fs.readFileSync('Bob.html','utf8');
const source=html.slice(html.indexOf('function intradayRiskData('),
                        html.indexOf('function intradayEntryContext('));
assert(source.includes('function continuedTradePlan('));
const NOW=Date.parse('2026-10-16T12:00:00Z'),STEP=900000;
function fixture(){
 const bars=Array.from({length:50},(_,i)=>{
  const x=4140+i*.4;
  return {openTime:NOW-(50-i)*STEP,open:x,high:x+1,low:x-1,close:x,
   isOpen:false,instrument:'XAU/USD',source:'biquote'};
 });
 return {spots:{xaus:4175,spot_price_as_of:new Date(NOW-15000).toISOString(),
  is_genuine_xauusd_spot:true,spot_error:null},
  history:{bars_by_tf:{'15m':bars}}};
}
let seenTargets=0;
const env={Date,Number,Math,liveBundleCache:null,
 atr:rows=>2,
 stopModel:(dir,price)=>({stop:dir==='LONG'?price-9:price+9}),
 targetModel:(dir,price)=>{seenTargets++;return {target:dir==='LONG'?price+30:price-30}}};
vm.createContext(env);vm.runInContext(source,env);
const compute=(t,b)=>env.continuedTradePlan(t,b,NOW);
const valid=fixture();
assert(env.intradayRiskData(valid,NOW).available);
for(const dir of ['LONG','SHORT']){
 const trade={active:true,dir,tradeId:'safe-1',stop:dir==='LONG'?4140:4200,
  target:dir==='LONG'?4270:4050};
 const plan=compute(trade,valid);
 assert(plan);
 assert.equal(plan.target,trade.target,'Target may only move after an explicit confirmed checkpoint');
 assert.equal(plan.targetSource,'confirmed-trade-plan');
 assert.equal(seenTargets,0,'No silent tick-by-tick target recomputation');
 assert(dir==='LONG'?plan.stop>=trade.stop:plan.stop<=trade.stop);
 const alternative={...valid,spots:{...valid.spots,xaus:4195}};
 assert.equal(compute(trade,alternative).target,trade.target);
}
const unconfirmed=compute({active:true,dir:'LONG',stop:4140,tradeId:'new'},valid);
assert(unconfirmed&&unconfirmed.targetSource==='provisional-only');
assert.equal(seenTargets,1);
const invalid=(mutate)=>{
 const b=structuredClone(valid);mutate(b);return b;
};
const stale=invalid(b=>{b.spots.spot_price_as_of=new Date(NOW-100000).toISOString();});
assert.equal(compute({active:true,dir:'LONG',stop:4140,target:4260},stale),null);
assert.equal(compute({active:true,dir:'LONG',stop:4140,target:4260},
 invalid(b=>{b.spots.is_genuine_xauusd_spot=false;})),null);
assert.equal(compute({active:true,dir:'LONG',stop:4140,target:4260},
 invalid(b=>{b.spots.spot_error='unavailable';})),null);
assert.equal(compute({active:true,dir:'LONG',stop:4140,target:4260},
 invalid(b=>{b.spots.spot_price_as_of=new Date(NOW+5000).toISOString();})),null);
const gap=invalid(b=>{b.history.bars_by_tf['15m'][30].openTime-=STEP;});
assert.equal(env.intradayRiskData(gap,NOW).available,false,'40-bar structure must not bridge missing 15m bar');
assert.equal(compute({active:true,dir:'LONG',stop:4140,target:4260},gap),null);
const estimated=invalid(b=>{b.history.bars_by_tf['15m'][35].estimated=true;});
assert.equal(env.intradayRiskData(estimated,NOW).available,false);
const wrongBasis=invalid(b=>{b.history.bars_by_tf['15m'][35].instrument='GC=F';});
assert.equal(env.intradayRiskData(wrongBasis,NOW).available,false);
const outdated=invalid(b=>{b.history.bars_by_tf['15m'].forEach(v=>v.openTime-=4*STEP);});
assert.equal(env.intradayRiskData(outdated,NOW).available,false);
console.log('15m integrity, stale/synthetic inputs, locked target and tightening-only stop passed');
