'use strict';
const assert=require('node:assert/strict');
global.BobTradeProduct=require('./trade_product.js');
const stop=require('./bob_stop_assistant.js');

const now=Date.parse('2026-11-17T15:00:00Z');
const time=new Date(now).toISOString();
const product={
 isin:'DE000FB0A490',direction:'SHORT',currency:'EUR',
 simpleSpotTurbo:true,referenceConfirmed:true,
 bid:20,goldReference:4000,fxReference:0.9,fxScenario:0.9,
 ratio:0.1,strike:4151.07,ko:4151.07,entry:20,quantity:7
};
const spots={
 is_genuine_xauusd_spot:true,spot_price_as_of:time,xaus:4005,
 usd_eur_meta:{rate:0.9,fetchedAt:time}
};
const draft=stop.simulationDraft({product,stopGold:4010,targetGold:3900,spots,now});
assert.equal(draft.available,true,JSON.stringify(draft));
assert.equal(draft.raw,'BOB-STOP/1|DE000FB0A490|EUR|7|19.10|'+now);
assert.equal(draft.stopEur,19.10);
assert.equal(draft.automaticOrder,false);
assert.equal(draft.degiroExecutable,false);

const fail=(changes)=>assert.equal(stop.simulationDraft({
 product:{...product,...(changes.product||{})},
 stopGold:changes.stopGold??4010,targetGold:changes.targetGold??3900,
 spots:changes.spots||spots,now
}).available,false);
fail({spots:{...spots,is_genuine_xauusd_spot:false}});
fail({spots:{...spots,usd_eur_meta:{rate:0.9,fetchedAt:new Date(now-100000).toISOString()}}});
fail({spots:{...spots,spot_price_as_of:new Date(now-90000).toISOString()}});
fail({product:{currency:'CHF'}});
fail({product:{quantity:0}});
fail({product:{quantity:1.5}});
fail({product:{isin:'NOT-AN-ISIN'}});
fail({stopGold:4200});
assert.equal(stop.evaluate({product,stopGold:4010,targetGold:3900,spots,now}).automaticOrder,false);
console.log('Bob model-to-offline-simulation: real calculated EUR product stop; stale/CHF/invalid/KO fail closed; no broker order.');
