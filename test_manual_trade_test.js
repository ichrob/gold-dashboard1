const assert=require('assert'),fs=require('fs'),vm=require('vm');
const env={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),env);
const api=env.window.BobManualTradeTest,now=Date.parse('2026-10-08T10:00:00Z');
const p=api.position('DE000FC1CHB7','LONG',8.71,10,now);
assert.equal(p.mode,'manual-paper-test');
assert.throws(()=>api.position(p.isin,'NEUTRAL',8,1));
for(const [price,qty] of [[0,1],[8,1.5],[Infinity,1],[8,0]])assert.throws(()=>api.position(p.isin,'LONG',price,qty));
const q={isin:p.isin,bid:9,currency:'EUR',found:true,productVerified:true,bidAt:new Date(now).toISOString()};
assert(Math.abs(api.valuation(p,q,now).pnl-2.9)<1e-9);
assert(api.valuation(p,q,now+91000).stale);
assert(!api.valuation(p,q,now-1).available);
for(const patch of [{isin:'DE000FG4JXV7'},{currency:'CHF'},{bid:null},{productVerified:false},{bidAt:null}])assert(!api.valuation(p,{...q,...patch},now).available);
const short=api.position(p.isin,'SHORT',8.71,10,now);assert.equal(api.valuation(short,q,now).pnl,api.valuation(p,q,now).pnl);
// All valid imported products appear without reading market signal or release gates.
const fields=[{value:p.isin,dataset:{i:'1'}},{value:p.isin,dataset:{i:'2'}}];
env.document={querySelectorAll:()=>fields,querySelector:selector=>selector.includes('dir')?{value:'LONG'}:selector.includes('name')?{value:'Gold Long'}:null};
const rows=env.window.BobDegiro.tradeTestProducts();assert.equal(rows.length,1);assert.equal(rows[0].isin,p.isin);
console.log('Manual paper test: neutral-independent selection, deduplication, inputs, matching EUR quotes, stale quotes and long/short P&L passed');

const chart={...q,found:false,metadata:{status:1},analysisQuote:{bid:9.2,bidAt:q.bidAt,currency:'EUR',source:'SG Chart'}};
assert(api.valuation(p,chart,now).available);
assert(api.valuation(p,chart,now).referenceOnly);
assert(api.valuation(p,chart,now+91000).stale);
for(const patch of [{currency:'CHF'},{bidAt:null},{bidAt:new Date(now+1).toISOString()}])assert(!api.valuation(p,{...chart,analysisQuote:{...chart.analysisQuote,...patch}},now).available);
assert(!api.valuation(p,{...chart,isin:'DE000FG4JXV7'},now).available);
assert(!api.valuation(p,{...chart,metadata:{status:2}},now).available);
console.log('Dated analysis quotes: fallback, stale label, currency, identity, future dates and terminal status passed');
