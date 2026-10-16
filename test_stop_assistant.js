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
// Original clocks from independently linked sources may be compared, never copied.
const multi=assistant.compareQuoteSources({...baseQuote,secondaryQuote:alt},isin,now);
assert.equal(multi.quotes.length,2);
assert.equal(multi.quotes[0].origin,'comdirect');
assert.equal(multi.quotes[0].at,alt.bidAt);
assert.equal(multi.quotes[1].at,baseQuote.bidAt);
assert.equal(multi.comparisons.length,1);
assert.equal(multi.comparisons[0].clockGapSeconds,10);
assert.equal(multi.comparisons[0].bidDifference,-0.2);
assert.equal(multi.comparisons[0].askDifference,-0.2);
assert.equal(multi.automaticOrder,false);
assert.equal(multi.degiroExecutable,false);
assert.equal(chosen.comparison.quotes.length,2);
assert.equal(assistant.compareQuoteSources({...baseQuote,secondaryQuote:{...alt,bidAt:asAt(80000),askAt:asAt(80000)}},isin,now).comparisons.length,0);
assert.equal(assistant.compareQuoteSources({...baseQuote,secondaryQuote:{...alt,askAt:null}},isin,now).quotes.length,1);
assert.equal(assistant.compareQuoteSources({...baseQuote,secondaryQuote:{...alt,bidAt:asAt(10000),askAt:asAt(65000)}},isin,now).comparisons.length,0);

assert.equal(assistant.compareQuoteSources({...baseQuote,secondaryQuote:{...alt,isin:'DE000FC1CHB7'}},isin,now).quotes.length,1);
assert.equal(assistant.compareQuoteSources({...baseQuote,secondaryQuote:{...alt,bid:16,ask:16.02,bidAt:baseQuote.bidAt,askAt:baseQuote.askAt}},isin,now).comparisons[0].divergent,true);
assert.equal(assistant.compareQuoteSources({...baseQuote,secondaryQuote:{...alt,estimated:true}},isin,now).quotes.length,1);
// No live issuer quote can be manufactured from a screenshot/model/secondary source.
assert.equal(assistant.selectQuote({...baseQuote,found:false,secondaryQuote:alt},isin,now).kind,'research');
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
assert(!evaluate({product:{...product,currency:'GBP'}}).available);
const guide=assistant.instructions({isin,quantity:10,stopEur:result.model.stopEur});
assert(guide.available);
assert(guide.steps.length>=4);
assert(guide.steps.join(' ').includes('ausschließlich selbst bestätigen'));
assert(!assistant.instructions({isin:'bad',quantity:10,stopEur:16}).available);
assert(!assistant.instructions({isin,quantity:10,stopEur:16,currency:'GBP'}).available);
const html=fs.readFileSync('Bob.html','utf8');
assert(html.includes('/bob_stop_assistant.js?'));
assert(html.includes('window.BobStopAssistant?.update({product:p'));
assert(html.includes('window.BobStopAssistant?.selectQuote(q,isin,Date.now(),currency)'));
assert(fs.readFileSync('bob_stop_assistant.js','utf8').includes('Quellenvergleich und Originalzeiten'));
assert(fs.readFileSync('bob_stop_assistant.js','utf8').includes('data-stop-sources'));
assert(fs.readFileSync('bob_stop_assistant.js','utf8').includes('comparison.quotes.length'));
console.log('Read-only source switch, verified bid/ask clocks, theoretical stop tier, issuer tier, FX/KO fail-closed and manual DEGIRO help passed');
const chfProduct={...product,currency:'CHF',fxReference:.8,fxScenario:.8};
const chfQuote=assistant.selectQuote({...baseQuote,currency:'CHF',secondaryQuote:alt},isin,now,'CHF');
assert.equal(chfQuote.currency,'CHF');assert.equal(chfQuote.kind,'issuer');
assert.equal(assistant.selectQuote(baseQuote,isin,now,'CHF'),null);
const chfResult=evaluate({product:chfProduct,quote:chfQuote,spots:{...spots,usd_chf_meta:{rate:.8,fetchedAt:asAt(12000)}}});
assert(chfResult.model);assert.equal(chfResult.model.currency,'CHF');
assert.equal(chfResult.model.stopEur,17.6);
assert.equal(evaluate({product:chfProduct,quote:null}).model,null);
assert.equal(evaluate({product:chfProduct,quote:null,spots:{...spots,usd_chf_meta:{rate:.8,fetchedAt:asAt(130000)}}}).model,null);
assert(assistant.instructions({isin,quantity:10,stopEur:17.6,currency:'CHF'}).available);
