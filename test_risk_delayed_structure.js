'use strict';
const assert=require('node:assert/strict'),r=require('./risk_workspace');
const now=Date.parse('2026-10-29T19:58:30Z');
function fixture(dir){
 const last=now-150000;
 return {spots:{xaus:dir==='LONG'?4001.2:3998.8,is_genuine_xauusd_spot:true,
  spot_price_as_of:new Date(now-10000).toISOString()},history:{bars_by_tf:{'1m':
  Array.from({length:21},(_,i)=>({openTime:last-(20-i)*60000,instrument:'XAU/USD',source:'observed',
   open:4000,high:4001,low:3999,close:4000}))}}};
}
for(const dir of ['LONG','SHORT']){
 const b=fixture(dir),before=JSON.stringify(b);
 assert.equal(r.analyze(b,now).ready,false);
 const s=r.analyzePaper(b,now);
 assert.equal(s.ready,true);assert.equal(s.direction,dir);assert.equal(s.stage,'VORWARNUNG');
 assert.equal(s.dataMode,'estimate');assert.equal(s.estimateMethod,'spot-lagged-minute-context-v1');
 assert.equal(s.at,now-10000);assert.equal(s.sourceAt,now-10000);assert.equal(s.barAt,now-150000);
 assert.equal(JSON.stringify(b),before);
 const backup=fixture(dir);backup.risk_spot_backup={observed:true,instrument:'XAU/USD',source:'XAUS · XAU/USD Spot',price:backup.spots.xaus,at:backup.spots.spot_price_as_of};
 backup.spots.spot_error='primary unavailable';
 assert.equal(r.analyzePaper(backup,now).referenceSource,'XAUS · XAU/USD Spot');
 for(const mutate of [
  b=>b.spots.spot_price_as_of=new Date(now-60001).toISOString(),
  b=>b.spots.spot_price_as_of=new Date(now+1).toISOString(),
  b=>b.history.bars_by_tf['1m'].forEach(x=>x.openTime-=60000),
  b=>b.history.bars_by_tf['1m'][10].openTime-=60000,
  b=>b.history.bars_by_tf['1m'][20].providerIsOpen=true,
  b=>b.history.bars_by_tf['1m'][10].estimated=true,
  b=>b.history.bars_by_tf['1m'][10].instrument='GC=F']){
   const bad=fixture(dir);mutate(bad);assert.equal(r.analyzePaper(bad,now).ready,false);
 }
}
console.log('Delayed structure: LONG/SHORT, backup, immutable source clocks, expiry and invalid data gates passed.');

// At a minute boundary, the newest completed bar can be newer than the spot.
// A genuine backup must still use its own preceding complete structure.
for(const dir of ['LONG','SHORT']){
 const clock=Date.parse('2026-10-30T12:00:10Z'),spotAt=clock-20000;
 const bars=Array.from({length:23},(_,i)=>({openTime:Date.parse('2026-10-30T11:37:00Z')+i*60000,
  instrument:'XAU/USD',source:'observed',open:4000,high:4001,low:3999,close:4000}));
 const bundle={spots:{spot_error:'primary unavailable'},risk_spot_backup:{observed:true,
  instrument:'XAU/USD',source:'XAUS · XAU/USD Spot',price:dir==='LONG'?4001.2:3998.8,
  at:new Date(spotAt).toISOString()},history:{bars_by_tf:{'1m':bars}}};
 const before=JSON.stringify(bundle),signal=r.analyzePaper(bundle,clock);
 assert.equal(signal.ready,true);assert.equal(signal.direction,dir);
 assert.equal(signal.dataMode,'estimate');assert.equal(signal.at,spotAt);
 assert.equal(signal.barAt,Date.parse('2026-10-30T11:58:00Z'));
 assert.equal(signal.estimateMethod,'spot-lagged-minute-context-v1');
 assert.equal(JSON.stringify(bundle),before);
 // A timestamp-complete bar can remain provider-open briefly at the boundary.
 // It must not suppress the preceding complete 21-bar structure.
 bars.at(-1).providerIsOpen=true;
 assert.deepEqual(r.analyzePaper(bundle,clock),signal);
 // Neither a future bar value nor a later close can influence this context.
 bars.at(-1).close=4000.9;
 assert.deepEqual(r.analyzePaper(bundle,clock),signal);
 assert.equal(r.analyzePaper(bundle,clock+60001).ready,false);
}
