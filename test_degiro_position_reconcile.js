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
assert.equal(p.loadTransactions(storage).rows.length,2);
const csv={kind:'portfolio',records:[{isin:valid,quantity:2,currency:'EUR'}],
 importedAt:'2026-11-03T01:00:00Z'};
const mail=(side,quantity,price,time,digest)=>({result:{
 status:'pending-review',isin:valid,side,quantity,priceEur:price,
 executedLocal:'02.11.2026 '+time,orderIdDigest:digest}});
const buy=mail('BUY',4,12.5,'14:05:06','a'.repeat(64));
const sell=mail('SELL',2,13,'14:07:08','b'.repeat(64));
let result=p.compare(csv,parsed,{configured:true,items:[buy,sell]});
assert.equal(result.status,'observed');
assert.equal(result.items.length,1);
assert.equal(result.items[0].matched,2);
assert.equal(result.items[0].emailNet,2);
assert.equal(result.items[0].csvQuantity,2);
assert.equal(result.items[0].state,'partial-verified');
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
assert.equal(result.items[0].state,'transactions-missing');
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
