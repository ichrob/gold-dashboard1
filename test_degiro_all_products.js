'use strict';
const assert=require('node:assert/strict');
const combined=require('./degiro_all_products');
const depotStore=require('./degiro_portfolio_store');
function isin(n){
 const base='DETEST'+String(n).padStart(5,'0');
 for(let digit=0;digit<10;digit++)if(combined.validIsin(base+digit))return base+digit;
 throw Error('No valid synthetic ISIN');
}
const ids=Array.from({length:12},(_,i)=>isin(i+1));
const samplePortfolio={
 kind:'portfolio',
 records:ids.slice(0,5).map((id,i)=>({isin:id,product:'Synthetic Depot Factor '+i,quantity:1,currency:'EUR',
 price:'1.25',value:'1.25',accountValue:'1.16'})),
 cashBalances:[{currency:'CHF',amount:100,accountValue:100}],
 accountCurrency:'CHF'
};
const saved=depotStore.prepare(samplePortfolio,'2026-10-20T02:00:00Z');
const watchlist=ids.slice(4,12).map(id=>({isin:id,name:'Screenshot product '+id,direction:'SHORT'}));
const status={status:'stale',lastCheckedAt:'2026-10-19T19:34:03Z',
 items:watchlist.map(w=>({isin:w.isin,direction:'SHORT',state:'analysis-evidence-complete',
 quoteSourceAt:'2026-10-19T19:33:00+00:00',tradeApproved:false}))};
const items=combined.combine(saved,watchlist,status,[],Date.parse('2026-10-20T02:00:00Z'));
assert.equal(items.length,12,'5 portfolio + 8 watchlist, one overlap');
const overlap=items.find(x=>x.isin===ids[4]);
assert(overlap.inDepot&&overlap.inWatchlist&&overlap.inAudit,'Duplicate ISIN must be merged');
assert.equal(overlap.quantity,1);
assert.equal(items.filter(x=>x.inDepot).length,5);
assert.equal(items.filter(x=>x.inWatchlist||x.inAudit).length,8);
assert(items.every(x=>x.tradeApproved===false && x.executableQuote===false &&
 x.degiroConnected===false && x.rankingEligible===false));
assert(items.find(x=>x.isin===ids[0]).productKind==='factor');
assert(items.find(x=>x.isin===ids[11]).inDepot===false);
assert.equal(combined.safeAudit(status).status,'stale');
assert.equal(combined.summary(items,status).accountSynced,false);
const storage={
 getItem:key=>key==='bobDegiroProductsV2'?JSON.stringify({version:2,
  products:watchlist, listUploadedAt:'2026-10-19T06:30:00Z'}):null
};
const recovered=combined.readWatchlist(storage);
assert.equal(recovered.length,8);
const quoted={
 isin:ids[4],
 quote:{isin:ids[4],bid:18.12,ask:18.14,currency:'CHF',
 bidAt:'2026-10-20T01:59:35+00:00',askAt:'2026-10-20T01:59:35+00:00',
 source:'SG - chart',researchOnly:true}
};
const fresh=combined.combine(saved,watchlist,status,[quoted],Date.parse('2026-10-20T02:00:00Z'));
assert(fresh.find(x=>x.isin===ids[4]).quote.fresh);
assert.equal(fresh.find(x=>x.isin===ids[4]).quote.degiroExecutable,false);
const stale=combined.combine(saved,watchlist,status,[quoted],Date.parse('2026-10-20T02:03:00Z'));
assert.equal(stale.find(x=>x.isin===ids[4]).quote.fresh,false);
assert.equal(combined.quoteObservation({isin:ids[1],quote:{...quoted.quote,isin:ids[1],bid:20,ask:10}},
 Date.parse('2026-10-20T02:00:00Z')),null,'Crossed prices rejected');
assert.equal(combined.quoteObservation({isin:ids[1],quote:{...quoted.quote,isin:ids[1],bidAt:'bad',askAt:'bad'}},
 Date.parse('2026-10-20T02:00:00Z')),null,'No undated quotes');
const injected=combined.combine(saved,watchlist,{status:'ok',items:[
 {isin:'INVALID-ISIN',name:'spoofed'},
 {isin:ids[1],tradeApproved:true,degiroVerified:true,degiroExecutable:true}
]},[],Date.now());
assert.equal(injected.length,12,'Bad server ISIN rejected');
assert(injected.every(x=>x.tradeApproved===false&&x.executableQuote===false),'Server flags cannot grant trade');
assert.equal(combined.readWatchlist({getItem:()=>'{'}).length,0);
console.log('DEGIRO unified products: holdings/watchlist/audit union, freshness, safety and dedupe passed');
