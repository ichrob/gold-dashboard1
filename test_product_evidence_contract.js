'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const common=require('./product_evidence_contract');
const workspace=require('./bob_unified_workspace');
const products=require('./degiro_all_products');
const now=Date.parse('2026-10-22T10:05:30Z');
const id='DE000FG14AV8';
const base={isin:id,direction:'LONG',reference:{isin:id,ko:4200,currency:'EUR'},quote:{
 isin:id,found:true,productVerified:true,priceKind:'market-observation',
 currency:'EUR',metadata:{status:1,direction:'LONG',currency:'EUR'},
 bid:4.20,ask:4.25,bidAt:'2026-10-22T10:05:00Z',askAt:'2026-10-22T10:05:00Z',
 leverage:12,leverageAt:'2026-10-22T10:05:00Z',source:'Issuer'}};
assert.equal(common.validIsin(id),true);
assert.equal(common.validIsin('DE000FG14AV9'),false);
assert.equal(common.originalAge(base.quote.bidAt,now),30000);
assert.equal(common.originalAge('2026-10-22 10:05:00',now),null);
const verified=common.productEvidence(base,now);
assert.equal(verified.prices.state,'observed');
assert.equal(verified.leverage.state,'observed');
assert.equal(verified.barrier.state,'observed');
assert.equal(verified.venue.state,'unknown');
assert.equal(verified.tradeable,false);
assert.equal(verified.automaticOrder,false);
// The mobile cockpit must never reinterpret or upgrade the unified contract.
assert.deepEqual(workspace.productEvidence(base,now),verified);
for(const changed of [
 {quote:{...base.quote,bid:5,ask:4}},
 {quote:{...base.quote,bidAt:null}},
 {quote:{...base.quote,askAt:'2026-10-22T10:02:00Z'}},
 {quote:{...base.quote,priceKind:'issuer-chart'}},
 {quote:{...base.quote,paperSelectionOnly:true}},
 {quote:{...base.quote,metadata:{...base.quote.metadata,status:2}}},
]){
 const x=common.productEvidence({...base,...changed},now);
 assert.notEqual(x.prices.state,'observed');
 assert.equal(x.tradeable,false);
}
assert.equal(common.productEvidence({...base,reference:{...base.reference,currency:'CHF'}},now).currency.state,'conflict');
assert.equal(common.productEvidence({...base,direction:'SHORT'},now).direction.state,'conflict');
const combined=products.combine(
 {records:[{isin:id,quantity:10,currency:'EUR',price:4.1,value:41,name:'Test'}]},
 [{isin:id,name:'Screenshot GOLD',direction:'LONG'}],
 {status:'ok',lastCheckedAt:new Date(now).toISOString(),items:[{isin:id,state:'incomplete'}]},
 [{isin:id,quote:base.quote}],now
);
assert.equal(combined.length,1);
assert.equal(combined[0].inDepot,true);
assert.equal(combined[0].inWatchlist,true);
assert.equal(combined[0].evidence.isin,id);
assert.equal(combined[0].evidence.identity.state,'observed');
assert.equal(combined[0].evidence.quote.state,'observed');
assert.equal(combined[0].evidence.executableQuote,false);
assert.equal(combined[0].evidence.tradeable,false);
assert.equal(combined[0].tradeApproved,false);
const staticServer=fs.readFileSync('server.py','utf8');
assert.match(staticServer,/PRODUCT_EVIDENCE_CONTRACT_JS/);
assert.match(staticServer,/\/product_evidence_contract\.js/);
const first=staticServer.indexOf('src="/product_evidence_contract.js"');
const after=staticServer.indexOf('src="/degiro_handoff.js"');
assert(first>=0&&after>first);
console.log('Product source contract: shared bid/ask evidence, immutable clocks, CSV/watchlist union, no DEGIRO approval passed');