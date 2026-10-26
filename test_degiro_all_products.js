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
const recentIssuer={isin:ids[5],sourceObservations:[{
 bid:12.1,ask:12.2,currency:'EUR',source:'SG Vergleich',
 bidAt:'2026-10-20T01:59:35Z',askAt:'2026-10-20T01:59:35Z',
 researchOnly:true,degiroExecutable:false
}]};
const staleIssuer=combined.auditQuote(recentIssuer,Date.parse('2026-10-20T02:00:00Z'),'stale');
assert(staleIssuer&&!staleIssuer.fresh,'Stale overall report cannot claim fresh price');
assert.equal(staleIssuer.degiroExecutable,false);
const currentIssuer=combined.auditQuote(recentIssuer,Date.parse('2026-10-20T02:00:00Z'),'ok');
assert(currentIssuer.fresh,'Dated issuer pair may be shown as timely comparison');
assert.equal(currentIssuer.researchOnly,true);
assert.equal(combined.auditQuote({isin:ids[5],sourceObservations:[{
 ...recentIssuer.sourceObservations[0],askAt:null
}]},Date.parse('2026-10-20T02:00:00Z'),'ok'),null,'Issuer price pair requires both clocks');

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
assert.equal(combined.quoteObservation({isin:ids[1],quote:{...quoted.quote,isin:ids[1],askAt:null,quoteAt:null}},
 Date.parse('2026-10-20T02:00:00Z')),null,'Missing ask timestamp must not look fresh');
const injected=combined.combine(saved,watchlist,{status:'ok',items:[
 {isin:'INVALID-ISIN',name:'spoofed'},
 {isin:ids[1],tradeApproved:true,degiroVerified:true,degiroExecutable:true}
]},[],Date.now());
assert.equal(injected.length,12,'Bad server ISIN rejected');
assert(injected.every(x=>x.tradeApproved===false&&x.executableQuote===false),'Server flags cannot grant trade');
assert.equal(combined.readWatchlist({getItem:()=>'{'}).length,0);
console.log('DEGIRO unified products: holdings/watchlist/audit union, freshness, safety and dedupe passed');

const evidenceStore={values:{},getItem(k){return this.values[k]||null;},setItem(k,v){this.values[k]=v;}};
const observed1=Date.parse('2026-10-20T08:00:00Z');
const observed2=Date.parse('2026-10-21T08:00:00Z');
assert.equal(combined.updateEvidenceHistory(evidenceStore,[{isin:ids[0]},{isin:ids[1]}],new Date(observed1).toISOString(),observed2).saved,true);
const history=combined.updateEvidenceHistory(evidenceStore,[{isin:ids[1]}],new Date(observed2).toISOString(),observed2);
assert.equal(history.items.length,2,'Old list evidence remains after new import');
assert.equal(history.items.find(x=>x.isin===ids[0]).lastSeenAt,new Date(observed1).toISOString());
assert.equal(history.items.find(x=>x.isin===ids[1]).lastSeenAt,new Date(observed2).toISOString());
assert(history.items.every(x=>x.brokerTradeable===false));
assert.equal(combined.updateEvidenceHistory(evidenceStore,[{isin:ids[2]}],new Date(observed2+60000).toISOString(),observed2).saved,false);
