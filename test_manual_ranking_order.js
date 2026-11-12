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



// Broker-screen stage: manually transcribed displayed price recalculates budget,
// quantity and stop risk, but never becomes an executable broker quote or fill.
const brokerDisplay={isin:candidate.isin,currency:'EUR',bid:20.2,ask:20.3,
 quoteAt:at,venue:'Societe Generale OTC',buyingPowerCHF:'900',
 fxRateCHF:'0.9',fxAt:at,tickSize:'0.01',lotSize:'1',
 orderType:'LIMIT',orderDuration:'DAY',confirmedByUser:true};
function brokerReview(overrides={},other={}){
 return m.reconcileBrokerDisplay({candidate,product,preliminary:test(),
  broker:{...brokerDisplay,...overrides},fx:{available:true,rate:1,note:'Marktreferenz'},
  budgetCHF:1000,riskCHF:100,feesCHF:8,now,direction:'SHORT',...other});
}
const brokerResult=brokerReview();
assert.equal(brokerResult.available,true);
assert.equal(brokerResult.entry,20.3);
assert.ok(Math.abs(brokerResult.stop-18.8)<1e-9);
assert.equal(brokerResult.quantity,48);
assert.ok(Math.abs(brokerResult.totalCHF-885)<0.05);
assert.ok(Math.abs(brokerResult.lossCHF-72.8)<0.01);
assert.equal(brokerResult.manualFieldsComplete,true);
assert.ok(Math.abs(brokerResult.stopShift-0.3)<1e-9);
assert.equal(brokerReview({quoteAt:iso(now-75000)}).manualFieldsComplete,false);
assert.equal(brokerResult.copyAllowed,false);
assert.equal(brokerResult.brokerExecutionVerified,false);
assert.equal(brokerResult.orderSubmitted,false);
assert.equal(brokerReview({confirmedByUser:false}).available,false);
assert.equal(brokerReview({isin:'DE000FG8NHQ3'}).available,false);
assert.equal(brokerReview({currency:'CHF'}).available,false);
assert.equal(brokerReview({quoteAt:'12.11.2026 14:01'}).available,false);
assert.equal(brokerReview({quoteAt:iso(now-91000)}).available,false);
assert.equal(brokerReview({quoteAt:iso(now+6000)}).available,false);
assert.equal(brokerReview({bid:21,ask:20.3}).available,false);
assert.equal(brokerReview({ask:18.4,bid:18.3}).available,false);
assert.equal(brokerReview({buyingPowerCHF:'0'}).available,false);
assert.equal(brokerReview({buyingPowerCHF:''}).manualFieldsComplete,false);
assert.equal(brokerReview({lotSize:'5'}).quantity,45);
assert.equal(brokerReview({lotSize:'2.5'}).available,false);
assert.equal(brokerReview({tickSize:'0.06'}).manualFieldsComplete,false);
assert.equal(brokerReview({venue:''}).manualFieldsComplete,false);
assert.equal(brokerReview({orderType:''}).manualFieldsComplete,false);
assert.equal(brokerReview({orderDuration:''}).manualFieldsComplete,false);
assert.equal(brokerReview({fxRateCHF:''}).manualFieldsComplete,false);
assert.equal(brokerReview({fxAt:iso(now-91000)}).available,false);
assert.equal(brokerReview({ask:30,bid:29}).manualFieldsComplete,false); // >5% divergence
assert.equal(brokerReview({}, {preliminary:test({quote:{...quote,kind:'calculated',
 modelVerified:true,validationReady:true,validationSamples:30}})}).available,true);
assert.equal(brokerReview({}, {preliminary:test({stopPlan:{...stopPlan,available:false}})}).available,false);
assert.equal(brokerReview({}, {product:{...product,quote:{isin:candidate.isin,metadata:{status:2}}}}).available,false);
assert.equal(brokerReview({}, {riskCHF:8}).available,false);
console.log('manual Top-3 DEGIRO screen re-evaluation: identity, source clock, FX, risk and no-order gates passed');


// User-shared DEGIRO product image: reusable bid/ask, but NEVER auto-fill an
// invented source timestamp or elevate OCR to an order execution quote.
globalThis.BobAndroidEvidence=require('./degiro_android_bridge.js');
const shared=globalThis.BobAndroidEvidence.readDraft([
 'BOB OCR-ENTWURF – NICHT VERIFIZIERT',
 'ISIN: DE000FG4JXV7',
 'Geld (OCR ungeprüft): 20,20',
 'Brief (OCR ungeprüft): 20,30',
 'Handelsplatz (OCR ungeprüft): Societe Generale OTC',
 'Anzeigezeit (OCR ungeprüft): 12/11/2026 14:02'
].join('\n'));
const imported=m.importAndroidScreenDraft(shared);
assert.equal(imported.available,true);
assert.equal(imported.values.bid,'20.2');
assert.equal(imported.values.ask,'20.3');
assert.equal(imported.values.quoteAt,'');
assert.equal(imported.values.confirmedByUser,false);
assert.equal(m.importAndroidScreenDraft({...shared,tradeApproved:true}).available,false);
assert.equal(m.importAndroidScreenDraft({...shared,sourceTime:at}).available,false);
console.log('manual DEGIRO read-only screenshot import never invents source times or trade approval');

// Authenticated handset summary crosses into the existing comparison only as
// an unconfirmed display. No receipt timestamp or market approval is promoted.
const handset={code:'COMPLETE',researchOnly:true,verified:false,tradeApproved:false,
 executionConfirmed:false,sourceTime:null,observedAt:at,fields:{
 'Geld':'20.20','Brief':'20.30','Währung':'EUR','Handelsplatz':'Test venue',
 'Hebel':'12,5','KO-Schwelle':'4200','Anzeigezeit':'03/11/2026 13:00',
 'Hinweis':'Keine Aussage zur Handelbarkeit'}};
const report={status:'ok',lastCheckedAt:at,items:[{isin:candidate.isin,
 state:'analysis-evidence-complete',handsetObservation:handset}]};
const read=(o={},r={})=>m.importHandsetReport({...report,...r,
 items:[{...report.items[0],handsetObservation:{...handset,...o}}]},candidate.isin,now);
assert.equal(read().available,true);
assert.equal(read().values.venue,'Test venue');
assert.equal(read().values.bid,'20.2');
assert.equal(read().values.quoteAt,'');
assert.equal(read().values.confirmedByUser,false);
assert.equal(read().leverage,'12,5');
assert.equal(read().ko,'4200');
assert.equal(read({observedAt:iso(now-90001)}).available,false);
assert.equal(read({observedAt:iso(now+1)}).available,false);
assert.equal(read({sourceTime:at}).available,false);
assert.equal(read({verified:true}).available,false);
assert.equal(read({terminalAtAudit:true}).available,false);
assert.equal(read({}, {status:'stale'}).available,false);
assert.equal(read({}, {lastCheckedAt:iso(now-120001)}).available,false);
for(const change of [{Hinweis:'Kurse verzögert'},{Hinweis:'Handel eingeschränkt'},
 {'Währung':'USD'},{Geld:'21.00'},{Geld:'1,234.50'},{Brief:'0'}])
 assert.equal(read({fields:{...handset.fields,...change}}).available,false);
assert.equal(m.importHandsetReport({...report,items:[...report.items,...report.items]},candidate.isin,now).available,false);
assert.equal(m.importHandsetReport({...report,items:[{...report.items[0],state:'terminated'}]},candidate.isin,now).available,false);
console.log('Handset audit bridge: timestamps, venue, decimal formats, stale/terminal/conflict guards passed');
