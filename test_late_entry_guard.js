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
