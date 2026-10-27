'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};const env={window};vm.createContext(env);
vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),env);
vm.runInContext(fs.readFileSync('bob_stop_assistant.js','utf8'),env);
const b=window.BobDegiro,now=Date.parse('2026-10-27T10:00:00Z'),at=new Date(now-10000).toISOString();
for(const direction of ['LONG','SHORT'])for(const currency of ['EUR','CHF']){
 const sign=direction==='LONG'?1:-1,ko=4200-sign*300;
 const q={isin:'DE000FG14AV8',found:true,productVerified:true,currency,source:'fixture',bid:20,ask:20.1,bidAt:at,askAt:at,isExecutableQuote:true,
 metadata:{status:1,currency},productModel:{isin:'DE000FG14AV8',verifiedSimpleTurbo:true,underlying:'XAU/USD',direction,ko,strike:ko,ratio:.1}};
 const p={isin:q.isin,isinConfirmed:true,productDirection:direction,ko,quote:q};
 const market={available:true,direction,entry:4200,stop:4200-sign*30,target:4200+sign*60,atr:10,at,spots:{[currency==='EUR'?'usd_eur_meta':'usd_chf_meta']:{rate:.9,fetchedAt:at}}};
 const before=JSON.stringify({p,market}),r=b.productRiskPreview(p,market,now);
 assert(r.available);assert.equal(r.currency,currency);assert(Math.abs(r.stop-17.3)<1e-8);assert(Math.abs(r.target-25.4)<1e-8);assert(Math.abs(r.lossPerUnit-2.8)<1e-8);
 assert.equal(r.automaticOrder,false);assert.equal(r.tradeable,false);assert.equal(JSON.stringify({p,market}),before);
 for(const bad of [{...market,available:false},{...market,entrySuitable:false},{...market,stop:ko+sign*20},{...market,direction:'NEUTRAL'},{...market,spots:{}}])assert(!b.productRiskPreview(p,bad,now).available);
 for(const bad of [{...p,isinConfirmed:false},{...p,ko:4200-sign*20},{...p,quote:{...q,isin:'OTHER'}},{...p,quote:{...q,productModel:{...q.productModel,underlying:'GC=F'}}},{...p,quote:{...q,productModel:{...q.productModel,verifiedSimpleTurbo:false}}}])assert(!b.productRiskPreview(bad,market,now).available);
 assert(!b.productRiskPreview(p,market,now+100000).available);
 assert(b.productRiskPreviewText(p,market,now).includes('Gesamtverlust erst mit tatsächlichem Kaufkurs'));
}
console.log('Product risk preview: shared plan, LONG/SHORT, EUR/CHF, KO buffer, identity, stale FX/quotes, immutability passed');

const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('function productMarketPlan('),end=html.indexOf('function continuedTradePlan(',start);
const fixed={available:true,atr:10,bars:[]},calls=[];
const planEnv={liveBundleCache:{spots:{xaus:4200,is_genuine_xauusd_spot:true,spot_price_as_of:at}},
 intradayRiskData:()=>fixed,$:id=>({value:id==='trailAtr'?'1.8':'2.5'}),
 stopModel:(...args)=>{calls.push(args);return {stop:4170,reason:'shared'};},
 targetModel:(...args)=>{calls.push(args);return {target:4260,entrySuitable:true};}};
vm.createContext(planEnv);vm.runInContext(html.slice(start,end),planEnv);
assert(planEnv.productMarketPlan('LONG',now).available);
assert.equal(calls[0][3],1.8);assert.equal(calls[1][3],2.5);
assert.strictEqual(calls[0][4],fixed);assert.strictEqual(calls[1][4],fixed);
for(const stamp of [new Date(now-60001).toISOString(),new Date(now+1).toISOString(),'2026-10-27T10:00:00']){
 planEnv.liveBundleCache.spots.spot_price_as_of=stamp;
 assert.equal(planEnv.productMarketPlan('LONG',now).available,false);
}
console.log('Market preview uses existing stop/target engines, user parameters and same risk snapshot; rejects stale/future/ambiguous clocks');
