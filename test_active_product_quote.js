const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const bridge=require('./bob_stop_assistant.js');
const html=fs.readFileSync('Bob.html','utf8');
const c={window:{BobStopAssistant:bridge}};
vm.runInNewContext(html.slice(html.indexOf('function selectActiveProductQuote('),
  html.indexOf('let activeProductQuote=null')),c);
const isin='DE000FG7K275';
const now=new Date(Date.now()-12000).toISOString();
const base={isin,productVerified:true,metadata:{status:1},found:true,currency:'EUR',
  bid:15,ask:15.02,bidAt:now,askAt:now,source:'issuer',isExecutableQuote:true,
  priceKind:'market-observation'};
const select=q=>c.selectActiveProductQuote(q,isin);
assert.equal(select({...base,calculatedProduct:{available:false}}).bid,15);
assert.equal(select({...base,calculatedProduct:{available:true}}).kind,'issuer');
const chart={...base,found:false,
 analysisQuote:{isin,bid:14,ask:14.02,bidAt:now,askAt:now,currency:'EUR',
  source:'SG chart',priceKind:'issuer-chart',isExecutableQuote:false,degiroExecutable:false}};
assert.equal(select(chart).kind,'research');
assert.equal(select(chart).chart,true);
assert.equal(select({...chart,secondaryQuote:{...chart.analysisQuote,bid:13,ask:13.02,
  source:'comdirect',priceKind:'market-observation'}}).kind,'research');
for(const q of [{...base,isin:'other'},{...base,bidAt:null},{...base,askAt:null},
 {...base,estimated:true},{...base,priceKind:'calculated'},{...base,currency:'USD'},
 {...base,metadata:{status:2}},{...base,productVerified:false},
 {...base,bidAt:'2020-01-01T00:00:00Z'},
 {...base,bidAt:new Date(Date.now()+100000).toISOString()}
])assert.throws(()=>select(q));
assert.equal(select({...base,found:false,
 secondaryQuote:{...chart.analysisQuote,source:'comdirect'}}).kind,'research');
console.log('Active trade fallback: verified ISIN, original bid/ask clocks, chart/research separation, stale and terminated exclusion passed');
