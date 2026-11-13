'use strict';
const assert=require('node:assert/strict');
const p=require('./degiro_position_reconcile.js');
const valid='DE000FG4JXV7';
const store=()=>{const map=new Map();return {
 getItem:k=>map.has(k)?map.get(k):null,
 setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k)};};
const storage=store();
const transactions={kind:'transactions',records:[
 {isin:valid,side:'Buy',quantity:4,price:'12,50',currency:'EUR',date:'02.11.2026',time:'14:05:06'},
 {isin:valid,side:'Sell',quantity:2,price:'13,00',currency:'EUR',date:'02.11.2026',time:'14:07:08'}
 ],invalidRows:[]};
const parsed=p.saveTransactions(storage,transactions,'2026-11-03T01:00:00Z');
assert.equal(parsed.rows.length,2);
assert.equal(parsed.rows[0].price,12.5);
const signedSale=p.normalTransactions({kind:'transactions',records:[
 {...transactions.records[1],quantity:-2}]},'2026-11-03T01:00:00Z');
assert.equal(signedSale.rows[0].quantity,2);
assert.throws(()=>p.normalTransactions({kind:'transactions',records:[
 {...transactions.records[0],quantity:-2}]},'2026-11-03T01:00:00Z'));
assert.equal(p.loadTransactions(storage).rows.length,2);
const csv={kind:'portfolio',records:[{isin:valid,quantity:2,currency:'EUR'}],
 importedAt:'2026-11-03T01:00:00Z'};
const mail=(side,quantity,price,time,digest)=>({result:{
 status:'pending-review',isin:valid,side,quantity,priceEur:price,
 executedLocal:'02.11.2026 '+time,orderIdDigest:digest}});
const screenshotStore=store();
screenshotStore.setItem('bobTradeEvidenceV1',JSON.stringify({
 [valid]:{isin:valid,currency:'EUR',direction:'SHORT',
 entry:{price:12.5,quantity:4,at:'02.11.2026 14:05:06',orderId:'screenshot-local'}}
}));
const screenshots=p.screenshotPurchases(screenshotStore);
assert.equal(screenshots.length,1);
assert.equal(screenshots[0].hasSeconds,true);
assert.equal(screenshots[0].side,'BUY');
const buy=mail('BUY',4,12.5,'14:05:06','a'.repeat(64));
assert.equal(p.stableMail(buy).currency,'EUR');
const sell=mail('SELL',2,13,'14:07:08','b'.repeat(64));
let result=p.compare(csv,parsed,{configured:true,items:[buy,sell]});
assert.equal(result.status,'observed');
assert.equal(result.items.length,1);
assert.equal(result.items[0].matched,2);
assert.equal(result.items[0].emailNet,2);
assert.equal(result.items[0].csvQuantity,2);
assert.equal(result.items[0].state,'partial-verified');
const threeSource=p.compare(csv,parsed,{configured:true,items:[buy,sell]},Date.now(),screenshots);
assert.equal(threeSource.items[0].screenshotBuys,1);
assert.equal(threeSource.items[0].screenshotCsvMatched,1);
assert.equal(threeSource.items[0].screenshotMailMatched,1);
assert.equal(threeSource.items[0].emailNet,2,'Screenshot must not change email net inventory');
const minutes=store();
minutes.setItem('bobTradeEvidenceV1',JSON.stringify({
 [valid]:{isin:valid,currency:'EUR',entry:{price:12.5,quantity:4,at:'02.11.2026 14:05'}}}));
const min=p.screenshotPurchases(minutes);
assert.equal(min.length,1);
assert.equal(min[0].hasSeconds,false);
const minuteReport=p.compare(csv,parsed,{configured:true,items:[buy,sell]},Date.now(),min);
assert.equal(minuteReport.items[0].screenshotTimeUncertain,1);
assert.equal(minuteReport.items[0].screenshotMailMatched,0);
const wrong=store();
wrong.setItem('bobTradeEvidenceV1',JSON.stringify({
 [valid]:{isin:valid,currency:'EUR',entry:{price:-3,quantity:4,at:'02.11.2026 14:05:06'}}}));
assert.equal(p.screenshotPurchases(wrong).length,0);
assert.equal(p.screenshotPurchases(store()).length,0);

