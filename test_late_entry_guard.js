const assert=require('assert');
const guard=require('./late_entry_guard.js');
const M=60000,now=Date.UTC(2026,9,16,10,30,0);
function frame(step,drift=1,burst=0){
 const last=now-step;
 return Array.from({length:100},(_,i)=>{
   const base=4200+drift*(0.11*i)+0.32*Math.sin(i*0.8);
   const extra=i>96?(i-96)*burst*drift:0;
   const close=base+extra,open=4200+drift*(0.11*(i-1))+0.32*Math.sin((i-1)*0.8)+(i>97?(i-97)*burst*drift:0);
   return {openTime:last-(99-i)*step,open,close,high:Math.max(open,close)+1.2,
           low:Math.min(open,close)-1.2,isOpen:false,instrument:'XAU/USD'};
 });
}
function bundle(direction='LONG',burst=0){
 const side=direction==='LONG'?1:-1;
 const five=frame(5*M,side,burst),fifteen=frame(15*M,side,0);
 // 15m finished at the most recent true aligned 15m boundary.
 const latest15=Math.floor(now/(15*M))*(15*M)-15*M;
 const delta=latest15-fifteen.at(-1).openTime;
 fifteen.forEach(b=>b.openTime+=delta);
 return {spots:{xaus:five.at(-1).close+side*.04,
                spot_price_as_of:new Date(now-10000).toISOString(),
                is_genuine_xauusd_spot:true,spot_error:null},
         history:{bars_by_tf:{'5m':five,'15m':fifteen}}};
}
for(const side of ['LONG','SHORT']){
 const b=bundle(side),fresh=guard.check(b,side,now,now-5*M);
 assert.equal(fresh.available,true,side+' '+fresh.reason);
 assert.equal(fresh.allowed,true,side+' '+JSON.stringify(fresh));
 assert.equal(fresh.late,false);
 const late=guard.check(b,side,now,now-31*M);
 assert.equal(late.available,true);
 assert.equal(late.allowed,false,'old '+side);
 assert.match(late.reason,/15 Minuten/);
 const blown=bundle(side,3.2),reject=guard.check(blown,side,now,now-3*M);
 assert.equal(reject.allowed,false,'chase '+side);
 assert.match(reject.reason,/ATR/);
}
// Separate closed-5m follow-through may re-open an older same-direction trend.
// It must NOT refresh the timestamp of the older 15m confirmation.
function followThroughBundle(direction){
 const b=bundle(direction),sign=direction==='LONG'?1:-1;
 const five=b.history.bars_by_tf['5m'],p=five.at(-3).close;
 function setBar(bar,open,close){
  bar.open=open;bar.close=close;bar.high=Math.max(open,close)+.05;
  bar.low=Math.min(open,close)-.05;
 }
 setBar(five.at(-2),p,p+sign*.8);
 setBar(five.at(-1),p+sign*.8,p+sign*1.6);
 b.spots.xaus=five.at(-1).close+sign*.04;
 return b;
}
for(const direction of ['LONG','SHORT']){
 const b=followThroughBundle(direction),r=guard.check(b,direction,now,now-31*M);
 assert.equal(r.allowed,true,direction+' '+JSON.stringify(r));
 assert.equal(r.setup,'fresh-5m-continuation');
 assert.equal(r.freshContinuation,true);
 assert(Object.values(r.continuationChecks).every(Boolean));
 assert.equal(r.freshContinuationAt,now);
 assert.equal(r.signalAgeMinutes,31); // original 15m clock is not forged
 const noBreak=JSON.parse(JSON.stringify(b));
 const prev=noBreak.history.bars_by_tf['5m'].at(-2),latest=noBreak.history.bars_by_tf['5m'].at(-1);
 if(direction==='LONG')prev.high=latest.close+.5;
 else prev.low=latest.close-.5;
 assert.equal(guard.check(noBreak,direction,now,now-31*M).allowed,false,'no real close breakout');
 assert.equal(guard.check(noBreak,direction,now,now-31*M).continuationChecks.closedBreakout,false);
 const old=JSON.parse(JSON.stringify(b)),later=now+2*M;
 old.spots.spot_price_as_of=new Date(later-10000).toISOString();
 assert.equal(guard.check(old,direction,later,later-31*M).allowed,false,'2-minute-old continuation cannot be reused');
}
const base=bundle('LONG');
const tamper=[
 b=>{b.spots.spot_price_as_of=new Date(now-130000).toISOString();},
 b=>{b.spots.is_genuine_xauusd_spot=false;},
 b=>{b.history.bars_by_tf['5m'].at(-1).instrument='GC=F';},
 b=>{b.history.bars_by_tf['5m'].at(-2).openTime-=5*M;},
 b=>{b.history.bars_by_tf['15m'].at(-1).estimated=true;},
 b=>{b.spots.xaus=b.spots.xaus+50;},
 b=>{b.history.bars_by_tf['5m'].at(-1).low=5000;},
 b=>{b.history.bars_by_tf['5m']=[];}
];
for(const [i,change] of tamper.entries()){
 const b=JSON.parse(JSON.stringify(base));change(b);
 const r=guard.check(b,'LONG',now,now-5*M);
 assert.equal(r.allowed,false,'source rejection '+i);
}
assert.equal(guard.check(base,'NEUTRAL',now).allowed,false);
console.log('Late entry protection: timely LONG/SHORT, aged, chase, invalid source/time, mixed basis and price divergence OK');
// Paper 2.5 ATR changes only the distance veto. Live API ignores extra arguments.
for(const side of ['LONG','SHORT']){
 let found=false;
 for(let burst=.1;burst<3;burst+=.05){
  const b=bundle(side,burst),live=guard.check(b,side,now,now-3*M);
  const paper=guard.checkPaper25(b,side,now,now-3*M);
  if(live.deviationAtr>2&&live.deviationAtr<2.5&&paper.allowed){
   found=true;assert.equal(live.allowed,false);assert.equal(paper.paperOnly,true);
   assert.deepStrictEqual(guard.check(b,side,now,now-3*M,true),live);
   assert.equal(guard.checkPaper25(b,side,now,now-31*M).allowed,false);
   b.spots.spot_price_as_of=new Date(now-61000).toISOString();
   assert.equal(guard.checkPaper25(b,side,now,now-3*M).allowed,false);
   break;
  }
 }
 assert(found,'paper-only stretched '+side+' case exercised');
}
// Isolated 5,000 EUR experiment removes only the direct distance rejection.
for(const side of ['LONG','SHORT']){
 const b=bundle(side,1.8); b.history.bars_by_tf['5m'].at(-2)[side==='LONG'?'high':'low']=b.history.bars_by_tf['5m'].at(-1)[side==='LONG'?'high':'low']; const opts={paperProfile:'noema5000nov'};
 const base=guard.check(b,side,now,now-3*M);
 const test=guard.checkPaperNoEma(b,side,now,now-3*M);
 assert.match(base.reason,/Preis über 1,5 ATR/);
 assert.equal(test.allowed,true,JSON.stringify(test));
 assert.equal(test.emaDistanceDisabled,true);
 assert.equal(guard.checkPaperNoEma(b,side,now,now-31*M).allowed,false);
 assert.match(guard.checkPaperNoEma(bundle(side,6),side,now,now-3*M).reason,/2,5 ATR/);
 b.spots.spot_price_as_of=new Date(now-90000).toISOString();
 assert.equal(guard.checkPaperNoEma(b,side,now,now-3*M).available,false);
}


 // Regression: a real 1m breakout can explain a >0.8 ATR spot/5m-close gap.
 // Missing, open, estimated, stale, misidentified or countertrend 1m bars cannot.
