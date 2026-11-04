'use strict';
const assert=require('node:assert/strict');
const m=require('./manual_ranking_order.js');
const now=Date.parse('2026-11-03T12:00:00Z');
const iso=ms=>new Date(ms).toISOString();
const at=iso(now-30000);
const candidate={isin:'DE000FG4JXV7',direction:'SHORT'};
const product={isin:candidate.isin,productDirection:'SHORT',isinConfirmed:true};
const quote={isin:candidate.isin,currency:'EUR',ask:20,bid:19.9,at,askAt:at,kind:'issuer',source:'Originalanbieter'};
const stopPlan={available:true,currency:'EUR',stop:18.5,referenceAt:at};
function test(extra={}){
 return m.evaluate({candidate,product,quote,stopPlan,fx:{available:true,rate:1,note:'Test'},budgetCHF:1000,riskCHF:100,feesCHF:8,now,direction:'SHORT',...extra});
}
let x=test();
assert.equal(x.available,true);
assert.equal(x.quantity,49);
assert.equal(x.totalCHF,988);
assert.equal(x.lossCHF,81.5);
assert.equal(x.entry,20);assert.equal(x.stop,18.5);
assert.equal(test({riskCHF:50}).quantity,28);
assert.equal(test({budgetCHF:30,riskCHF:100,feesCHF:8}).quantity,1);
assert.equal(test({direction:'LONG'}).available,false);
assert.equal(test({product:{...product,isin:'DE000FG8NHQ3'}}).available,false);
assert.equal(test({quote:{...quote,askAt:iso(now-91000)}}).available,false);
assert.equal(test({quote:{...quote,askAt:iso(now-70000)}}).available,false); // clocks > 30s apart
assert.equal(test({quote:{...quote,ask:19.5,bid:20}}).available,false);
assert.equal(test({quote:{...quote,kind:'calculated'}}).available,false);
assert.equal(test({quote:{...quote,at:'undated'}}).available,false);
assert.equal(test({stopPlan:{...stopPlan,stop:21}}).available,false);
assert.equal(test({stopPlan:{...stopPlan,available:false}}).available,false);
assert.equal(test({fx:{available:false,reason:'stale'}}).available,false);
assert.equal(test({feesCHF:NaN}).available,false);
assert.equal(test({feesCHF:0}).available,true);
assert.equal(test({riskCHF:8}).available,false);
assert.equal(test({budgetCHF:0}).available,false);
const fx=m.readChfFx({usd_chf_meta:{rate:0.8,fetchedAt:at},
 usd_eur_meta:{rate:0.9,fetchedAt:at}},now,'EUR');
assert.equal(fx.available,true);assert.ok(Math.abs(fx.rate-(0.8/0.9))<1e-12);
assert.equal(m.readChfFx({usd_chf_meta:{rate:0.8,fetchedAt:at},
 usd_eur_meta:{rate:0.9,fetchedAt:iso(now-91000)}},now,'EUR').available,false);
assert.equal(m.readChfFx({},now,'CHF').rate,1);
assert.equal(m.readChfFx({},now,'USD').available,false);
assert.equal(test({quote:{...quote,at:iso(now+2000),askAt:iso(now+2000)}}).available,false);
console.log('manual Top-3 order figures: strict quote, source, FX and risk tests passed');
