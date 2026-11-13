'use strict';
const assert=require('node:assert/strict');
const study=require('./entry_opportunity_study');
const late=require('./late_entry_guard');
const M=60000,now=Date.UTC(2026,10,12,12,0);
function fixture(sign=1,drift=.2,clock=now){
 const frames={};
 for(const step of [5*M,15*M]){
   const end=Math.floor(clock/step)*step;
   frames[step===5*M?'5m':'15m']=Array.from({length:100},(_,i)=>{
     const close=4000+sign*drift*i,open=close-sign*drift;
     return {openTime:end-step*(100-i),open,close,high:Math.max(open,close)+.3,
       low:Math.min(open,close)-.3,isOpen:false,instrument:'XAU/USD'};
   });
 }
 return {history:{bars_by_tf:frames},spots:{xaus:frames['5m'].at(-1).close,
   spot_price_as_of:new Date(clock).toISOString(),is_genuine_xauusd_spot:true}};
}
for(const sign of [1,-1]){
 const direction=sign===1?'LONG':'SHORT',bundle=fixture(sign),entry=bundle.spots.xaus;
 const before=JSON.stringify(bundle);
 const args={bundle,direction,now,confirmationAt:now-18*M,ready:true,riskData:{available:false},
   makePlan:()=>({entry,stop:entry-sign*5,target:entry+sign*10,available:true,entrySuitable:true})};
 const r=study.evaluate(args);
 assert.equal(r.arms.reference.allowed,false);
 assert.equal(r.arms.distance25.allowed,false); // age still blocks
 assert.equal(r.arms.age20.allowed,false); // distance still blocks
 assert.equal(r.arms.combined.allowed,true); // independently computed plan
 assert.equal(JSON.stringify(bundle),before);
 assert.equal(late.check(bundle,direction,now,now-18*M).allowed,false);
 assert.equal(study.evaluate({...args,ready:false}).status,'waiting-for-input-or-direction');
 assert.equal(study.evaluate({...args,direction:'NEUTRAL'}).status,'waiting-for-input-or-direction');
 // EMA oracle: closed-form weighted sum, independent of the recurrence in production.
 const closes=bundle.history.bars_by_tf['5m'].map(b=>b.close),q=19/21;
 const ema=closes[0]*q**99+closes.slice(1).reduce((a,c,i)=>a+c*(2/21)*q**(98-i),0);
 const g=late.checkStudy(bundle,direction,now,now,{distance:2.5,age:15});
 assert(Math.abs(g.atr5m-.8)<1e-9);
 assert(Math.abs(g.deviationAtr-sign*(entry-ema)/.8)<.006);
 const stale=structuredClone(bundle);stale.spots.spot_price_as_of=new Date(now-61000).toISOString();
 assert.equal(late.checkStudy(stale,direction,now,now,{distance:2.5,age:20}).allowed,false);
}
// The minute variant needs two CLOSED, ordered, current candles after the 5m close.
for(const sign of [1,-1]){
 const clock=now+2*M,side=sign===1?'LONG':'SHORT',b=fixture(sign,0,clock);
 b.spots.xaus=4000+sign*.6;
 b.history.bars_by_tf['1m']=[0,1].map(i=>{
   const open=4000+sign*(.31+i*.14),close=4000+sign*(.45+i*.14);
   return {openTime:now+i*M,open,close,high:Math.max(open,close)+.01,
     low:Math.min(open,close)-.01,isOpen:false,instrument:'XAU/USD'};
 });
 assert.equal(late.check(b,side,clock,clock).allowed,true); // corroborated 1m breakout now passes the live timing gate
 const withoutMinute=structuredClone(b);delete withoutMinute.history.bars_by_tf['1m'];
 assert.equal(late.check(withoutMinute,side,clock,clock).allowed,false);
 assert.equal(late.checkStudy(b,side,clock,clock,{distance:1.5,age:15,minute:true}).allowed,true);
 const bad=structuredClone(b);bad.history.bars_by_tf['1m'][1].estimated=true;
 assert.equal(late.checkStudy(bad,side,clock,clock,{distance:1.5,age:15,minute:true}).allowed,false);
 bad.history.bars_by_tf['1m'][1].estimated=false;bad.history.bars_by_tf['1m'][1].isOpen=true;
 assert.equal(late.checkStudy(bad,side,clock,clock,{distance:1.5,age:15,minute:true}).allowed,false);
}
// A single small pivot may be ignored only in the declared zone hypothesis.
const bars=Array.from({length:60},()=>({high:110,low:90,close:100}));
bars[10].high=120; bars[30].high=101;bars[28].high=100;bars[29].high=100;bars[31].high=100;bars[32].high=100;
const p={entry:100,stop:98,target:104};
assert.equal(study.zones('LONG',p,{available:true,atr:1,bars}).entrySuitable,true);
bars[40].high=101;for(const i of [38,39,41,42])bars[i].high=100;
assert.equal(study.zones('LONG',p,{available:true,atr:1,bars}).entrySuitable,false);
const mirrored=bars.map(b=>({high:200-b.low,low:200-b.high,close:200-b.close}));
assert.equal(study.zones('SHORT',{entry:100,stop:102,target:96},{available:true,atr:1,bars:mirrored}).entrySuitable,false);
console.log('Entry opportunity study: factorial gates, independent plans, math oracle, minute evidence and zones OK');
