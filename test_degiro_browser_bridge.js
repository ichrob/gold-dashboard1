'use strict';
const assert=require('node:assert/strict');
const bridge=require('./degiro_browser_bridge');
const store=require('./degiro_portfolio_store');
const parser=require('./degiro_report_import');
const report=parser.readReport('Produkt,ISIN,Anzahl,Währung\nSynthetic,US0378331005,2,USD');
const now=Date.now();
const offer={id:'12345678-1234-1234-1234-123456789012',createdAt:now,report};
const result=bridge.validate(offer,store,now);
assert.equal(result.records.length,1);
assert.equal(result.sourceKind,'browser-export');
for(const key of ['brokerVerified','ordersEnabled','rankingEligible','liveAccountConnected','realtime'])assert.equal(result[key],false);
for(const edit of [
 o=>o.createdAt=now-600001,o=>o.createdAt=now+5001,o=>o.id='../bad',
 o=>o.report.kind='transactions',o=>o.report.invalidRows=[4],
 o=>o.report.records.push({...o.report.records[0]}),
 o=>o.report.records[0].quantity='2',o=>o.report.records[0].quantity=Infinity,
 o=>o.report.records[0].currency='US<script>',o=>o.report.accountCurrency='INVALID',
 o=>o.report.records[0].isin='US0378331006',o=>o.report.cashBalances=[{currency:'USD',amount:Infinity}]
]){const copy=structuredClone(offer);edit(copy);assert.throws(()=>bridge.validate(copy,store,now));}
const elevated=structuredClone(offer);Object.assign(elevated.report,{ordersEnabled:true,brokerVerified:true,password:'must-not-save',rawCSV:'must-not-save'});
const cleaned=bridge.validate(elevated,store,now);
assert.equal(cleaned.ordersEnabled,false);assert.equal(cleaned.password,undefined);assert.equal(cleaned.rawCSV,undefined);
assert.equal(store.prepare(cleaned,cleaned.importedAt).sourceKind,'browser-export');
console.log('Browser bridge: freshness, complete snapshot, types, duplicates, permissions and field allowlist passed');
