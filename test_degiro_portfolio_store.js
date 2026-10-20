'use strict';
const assert=require('node:assert/strict');
const parser=require('./degiro_report_import');
const depot=require('./degiro_portfolio_store');
function storage(){
 const data=new Map();
 return {getItem:k=>data.has(k)?data.get(k):null,
  setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k),data};
}
function mockISIN(n){
 const prefix='DETEST'+String(n).padStart(5,'0');
 for(let i=0;i<10;i++)if(depot.validIsin(prefix+i))return prefix+i;
 throw Error('Unable to make mock ISIN');
}
const ids=Array.from({length:5},(_,i)=>mockISIN(i+1));
const csv=[
 'Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF',
 'CASH & CASH FUND & F, , , ,CHF,503.31,503.31',
 'Test Faktor A,'+ids[0]+',1,0.10,EUR,0.10,0.09',
 'Test Constant Leverage B,'+ids[1]+',1,0.01,EUR,0.01,0.01',
 'Test Gold Future Faktor C,'+ids[2]+',1,0.12,EUR,0.12,0.11',
 'Test Technology Faktor D,'+ids[3]+',1,0.02,EUR,0.02,0.02',
 'Test Strategy Faktor E,'+ids[4]+',1,1.55,EUR,1.55,1.45'
].join('\n');
const parsed=parser.readReport(csv);
assert.equal(parsed.records.length,5);
const store=storage();
const saved=depot.save(store,parsed,'2026-10-20T02:00:00Z');
assert.equal(saved.records.length,5);
assert.equal(saved.cashBalances.length,1);
assert.equal(saved.records.filter(p=>p.type==='factor').length,5);
assert.equal(saved.records[2].isin,ids[2]);
assert.equal(saved.records[2].name,'Test Gold Future Faktor C');
assert.equal(saved.records[2].currency,'EUR');
assert.equal(saved.accountCurrency,'CHF');
assert.equal(saved.records[2].accountValue,'0.11');
assert.equal(saved.rankingEligible,false);
assert.equal(saved.brokerVerified,false);
assert.equal(saved.liveAccountConnected,false);
assert.equal(saved.ordersEnabled,false);
const restored=depot.load(store);
assert.equal(restored.records.length,5);
assert.equal(restored.records[2].name,saved.records[2].name);
assert.deepEqual(restored.records.map(x=>x.isin),ids);
assert.deepEqual(restored.cashBalances,saved.cashBalances);
assert.equal(restored.importedAt,'2026-10-20T02:00:00.000Z');
const smaller=parser.readReport(csv.split('\n').slice(0,4).join('\n'));
depot.save(store,smaller,'2026-10-20T02:05:00Z');
assert.equal(depot.load(store).records.length,2,'Next portfolio replaces previous holdings');
assert.throws(()=>depot.save(store,parser.readReport('Datum,ISIN,Quantity,Type\n19-10-2026,'+ids[2]+',1,Buy')),
 /Nur ein DEGIRO-Portfolioexport/);
assert.equal(depot.load(store).records.length,2,'Transaction CSV never replaces portfolio');
store.setItem(depot.KEY,JSON.stringify({...saved,brokerVerified:true}));
assert.equal(depot.load(store),null,'Corrupted permissions must never be used');
depot.save(store,parsed);
depot.clear(store);
assert.equal(depot.load(store),null);
const blocked={...store,setItem:()=>{throw Error('Storage blocked');}};
assert.throws(()=>depot.save(blocked,parsed),/Storage blocked/);
assert.equal(depot.load(store),null);
console.log('DEGIRO CSV holdings: all products, persistence, replacement, separation and privacy guards passed');
