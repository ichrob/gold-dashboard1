"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
global.BobTradeProduct=require('./trade_product.js');
const curve=require('./product_trade_curve.js');
const NOW=Date.parse('2026-10-16T08:00:00Z');
const at=(delta=0)=>new Date(NOW-delta).toISOString();
const product={isin:'DE000FG4JXV7',direction:'SHORT',currency:'EUR',simpleSpotTurbo:true,
 referenceConfirmed:true,bid:20,goldReference:4200,fxReference:.9,fxScenario:.9,
 ratio:.1,strike:4460,ko:4460,entry:20,quantity:5,
 source:'DEGIRO screenshot · paired anchor',referenceAt:at(60000)};
const trade={active:true,test:false,tradeId:'safe-trade-1',product};
const spots={xaus:4210,spot_price_as_of:at(15000),is_genuine_xauusd_spot:true,spot_error:null,
 usd_eur_meta:{rate:.9,fetchedAt:at(18000),source:'FX'}};
const input={trade,spots,stopGold:4240,targetGold:4180};
const model=curve.assess(input,NOW);
assert.equal(model.available,true);
assert.equal(model.kind,'model');
assert.equal(model.degiroExecutable,false);
assert.equal(model.automaticOrder,false);
assert.equal(model.price,19.1);
assert.equal(model.stop,16.4);
assert.equal(model.target,21.8);
assert.equal(model.stage,'observing');
assert.equal(model.ko,4460);
assert.equal(model.currency,'EUR');

const quote={isin:product.isin,currency:'EUR',kind:'issuer',bid:19.15,ask:19.17,
 at:at(11000),askAt:at(12000),source:'SG original quoted time',error:false,delayed:false};
const issuer=curve.assess({...input,quote},NOW);
assert.equal(issuer.kind,'issuer');
assert.equal(issuer.price,19.15);
assert.equal(issuer.sourceAt,Date.parse(quote.at));
const reference=curve.assess({...input,quote:{...quote,kind:'research',bid:19.1}},NOW);
assert.equal(reference.kind,'research');
assert.equal(reference.degiroExecutable,false);
assert.equal(curve.assess({...input,quote:{...quote,at:at(100000),askAt:at(100000)}},NOW).kind,'model');
assert.equal(curve.assess({...input,quote:{...quote,isin:'DE000FC1CHB7'}},NOW).kind,'model');
assert.equal(curve.assess({...input,quote:{...quote,currency:'CHF'}},NOW).kind,'model');
assert.equal(curve.assess({...input,quote:{...quote,kind:'model'}},NOW).kind,'model');
assert.equal(curve.assess({...input,quote:{...quote,askAt:null}},NOW).kind,'model');
assert.equal(curve.assess({...input,quote:{...quote,error:true}},NOW).kind,'model');
assert.equal(curve.assess({...input,quote:{...quote,bid:16.3,ask:16.32}},NOW).stage,'stop');
assert.equal(curve.assess({...input,quote:{...quote,bid:22,ask:22.05}},NOW).stage,'target');
const near=curve.assess({...input,spots:{...spots,xaus:4390}},NOW);
assert(near.koDistancePct<2);
assert(near.action.includes('KO-Abstand'));
const knocked=curve.assess({...input,spots:{...spots,xaus:4460}},NOW);
assert.equal(knocked.stage,'ko');
assert.equal(knocked.available,false);
const noGold=curve.assess({...input,quote,spots:{...spots,spot_price_as_of:at(100000)}},NOW);
assert.equal(noGold.kind,'issuer');
assert.equal(noGold.stop,null,'Do not compare a fresh provider quote to model levels using stale Gold');
assert.equal(noGold.stage,'levels-unavailable');
const stale=curve.assess({...input,quote:null,spots:{...spots,spot_price_as_of:at(100000)}},NOW);
assert.equal(stale.available,false);
assert.equal(stale.stage,'waiting');
const noFx=curve.assess({...input,quote:null,spots:{...spots,usd_eur_meta:{rate:.9,fetchedAt:at(120000)}}},NOW);
assert.equal(noFx.available,false);
assert.equal(noFx.stop,null);
assert.equal(curve.assess({...input,trade:{...trade,test:true}},NOW).available,false);
assert.equal(curve.assess({...input,trade:{...trade,product:{...product,currency:'GBP'}}},NOW).available,false);
const chfProduct={...product,currency:'CHF',fxReference:.8,fxScenario:.8};
const chf=curve.assess({...input,trade:{...trade,product:chfProduct},
 spots:{...spots,usd_chf_meta:{rate:.8,fetchedAt:at(10000)}}},NOW);
