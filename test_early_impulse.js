const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('function earlyImpulseContext('),end=html.indexOf('function renderEarlyImpulseStatus()',start);
assert(start>=0&&end>start,'early impulse function missing');
const env={};vm.createContext(env);vm.runInContext(html.slice(start,end),env);
const observe=(bundle,now)=>env.earlyImpulseContext(bundle,now);
const M=60000,now=Date.UTC(2026,9,12,10,35);
function bars(tf,side=1){
 const step=tf==='5m'?5*M:15*M;
 const latest=tf==='5m'?now-step:now-20*M;
 return Array.from({length:100},(_,i)=>{
  const p=i>0&&i>=97?side*(i-96)*(tf==='5m'?3:1):0.12*Math.sin(i/3);
  const prev=i>0&&i-1>=97?side*(i-1-96)*(tf==='5m'?3:1):i>0?0.12*Math.sin((i-1)/3):0;
  const open=4200+prev,close=4200+p;
  return {instrument:'XAU/USD',openTime:latest-(99-i)*step,open,close,high:Math.max(open,close)+1,low:Math.min(open,close)-1,isOpen:false};
 });
}
const bundle=(dir5,dir15=dir5)=>({history:{bars_by_tf:{'5m':bars('5m',dir5),'15m':bars('15m',dir15)}}});
for(const [side,direction] of [[1,'LONG'],[-1,'SHORT']]){
 const result=observe(bundle(side),now);
 assert.equal(result.available,true);
 assert.equal(result.direction,direction);
 assert.equal(result.comparisonOnly,true);
 assert.equal(result.affectsApproval,false);
 assert.equal(result.version,'early-impulse-v1');
 assert.equal(result.barAt,now-5*M);
 assert.equal(result.extensionRisk,true);
}
const neutral=bundle(1,-1);
assert.equal(observe(neutral,now).direction,'NEUTRAL','timeframes must align');
const weak=bundle(1);
for(const tf of ['5m','15m']){
 for(const b of weak.history.bars_by_tf[tf]){
  b.open=4200;b.close=4200;b.high=4201;b.low=4199;
 }
}
const quiet=observe(weak,now);
assert.equal(quiet.available,true);assert.equal(quiet.direction,'NEUTRAL');
const open=bundle(-1);
open.history.bars_by_tf['5m'].push({...open.history.bars_by_tf['5m'].at(-1),openTime:now,open:999999,close:999999,high:999999,low:999999,isOpen:true});
assert.equal(observe(open,now).direction,'SHORT','unfinished candle must not change the decision');
for(const kind of ['stale','missing','gap','mixed','estimated','badPrice','future']){
 const b=bundle(1);let later=now;
 if(kind==='stale')later+=35*M;
 if(kind==='missing')b.history.bars_by_tf['15m'].pop();
 if(kind==='gap')b.history.bars_by_tf['5m'].at(-2).openTime-=10*M;
 if(kind==='mixed')b.history.bars_by_tf['5m'].at(-1).instrument='GC=F';
 if(kind==='estimated')b.history.bars_by_tf['15m'].at(-1).estimated=true;
 if(kind==='badPrice')b.history.bars_by_tf['5m'].at(-1).low=5000;
 if(kind==='future')b.history.bars_by_tf['5m'].at(-1).openTime=later+5*M;
 const r=observe(b,later);
 assert.equal(r.available,false,kind);
 assert.equal(r.direction,'NEUTRAL',kind);
}
assert(html.includes('Frühwarnung')||html.includes('FRÜHWARNUNG'));
assert(html.includes('earlyImpulse:earlyImpulseContext(bundle)'));
console.log('Bidirectional early impulse: direction symmetry, quiet, disagreement, closed-only, stale/gap/mixed/source/price guards and shadow isolation passed');