function corroboratedMinuteBreakout(side){
 const b=bundle(side),s=side==='LONG'?1:-1,five=b.history.bars_by_tf['5m'].at(-1),later=now+2*M;
 const firstOpen=five.close+s*1.25,firstClose=five.close+s*1.6,secondClose=five.close+s*2.5;
 const bar=(time,open,close)=>({openTime:time,open,close,
     high:Math.max(open,close)+.05,low:Math.min(open,close)-.05,
     isOpen:false,instrument:'XAU/USD'});
 b.history.bars_by_tf['1m']=[bar(now,firstOpen,firstClose),bar(now+M,firstClose,secondClose)];
 b.spots.xaus=secondClose+s*.02;
 b.spots.spot_price_as_of=new Date(later-9000).toISOString();
 return {b,later};
}
for(const side of ['LONG','SHORT']){
 const {b,later}=corroboratedMinuteBreakout(side),approved=guard.check(b,side,later,now-3*M);
 assert.equal(approved.allowed,true,side+' corroborated minute continuation: '+approved.reason);
 assert.equal(approved.available,true);
 assert(approved.deviationAtr<=1.5,'other EMA limit remains effective');
 const failures=[
   x=>{x.history.bars_by_tf['1m'].at(-1).isOpen=true;},
   x=>{x.history.bars_by_tf['1m'].at(-1).estimated=true;},
   x=>{x.history.bars_by_tf['1m'].at(-1).instrument='GC=F';},
   x=>{x.history.bars_by_tf['1m'].at(-1).openTime-=2*M;},
   x=>{x.history.bars_by_tf['1m'].at(-1).close=x.history.bars_by_tf['1m'][0].close-(side==='LONG'?1:-1)*.3;},
   x=>{x.spots.spot_price_as_of=new Date(later-70000).toISOString();},
   x=>{delete x.history.bars_by_tf['1m'];}
 ];
 failures.forEach((mutate,index)=>{
   const x=JSON.parse(JSON.stringify(b));mutate(x);
   assert.equal(guard.check(x,side,later,now-3*M).allowed,false,side+' invalid minute input '+index);
 });
}