assert.equal(chf.currency,'CHF');
assert.equal(chf.kind,'model');

let history=curve.addObservation(null,issuer,NOW);
assert.equal(history.rows.length,1);
assert.equal(history.rows[0].at,NOW);
assert.equal(history.rows[0].sourceAt,Date.parse(quote.at),'Never replace original issuer time with capture time');
assert.equal(curve.addObservation(history,issuer,NOW+35000).rows.length,1,'Same issuer source time is not new history');
history=curve.addObservation(history,{...model,sourceAt:Date.parse(at(-25000))},NOW+30000);
assert.equal(history.rows.length,2);
assert.equal(history.rows[1].kind,'model');
history=curve.addObservation(history,stale,NOW+60000);
assert.equal(history.rows.length,2,'No synthetic points in source outages');
assert.equal(curve.addObservation(history,{available:false,tradeKey:null},NOW+61000).rows.length,2,'Archive survives closing trade');
const next=curve.addObservation(history,{...issuer,tradeKey:'DE000ANOTHER|trade2'},NOW+60000);
assert.equal(next.rows.length,1,'Never mix different trades');

const rise=[12,12.3,12.15,12.7,13.1,13.5].map((price,i)=>({price,at:NOW+i*30000}));
const upFib=curve.fibonacci(rise);
assert(upFib&&upFib.rising,'Fibonacci must use observed low-to-high product prices');
assert.equal(upFib.levels[0].price,13.5);
assert.equal(upFib.levels[3].price,12.75);
assert.equal(upFib.levels.at(-1).price,12);
const downFib=curve.fibonacci([...rise].reverse().map((row,i)=>({...row,at:NOW+i*30000})));
assert(downFib&&!downFib.rising,'High-to-low swing must reverse retracement direction');
assert.equal(downFib.levels[0].price,12);
assert.equal(downFib.levels.at(-1).price,13.5);
assert.equal(curve.fibonacci(rise.slice(0,2)),null,'Two chart points must never imply a price swing');
assert.equal(curve.fibonacci(rise.map((v,i)=>({...v,at:NOW+i*1000}))),null,'Require a real observation period');
assert.equal(curve.fibonacci(rise.map(v=>({...v,price:12}))),null,'Never draw levels from flat prices');

const html=fs.readFileSync('Bob.html','utf8'),server=fs.readFileSync('server.py','utf8');
assert(html.includes('<script src="/product_trade_curve.js?'));
assert(html.includes('20261016-fib-v2'), 'Versioned script URL refreshes mobile cache');
assert(html.includes("window.BobProductCurve?.mount(curveRoot)"));
assert(html.includes("window.BobProductCurve?.update(window.BobTradeSync?.chartData?.())"));
assert(html.includes('chartData(){'));
assert(server.includes('if path == "/product_trade_curve.js":'));
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
for(const item of scripts){
 if(item[1].includes('window.BobTradeSync={')||item[1].includes('function initMobile(){'))
  new vm.Script(item[1],{filename:'Bob.html-inline'});
}
console.log('Product curve: verified quote/model, CHF, stop/target, KO, provenance, bounded observation and syntax passed');
