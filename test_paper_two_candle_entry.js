'use strict';
const assert=require('node:assert/strict');
const E=require('./paper_two_candle_entry.js');
const NOW=Date.parse('2026-11-18T11:10:30Z'),STEP=300000,FIFTEEN=900000;
const SOURCE='biquote · XAU/USD Broker/MT5';
function fixture(side){
 const sign=side==='LONG'?1:-1;
 const last=Math.floor(NOW/STEP)*STEP-STEP,mid=Math.floor(NOW/FIFTEEN)*FIFTEEN-FIFTEEN;
 const candle=(openTime,open,close,source=SOURCE)=>({
  openTime,open,close,high:Math.max(open,close)+.3,
  low:Math.min(open,close)-.3,instrument:'XAU/USD',
  source,estimated:false,isOpen:false,providerIsOpen:false
 });
 const five=[candle(last-STEP,4000-2*sign,4000-sign),
  candle(last,4000-sign,4000)];
 const fifteen=[candle(mid,4000-3*sign,4000)];
 const price=4000+.1*sign;
 const bundle={spots:{xaus:price,spot_price_as_of:new Date(NOW-15000).toISOString(),
  is_genuine_xauusd_spot:true},history:{bars_by_tf:{'5m':five,'15m':fifteen}}};
 const opts={bundle,now:NOW,ready:true,priceFresh:true,price,
  trendContext:{available:true,intact:true,direction:side},
  dmi:{frames:{'15m':{available:true,direction:side},
               '1h':{available:true,direction:side}}},
  paperRisk:{available:true,atr:5,paperOnly:true},
  makePlan:(d,p)=>({stop:p-sign*7.5,target:p+sign*15,entrySuitable:true})};
 return opts;
}
for(const side of ['LONG','SHORT']){
 const good=fixture(side),out=E.evaluate(good);
 assert.equal(out.status,'ready',side+': '+out.reason);
 assert.equal(out.direction,side);
 assert.equal(out.paperOnly,true);
 assert.equal(out.comparisonOnly,true);
 assert.equal(out.realOrders,false);
 assert.equal(out.liveRulesChanged,false);
 assert.equal(out.productApproved,false);
 assert.equal(out.entryApproved,false);
 assert.equal(out.plan.kind,'candidate');
 assert.equal(out.plan.source,E.SOURCE);
 assert.equal(out.plan.direction,side);
 assert(out.plan.experimental&&out.plan.paperOnly);
 assert(Math.abs(out.plan.target-out.plan.entry)>=2*Math.abs(out.plan.entry-out.plan.stop));
 assert(Number.isFinite(out.barAt)&&out.sourceAt===NOW-15000);
 const reject=(label,mutate)=>{
  const x=fixture(side);mutate(x);
  const result=E.evaluate(x);
  assert.equal(result.status,'waiting',label+': '+JSON.stringify(result));
  assert.equal(result.direction,'NEUTRAL',label);
  assert.equal(result.plan,null,label);
  assert.equal(result.entryApproved,false,label);
 };
 reject('wrong higher trend',x=>x.trendContext.direction=side==='LONG'?'SHORT':'LONG');
 reject('weak 1h trend',x=>x.trendContext.intact=false);
 reject('15m DMI conflict',x=>x.dmi.frames['15m'].direction=side==='LONG'?'SHORT':'LONG');
 reject('1h DMI unknown',x=>x.dmi.frames['1h'].available=false);
 reject('estimated last candle',x=>x.bundle.history.bars_by_tf['5m'][1].estimated=true);
 reject('open last candle',x=>x.bundle.history.bars_by_tf['5m'][1].isOpen=true);
 reject('unknown source',x=>x.bundle.history.bars_by_tf['5m'][0].source='untrusted-feed');
 reject('missing 5m period',x=>x.bundle.history.bars_by_tf['5m'][0].openTime-=STEP);
 reject('wrong candle direction',x=>{
  const b=x.bundle.history.bars_by_tf['5m'][1];b.open=b.close+Math.sign(b.close-b.open);b.high=Math.max(b.open,b.close)+.3;
 });
 reject('old spot',x=>x.bundle.spots.spot_price_as_of=new Date(NOW-61000).toISOString());
 reject('spot not genuine',x=>x.bundle.spots.is_genuine_xauusd_spot=false);
 reject('bar/spot deviation',x=>{x.price+=7;x.bundle.spots.xaus=x.price;});
 reject('risk unavailable',x=>x.paperRisk.available=false);
 reject('too small 2R target',x=>{x.makePlan=(dir,p)=>({stop:p-7.5*(side==='LONG'?1:-1),target:p+6*(side==='LONG'?1:-1),entrySuitable:true});});
 reject('target obstacle',x=>x.makePlan=()=>({stop:3990,target:4020,entrySuitable:false,warning:'Mindest-CRV nicht erreicht'}));
 reject('no independent plan builder',x=>delete x.makePlan);
 reject('malformed newer closed candle',x=>{
  const last=x.bundle.history.bars_by_tf['5m'].at(-1);
  x.bundle.history.bars_by_tf['5m'].push({...last,estimated:true});
 });
}
console.log('Two original 5m paper hypothesis: LONG/SHORT, 15m+1h trend, 2R, stale/KO-independent safety, no live mutation');
