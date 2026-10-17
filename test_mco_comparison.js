const assert=require('assert'),fs=require('fs'),vm=require('vm');
const {compare}=require('./mco_comparison.js');
const at=1792236600000,ctx={analysisAt:at,timeframe:'15m',instrument:'XAU/USD',currency:'USD'},mark={key:'r618',price:4000,comparisonContext:ctx};
const item={channelId:'UCsl6Z6p7GOkczo8Cv-GH6Dg',trustedTranscript:true,mcoFibonacci:[mark]};
const calc=(bars,t,tf)=>{assert.equal(t,at);assert.equal(tf,'15m');return {available:true,levels:{r618:4020},goldPrice:4010};};
assert.equal(compare(item,[{}],calc,at+1)[0].percent,.5);
assert.equal(compare(item,[{}],calc,at+1)[0].delta,20);
assert.equal(compare(item,[{}],()=>({available:true,levels:{r618:4000}}),at+1)[0].percent,0);
for(const change of [{analysisAt:null},{analysisAt:at+100},{instrument:'GC=F'},{timeframe:null}]){
 const r=compare({...item,mcoFibonacci:[{...mark,comparisonContext:{...ctx,...change}}]},[{}],()=>{throw Error('Must not calculate');},at+1)[0];assert(r.reason);assert.equal(r.percent,null);
}
assert(compare({...item,trustedTranscript:false},[{}],calc,at+1)[0].reason);
// Exercise real historical filtering, including rejecting future confirmation bars.
const html=fs.readFileSync('Bob.html','utf8'),start=html.indexOf('window.BobMcoHistoricalFib=function'),end=html.indexOf('\nfunction chartTradingAxis',start);
let used;const sandbox={window:{},Date:{now:()=>at+900000},chartFibonacci:(bars)=>{used=bars;return {valid:true,levels:{r618:4000},direction:'LONG'};}};vm.createContext(sandbox);vm.runInContext(html.slice(start,end),sandbox);
const step=900000,base=at-20*step,bars=Array.from({length:22},(_,i)=>({openTime:base+i*step,open:4000,high:4010,low:3990,close:4002,instrument:'XAU/USD',isOpen:false}));
const fn=sandbox.window.BobMcoHistoricalFib,r=fn(bars,at,'15m');assert(r.available);assert.equal(used.length,20);assert(used.every(b=>b.openTime+step<=at));assert.equal(r.goldPrice,4002);assert.equal(r.asOf,at);
assert(!fn(bars.filter((_,i)=>i!==10),at,'15m').available);
assert(!fn(bars.map(b=>({...b,observedOnly:true})),at,'15m').available);
assert(!fn(bars.map(b=>({...b,instrument:'GC=F'})),at,'15m').available);
assert(!fn(bars.slice(0,10),at,'15m').available);
console.log('MCO comparison: signed delta, matching evidence, historical filtering and gaps verified');
{
const {estimateTime}=require('./mco_comparison.js');
const quote={price:4200,tolerance:.5},end=at,oneMinute=60000;
const observed=[0,1,2,3,4].map(i=>({openTime:end-(5-i)*oneMinute,instrument:'XAU/USD',isOpen:false,open:4100,high:4105,low:4095,close:4101}));
observed[2]={...observed[2],open:4199,high:4201,low:4198,close:4200};
const uncertain={instrument:'XAU/USD',currency:'USD',timeframe:'15m',currentGoldQuote:quote};
const pub={...item,publishedAt:end/1000};
let est=estimateTime(uncertain,pub,[{'1m':observed}],end+1);
assert.equal(est.kind,'estimated');assert.equal(est.at,end-2.5*oneMinute);assert.equal(est.ranges.length,1);assert(est.coverage<.01);
assert.equal(estimateTime({...uncertain,timeConflict:true},pub,[{'1m':observed}],end+1).kind,'unavailable');
assert.equal(estimateTime(uncertain,item,[{'1m':observed}],end+1).kind,'unavailable');
assert.equal(estimateTime({...uncertain,currentGoldQuote:null},pub,[{'1m':observed}],end+1).kind,'unavailable');
const repeated=observed.map(b=>({...b}));repeated[4]={...repeated[4],open:4199,high:4201,low:4198,close:4200};
assert.equal(estimateTime(uncertain,pub,[{'1m':repeated}],end+1).kind,'ambiguous');
assert.equal(estimateTime(uncertain,pub,[{'1m':observed.map(b=>({...b,observedOnly:true}))}],end+1).kind,'unavailable');
const future=observed.map(b=>({...b,openTime:b.openTime+10*oneMinute}));assert.equal(estimateTime(uncertain,pub,[{'1m':future}],end+1).kind,'unavailable');
// A confirmed time always wins, even when the price points to another time.
const confirmed=compare({...pub,mcoFibonacci:[{...mark,comparisonContext:{...ctx,currentGoldQuote:quote}}]},[{'1m':observed}],calc,end+1)[0];assert.equal(confirmed.timing.kind,'confirmed');assert.equal(confirmed.context.analysisAt,at);
const estimated=compare({...pub,mcoFibonacci:[{...mark,comparisonContext:uncertain}]},[{'1m':observed}],(bars,t)=>({available:true,levels:{r618:4020},goldPrice:4200}),end+1)[0];assert.equal(estimated.timing.kind,'estimated');assert.equal(estimated.percent,.5);
console.log('Estimated time: original-time priority, repeated-price ambiguity, provenance and future exclusion verified');

}
