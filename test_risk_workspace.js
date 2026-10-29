'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const r=require('./risk_workspace');
const now=Date.parse('2026-10-28T10:00:00Z');
function bundle(direction='LONG'){
 const bars=Array.from({length:21},(_,i)=>({openTime:now-(21-i)*60000,instrument:'XAU/USD',open:4000,high:4001,low:3999,close:4000}));
 for(const b of bars.slice(-2)){b.close=direction==='LONG'?4003:3997;b.high=Math.max(4001,b.close);b.low=Math.min(3999,b.close);}
 return {spots:{is_genuine_xauusd_spot:true,xaus:direction==='LONG'?4003.2:3996.8,spot_price_as_of:new Date(now).toISOString()},history:{bars_by_tf:{'1m':bars}}};
}
for(const dir of ['LONG','SHORT']){const s=r.analyze(bundle(dir),now);assert.equal(s.direction,dir);assert.equal(s.stage,'BESTÄTIGT');}
for(const mutate of [b=>b.spots.spot_price_as_of=new Date(now-60001).toISOString(),b=>b.spots.spot_price_as_of=new Date(now+1).toISOString(),b=>b.spots.is_genuine_xauusd_spot=false,b=>b.history.bars_by_tf['1m'][10].openTime-=60000,b=>b.history.bars_by_tf['1m'][20].high=1,b=>b.history.bars_by_tf['1m'][20].instrument='GC=F',b=>b.spots.xaus=Infinity,b=>b.history.bars_by_tf['1m']=[]]){const b=bundle();mutate(b);assert.equal(r.analyze(b,now).ready,false);}
const neutral=bundle();for(const b of neutral.history.bars_by_tf['1m']){b.close=4000;b.high=4001;b.low=3999;}neutral.spots.xaus=4000;assert.equal(r.analyze(neutral,now).direction,'ABWARTEN');
const state=r.analyze(bundle(),now),trade={tradeId:'test',active:true,dir:'LONG',entry:4000,stop:3990};
let w=r.monitor({},trade,state,now);const stop=w.stop;
w=r.monitor(w,trade,{...state,atr:10,spot:4004,at:now+1000},now+1000);assert(w.stop>=stop,'volatility cannot loosen stop');
w=r.monitor(w,trade,{...state,spot:3990,at:now+2000},now+2000);assert.equal(w.action,'AUSSTIEG PRÜFEN');
w=r.monitor(w,trade,{...state,spot:4010,at:now+3000},now+3000);assert.equal(w.action,'AUSSTIEG PRÜFEN','warning latches until trade closes');
assert.equal(r.monitor(w,{active:false},state).active,false);
assert.equal(r.monitor(w,trade,{ready:false,reason:'stale'}).action,'ÜBERWACHUNG EINGESCHRÄNKT');
assert.equal(r.monitor(w,{...trade,tradeId:'another'}, {ready:false,reason:'stale'}).stop,undefined,'Never carry another trade stop across a data gap');
assert.equal(r.monitor(w,{...trade,test:true},state).action,'SIMULATION');
const short={...trade,tradeId:'short',dir:'SHORT',stop:4010};let sw=r.monitor({},short,{...state,spot:4000},now);const shortStop=sw.stop;sw=r.monitor(sw,short,{...state,atr:20,spot:3999,at:now+1000},now+1000);assert(sw.stop<=shortStop);
const ctx={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);ctx.window.BobProductEvidence=require('./product_evidence_contract');const api=ctx.window.BobDegiro;
const market={atr:10,trend:'LONG',trend2:'LONG',mtf:'LONG',rsi:64,hist:2,adx:28,momentum:1};
// Public synthetic fixtures; no private account/list evidence.
const products=[['DE000FG14AV8',8],['DE000FG4JXV7',20],['DE000SQ02JQ6',12]].map(([isin,leverage])=>({isin,name:'Gold Turbo Long',isinConfirmed:true,productDirection:'LONG',price:7.5,leverage,ko:3800}));
const ranked=r.ranking(products,state,market,api,now);assert.deepEqual(ranked.map(x=>x.p.leverage),[20,12]);
assert.equal(r.ranking(products,{ready:false},market,api,now).length,0);
assert.equal(r.ranking(products,{...state,direction:'ABWARTEN'},market,api,now).length,0);
for(const bad of [{...products[0],ko:3999},{...products[0],name:'Faktor Gold'},{...products[0],productDirection:'SHORT'},{...products[0],isinConfirmed:false}])assert.equal(r.ranking([bad],state,market,api,now).length,0);
assert.equal(r.ranking([products[0],products[0]],state,market,api,now).length,1);
const html=r.markup({...state,reason:'<script>bad()</script>'},ranked,{},'SHORT');assert(!html.includes('<script>'));assert(html.includes('GEGEN DEN HAUPTTREND'));assert(html.includes('NICHT ALS DEGIRO-AUSFÜHRUNG BESTÄTIGT'));
const page=fs.readFileSync('Bob.html','utf8');for(const m of page.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
assert(page.includes("['risk','⚡','Risiko']"));assert(page.includes('mount(panels.risk)'));assert(fs.readFileSync('server.py','utf8').includes('"/risk_workspace.js"'));
console.log('Risk: direction, stale/future/gapped data, KO/factor/identity filters, top-two leverage, LONG/SHORT trailing stops, latched exit, escaping and integration passed.');


// Actual minute-boundary mismatch: quote 09:59:39, latest candle closes 10:00.
for(const dir of ['LONG','SHORT']){
 const clock=now+30000,b=bundle();
 const bars=Array.from({length:22},(_,i)=>({openTime:now-(22-i)*60000,instrument:'XAU/USD',open:4000,high:4002,low:3998,close:4000}));
 bars.at(-1).close=dir==='LONG'?4001:3999;
 b.history.bars_by_tf['1m']=bars;
 b.spots.xaus=dir==='LONG'?4000.2:3999.8;b.spots.spot_price_as_of=new Date(now-21000).toISOString();
 assert.equal(r.analyze(b,clock).ready,false);
 const estimate=r.analyzePaper(b,clock);
 assert.equal(estimate.ready,true);assert.equal(estimate.dataMode,'estimate');assert.equal(estimate.direction,dir);
 assert.equal(estimate.sourceAt,now-21000);assert.equal(estimate.at,now);assert.equal(estimate.computedAt,clock);
 assert.equal(estimate.stage,'VORWARNUNG');
 assert.equal(r.analyze(b,now).ready,true,'as-of candle selection avoids looking ahead at a later close');
 assert.equal(r.analyzePaper(b,clock+180001).ready,false,'no unlimited model continuation');
 const broken=JSON.parse(JSON.stringify(b));broken.history.bars_by_tf['1m'][10].openTime-=60000;
 assert.equal(r.analyzePaper(broken,clock).ready,false,'model cannot fill candle gaps');
 const backup={...b,risk_spot_backup:{price:dir==='LONG'?4001.2:3998.8,at:new Date(now+10000).toISOString(),observed:true,instrument:'XAU/USD',source:'XAUS · XAU/USD Spot'}};
 assert.equal(r.analyzePaper(backup,clock).dataMode,'backup','observed backup precedes estimate');
 const real={...backup,spots:{...backup.spots,xaus:backup.risk_spot_backup.price,spot_price_as_of:backup.risk_spot_backup.at}};
 assert.equal(r.analyzePaper(real,clock).dataMode,'original','original precedes backup');
 const unconfirmed=JSON.parse(JSON.stringify(b));unconfirmed.history.bars_by_tf['1m'].at(-1).providerIsOpen=true;
 assert.equal(r.analyzePaper(unconfirmed,clock).ready,false,'provider-open candles never support a model');
}
console.log('Risk paper: original/backup/model hierarchy, LONG/SHORT estimates, clocks and bounded validity passed.');
