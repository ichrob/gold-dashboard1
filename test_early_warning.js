const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('function earlyWarningContext('),end=html.indexOf('function renderEarlyImpulseStatus()',start);
const step=300000,now=Date.UTC(2026,9,20,14,50),endAt=now;
function bundle(side){return {history:{bars_by_tf:{'5m':Array.from({length:110},(_,i)=>({openTime:endAt-(110-i)*step,open:100,close:100,high:102,low:98,isOpen:false})), '15m':[]}}};}
function evaluate(b,signals,t=now,unavailable=false){
 const env={Intl,Date,earlyImpulseContext:(input,at)=>unavailable?{available:false,reason:'stale'}:
  ({available:true,direction:signals[at]||'NEUTRAL',barAt:at-step,extensionRisk:false,reason:'fixture'})};
 vm.createContext(env);vm.runInContext(html.slice(start,end),env);return env.earlyWarningContext(b,t);
}
for(const side of ['LONG','SHORT']){
 const b=bundle(side),signals={[now-step]:side};
 const held=evaluate(b,signals);
 assert.equal(held.state,'watch');assert.equal(held.direction,side);
 assert.equal(held.signalBarAt,now-step);assert.equal(held.affectsApproval,false);
 assert.equal(evaluate(b,{[now]:side}).state,'active');
 assert.equal(evaluate(b,signals,now,true).state,'unavailable','stale data must immediately hide direction');
 b.history.bars_by_tf['5m'].at(-1).close=side==='SHORT'?103:97;
 assert.equal(evaluate(b,signals).state,'withdrawn');
 assert.equal(evaluate(b,signals).direction,'NEUTRAL');
 assert.equal(evaluate(bundle(side),{[now-3*step]:side}).state,'expired','exact expiry boundary');
 assert.equal(evaluate(bundle(side),{[now-step]:side,[now]:side==='SHORT'?'LONG':'SHORT'}).direction,side==='SHORT'?'LONG':'SHORT');
 const withOpen=bundle(side);withOpen.history.bars_by_tf['5m'].push({openTime:now,isOpen:true,close:10000});
 assert.equal(evaluate(withOpen,signals).state,'watch','unfinished candle cannot invalidate');
}
assert.equal(evaluate(bundle(),{}).state,'waiting');
assert.equal(evaluate(bundle(),{},Date.UTC(2026,9,24,12)).state,'paused');
assert(html.includes("byId('bobNextStep').after(earlyWarning)"));
assert(!html.includes("fold(byId('earlyImpulseStatus')"));
console.log('Continuous warning: bidirectional lifecycle, invalidation, expiry, stale data, weekend, open-candle and visibility checks passed');

const worker=require('./background_analysis.js').evaluate({bundle:{history:{bars_by_tf:{}}}});
assert.equal(worker.earlyWarning.state,'unavailable');
assert.equal(worker.earlyWarning.monitoring,true);
assert.equal(worker.direction,'NEUTRAL');
