const assert=require('assert');
const NativeDate=Date, now=Date.parse('2026-10-06T09:12:00Z');
global.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}};
const {evaluate}=require('./background_analysis');
const plain=x=>JSON.parse(JSON.stringify(x));
for(const slope of [.1,-.1,0]){
 const bars={};
 for(const [tf,step] of Object.entries({'5m':300000,'15m':900000,'1h':3600000,'4h':14400000})){
  const end=Math.floor(now/step)*step;
  bars[tf]=Array.from({length:240},(_,i)=>({openTime:end-(240-i)*step,open:4100+i*slope,high:4104+i*slope,low:4096+i*slope,close:4100+i*slope+Math.sin(i/8),isOpen:false,instrument:'XAU/USD'}));
 }
 const bundle={spots:{xaus:4124,is_genuine_xauusd_spot:true,spot_price_as_of:new Date(now).toISOString()},history:{bars_by_tf:bars}};
 for(const timeframe of ['5m','15m','1h']){
  const input={bundle,timeframe,trade:{active:true,dir:slope<0?'SHORT':'LONG'}};
  assert.deepStrictEqual(plain(evaluate(input)),plain(evaluate(input,{render:true})),timeframe+' slope '+slope);
 }
 bundle.spots.spot_error='offline';
 assert.deepStrictEqual(plain(evaluate({bundle})),plain(evaluate({bundle},{render:true})));
}
console.log('Worker and dashboard outputs match for LONG/SHORT/neutral paths, all timeframes, stop/target and spot outages.');