assert.equal(result.sourceComplete,false);
assert.equal(result.brokerCurrent,false);
assert.equal(result.activeTradesModified,false);
result=p.compare(csv,parsed,{configured:true,items:[buy,buy,sell]});
assert.equal(result.items[0].duplicateMails,1);
assert.equal(result.items[0].emailBuys,4);
assert.equal(result.items[0].matched,2);
const conflicting=mail('BUY',5,12.5,'14:05:06','a'.repeat(64));
result=p.compare(csv,parsed,{configured:true,items:[buy,conflicting,sell]});
assert.equal(result.items[0].ambiguous,2);
assert.equal(result.items[0].matched,1);
assert.equal(result.items[0].emailNet,-2);
const sampleSale=[{id:'trade-1',snapshot:{closureSource:'confirmed-screenshot',
 product:{isin:valid,currency:'EUR'},
 exitReceipt:{side:'SELL',isin:valid,productCurrency:'EUR',
 quantity:2,price:13,executedLocal:'02.11.2026 14:07:08',
 imageSha256:'f'.repeat(64),transactionId:'DEGIRO-sale-1'}}}];
const sales=p.confirmedSaleScreenshots(sampleSale);
assert.equal(sales.length,1);
assert.equal(sales[0].side,'SELL');
const allEvidence=p.compare(csv,parsed,{configured:true,items:[buy,sell]},
 Date.now(),screenshots.concat(sales));
assert.equal(allEvidence.items[0].screenshotBuys,1);
assert.equal(allEvidence.items[0].screenshotSells,1);
assert.equal(allEvidence.items[0].screenshotCsvMatched,2);
assert.equal(allEvidence.items[0].screenshotMailMatched,2);
assert.equal(allEvidence.items[0].emailNet,2);
assert.equal(p.confirmedSaleScreenshots(sampleSale.concat(sampleSale)).length,1);
assert.equal(p.confirmedSaleScreenshots([{snapshot:{...sampleSale[0].snapshot,
 closureSource:'pending-review'}}]).length,0);
assert.equal(p.confirmedSaleScreenshots([{snapshot:{...sampleSale[0].snapshot,
 exitReceipt:{...sampleSale[0].snapshot.exitReceipt,imageSha256:'invalid'}}}]).length,0);

const noId=mail('BUY',4,12.5,'14:05:06',null);
result=p.compare(csv,parsed,{configured:true,items:[noId]});
assert.equal(result.items[0].ambiguous,1);
assert.equal(result.items[0].emailNet,0);
assert.equal(result.anonymous,1);
const earlier=p.saveTransactions(storage,{kind:'transactions',records:[
 {...transactions.records[0],time:'14:05'}]},'2026-11-03T01:05:00Z');
result=p.compare(csv,earlier,{configured:true,items:[buy]});
assert.equal(result.items[0].matched,0);
assert.equal(result.items[0].partialMatches,1);
result=p.compare(null,parsed,{configured:true,items:[buy,sell]});
assert.equal(result.items[0].state,'csv-missing');
result=p.compare(csv,null,{configured:true,items:[buy]});
assert.equal(result.items[0].state,'transactions-optional');
const withoutTransaction=p.compare(csv,null,{configured:true,items:[buy]},Date.now(),screenshots);
assert.equal(withoutTransaction.items[0].state,'screenshot-mail-corroborated');
assert.equal(withoutTransaction.items[0].screenshotMailMatched,1);
assert.equal(withoutTransaction.items[0].csvQuantity,2);
assert.equal(withoutTransaction.brokerCurrent,false);

const newer={...buy,result:{...buy.result,executedLocal:undefined,
 executedAt:'2026-11-03T02:00:00Z'}};
result=p.compare(csv,parsed,{configured:true,items:[newer]});
assert.equal(result.items[0].csvAfterEmailUnknown,false);
assert.equal(p.receiptLocal({executedAt:'2026-11-02T13:05:06Z'}).time,'14:05:06');
assert.equal(p.receiptLocal({executedAt:'invalid'}),null);
assert.equal(p.stableMail({result:{...buy.result,quantity:-3}}),null);
assert.throws(()=>p.saveTransactions(storage,{kind:'portfolio',records:transactions.records}),/Transaktions/);
assert.throws(()=>p.saveTransactions(storage,{kind:'transactions',records:[
 {...transactions.records[0],isin:'DE0000000000'}]}),/Keine eindeutig/);
p.clearTransactions(storage);
assert.equal(p.loadTransactions(storage),null);
console.log('DEGIRO CSV/email evidence reconciliation: source, duplicates, partial fills, UTC, privacy and fail-closed checks passed');
