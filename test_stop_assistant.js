/* Stop protection regression: independent source clocks, no broker orders. */
const assert=require('assert'),fs=require('fs');
const model=require('./trade_product.js');
const assistant=require('./bob_stop_assistant.js');
const now=Date.parse('2026-10-15T09:20:00Z');
const asAt=delay=>new Date(now-delay).toISOString();
const isin='DE000FG4JXV7';
const product=model.model({isin,direction:'SHORT',simpleSpotTurbo:true,
 referenceConfirmed:true,bid:20,goldReference:4200,fxReference:.9,fxScenario:.9,
 ratio:.1,strike:4460,ko:4460,entry:20,quantity:10,
 source:'Datiertes Referenzbild',referenceAt:asAt(30000)});
const baseQuote={isin,productVerified:true,found:true,metadata:{status:1,direction:'SHORT'},
 currency:'EUR',source:'SG offizieller Geld-/Briefkurs',priceKind:'market-observation',
 bid:20,ask:20.02,bidAt:asAt(20000),askAt:asAt(20000),isExecutableQuote:true};
const alt={isin,currency:'EUR',source:'comdirect · zweiseitige Marktbeobachtung',
 bid:19.8,ask:19.82,bidAt:asAt(10000),askAt:asAt(10000),
 priceKind:'market-observation',isExecutableQuote:false,degiroExecutable:false};
const chosen=assistant.selectQuote({...baseQuote,secondaryQuote:alt},isin,now);
assert.equal(chosen.kind,'research');
assert.equal(chosen.origin,'comdirect');
assert.equal(chosen.degiroExecutable,false);
assert.equal(chosen.bid,19.8);
const issuer=assistant.selectQuote({...baseQuote,secondaryQuote:{...alt,bidAt:asAt(40000),askAt:asAt(40000)}},isin,now);
assert.equal(issuer.kind,'issuer');
assert.equal(issuer.bid,20);
for(const patch of [
 {isin:'DE000FG5GUX2'},{currency:'CHF'},{isExecutableQuote:true},
 {degiroExecutable:true},{askAt:null},{ask:19.7},{bidAt:asAt(130000)},
 {priceKind:'calculated'},{source:''}
]){
 const selected=assistant.selectQuote({...baseQuote,found:false,
    isExecutableQuote:false,secondaryQuote:{...alt,...patch}},isin,now);
 assert.equal(selected,null,'No unverified alternate promoted: '+JSON.stringify(patch));
}
assert.equal(assistant.selectQuote({...baseQuote,metadata:{status:2},secondaryQuote:alt},isin,now),null);
assert.equal(assistant.selectQuote({...baseQuote,productVerified:false,secondaryQuote:alt},isin,now),null);
assert.equal(assistant.selectQuote({...baseQuote,found:false,sourceDisabled:true,secondaryQuote:alt},isin,now),null);
const spots={xaus:4225,is_genuine_xauusd_spot:true,
 spot_price_as_of:asAt(15000),usd_eur_meta:{rate:.9,fetchedAt:asAt(12000),source:'FX research'}};
const evaluate=(patch={})=>assistant.evaluate({product,stopGold:4230,targetGold:4150,spots,quote:chosen,now,...patch});
let result=evaluate();
assert(result.available);
assert.equal(result.observed,null);
assert.equal(result.model.signal,'model-stop-near');
assert(result.model.stopEur>0&&result.model.targetEur>0);
assert.equal(result.degiroExecutable,false);
assert.equal(evaluate({spots:{...spots,spot_error:'outage'},quote:{...issuer,bid:16,ask:16.02}}).stage,'issuer-price-only');
assert.equal(result.automaticOrder,false);
let hit=evaluate({spots:{...spots,xaus:4235}});
assert.equal(hit.stage,'model-stop-zone'); // Gold down/short up, closer to KO? model stop breached
assert.equal(hit.observed,null);
let issuerHit=evaluate({quote:{...issuer,bid:16,ask:16.02}});
assert.equal(issuerHit.stage,'issuer-stop-observed');
assert.equal(issuerHit.observed.bid,16);
assert.equal(issuerHit.degiroExecutable,false);
let researchHit=evaluate({quote:{...chosen,bid:16,ask:16.02}});
assert.equal(researchHit.observed,null);
assert.notEqual(researchHit.stage,'issuer-stop-observed');
for(const testSpots of [
 {...spots,spot_error:'provider offline'},
 {...spots,is_genuine_xauusd_spot:false},
 {...spots,spot_price_as_of:asAt(120000)},
 {...spots,usd_eur_meta:{...spots.usd_eur_meta,error:'failed'}},
 {...spots,usd_eur_meta:{...spots.usd_eur_meta,fetchedAt:asAt(125000)}}
]){
 const v=evaluate({spots:testSpots,quote:null});
 assert.equal(v.model,null);
 assert(!['issuer-stop-observed','model-stop-zone'].includes(v.stage));
}
assert(!evaluate({stopGold:4460}).available);
assert(!evaluate({product:{...product,currency:'CHF'}}).available);
const guide=assistant.instructions({isin,quantity:10,stopEur:result.model.stopEur});
assert(guide.available);
assert(guide.steps.length>=4);
assert(guide.steps.join(' ').includes('ausschließlich selbst bestätigen'));
assert(!assistant.instructions({isin:'bad',quantity:10,stopEur:16}).available);
assert(!assistant.instructions({isin,quantity:10,stopEur:16,currency:'CHF'}).available);
const html=fs.readFileSync('Bob.html','utf8');
assert(html.includes('/bob_stop_assistant.js?'));
assert(html.includes('window.BobStopAssistant?.update({product:p'));
assert(html.includes('window.BobStopAssistant?.selectQuote(q,isin)'));
console.log('Read-only source switch, verified bid/ask clocks, theoretical stop tier, issuer tier, FX/KO fail-closed and manual DEGIRO help passed');
