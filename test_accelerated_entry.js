const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8'),end=Date.UTC(2026,9,15,8,0),now=end+120000;
const env={Date,Number,Math,minuteEntryContext:(_,s)=>({available:true,direction:s.dir}),atr:()=>2,ema:()=>100};
vm.createContext(env);
vm.runInContext(html.slice(html.indexOf('function trendFollowingSignal('),html.indexOf('// Shared by the browser and the headless worker.')),env);
function fixture(sign){
 const price=x=>100+sign*x;
 const bar=(at,o,c)=>({openTime:at,open:price(o),close:price(c),high:Math.max(price(o),price(c))+.1,low:Math.min(price(o),price(c))-.1,isOpen:false,instrument:'XAU/USD'});
 return {history:{bars_by_tf:{'5m':[bar(end-300000,0,.3)],'1m':[bar(end,.4,.6),bar(end+60000,.6,.8)]}}};
}
for(const [sign,side] of [[1,'LONG'],[-1,'SHORT']]){
 const state={dir:'NEUTRAL',pending:side,preparedDirection:side,count:1,lastAt:end-300000,reason:'prepared'};
 const run=(b=fixture(sign),s=state,t=now)=>env.acceleratedMinuteConfirmation(b,s,t);
 assert.equal(run().dir,side);assert.equal(run().confirmationAt,now);
 assert.equal(run(undefined,undefined,end+300000),null);
 assert.equal(run(undefined,{...state,count:0}),null);
 for(const kind of ['open','gap','old','estimated','wrong','wick','retreat','extended']){
  const b=fixture(sign),r=b.history.bars_by_tf['1m'];
  if(kind==='open')r[1].isOpen=true;
  if(kind==='gap')r[0].openTime-=60000;
  if(kind==='old')r.forEach(x=>x.openTime-=120000);
  if(kind==='estimated')r[1].estimated=true;
  if(kind==='wrong')r[1].instrument='GC';
  if(kind==='wick')r[1].close=100;
  if(kind==='retreat')r[1].close=r[0].close;
  if(kind==='extended')r[1].close=100+sign*5;
  assert.equal(run(b),null,side+' '+kind);
 }
 env.fiveMinuteConfirmation=()=>state;
 env.sustainedTrendContext=()=>({available:true,intact:true,direction:side,reason:'trend'});
 assert.equal(env.trendFollowingSignal(fixture(sign),now).dir,side);
 env.sustainedTrendContext=()=>({available:true,intact:true,direction:sign===1?'SHORT':'LONG',reason:'opposite'});
 assert.equal(env.trendFollowingSignal(fixture(sign),now).dir,'NEUTRAL');
 env.sustainedTrendContext=()=>({available:false,intact:false,reason:'missing'});
 assert.equal(env.trendFollowingSignal(fixture(sign),now).dir,'NEUTRAL');
 env.minuteEntryContext=()=>({available:false});
 assert.equal(run(),null);
 env.minuteEntryContext=(_,s)=>({available:true,direction:s.dir});
}
console.log('Earlier LONG/SHORT: two post-signal closes; timing, gap, open, source, wick, retreat, extension and higher-trend vetoes pass.');
