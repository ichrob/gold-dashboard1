'use strict';
const assert=require('node:assert/strict');
const {forPaper}=require('./paper_risk_reference.js');
const M=60000, STEP=5*M, now=Date.parse('2026-11-17T08:35:00Z');
const SOURCE='biquote · XAU/USD Broker/MT5';
function fixture(){
 const rows=Array.from({length:40},(_,i)=>{
   const close=3900+i*.03;
   return {openTime:now-(40-i)*STEP,open:close-.02,high:close+.6,
     low:close-.6,close,isOpen:false,providerIsOpen:false,
     estimated:false,instrument:'XAU/USD',source:SOURCE};
 });
 return {history:{bars_by_tf:{'5m':rows}}};
}
function assess(x,primary={available:false,reason:'strict-15m-missing'}){
 return forPaper(x,now,primary,rows=>rows.length===40?1.2:null);
}
const good=fixture();
const before=JSON.stringify(good);
const out=assess(good);
assert.equal(out.available,true,out.reason);
assert.equal(out.paperOnly,true);
assert.equal(out.liveTradeApproved,false);
assert.equal(out.estimated,false);
assert.equal(out.timeframe,'5m');
assert.equal(out.basis,'closed-original-5m-v1');
assert.equal(out.confirmedBars,40);
assert.equal(out.atr,1.2);
assert.equal(JSON.stringify(good),before,'reference must not mutate source candles');
const strict={available:true,atr:9.3,bars:[{openTime:1}],timeframe:'15m'};
const preferred=assess(good,strict);
assert.equal(preferred.available,true);
assert.equal(preferred.timeframe,'15m','existing 15m primary must be preferred');
assert.equal(preferred.atr,9.3);
assert.equal(preferred.paperOnly,true);
for(const mutate of [
 x=>x.history.bars_by_tf['5m'].pop(),
 x=>x.history.bars_by_tf['5m'][16].openTime+=STEP,
 x=>x.history.bars_by_tf['5m'][15].estimated=true,
 x=>x.history.bars_by_tf['5m'][15].source='XAUS · datierte XAU/USD-Historie',
 x=>x.history.bars_by_tf['5m'][15].source='unknown',
 x=>x.history.bars_by_tf['5m'][15].isOpen=true,
 x=>x.history.bars_by_tf['5m'][15].providerIsOpen=true,
 x=>x.history.bars_by_tf['5m'][15].instrument='GCZ26',
 x=>x.history.bars_by_tf['5m'][15].close=-1,
 x=>x.history.bars_by_tf['5m'][15].high=-1,
 x=>x.history.bars_by_tf['5m'][15].openTime+=1
]){
 const corrupted=fixture();mutate(corrupted);
 const result=assess(corrupted);
 assert.equal(result.available,false,JSON.stringify(result));
}
const stale=fixture();
for(const row of stale.history.bars_by_tf['5m'])row.openTime-=4*STEP;
assert.equal(assess(stale).available,false,'old real candles are not current');
const fakeSource=fixture();for(const row of fakeSource.history.bars_by_tf['5m'])delete row.source;
assert.equal(assess(fakeSource).available,false,'unidentified source cannot be paper reference');
assert.equal(forPaper(good,now,{available:false},()=>0).available,false);
assert.equal(forPaper(good,now-1000,{available:false},()=>NaN).available,false);
console.log('Paper-only original 5m risk fallback: strict source, clocks, 40 closes, risk, stale, primary isolation OK');
