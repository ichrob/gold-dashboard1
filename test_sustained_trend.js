const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8'),now=Date.parse('2026-10-08T09:00:00Z');
const env={Date,Math,Number,dataAge:(t,limit,n)=>({fresh:n>=t&&n-t<=limit})};vm.createContext(env);
vm.runInContext(html.slice(html.indexOf('function ema('),html.indexOf('function calc('))+html.slice(html.indexOf('function rsiS('),html.indexOf('function buildMtfHierarchy('))+html.slice(html.indexOf('function sustainedTrendContext('),html.indexOf('function confirmedSignalDirection(')),env);
function bundle(sign){const frames={};for(const [tf,step] of Object.entries({'5m':300000,'15m':900000,'1h':3600000})){frames[tf]=Array.from({length:220},(_,i)=>{const p=4200+sign*i;return {openTime:now-(220-i)*step,open:p,close:p,high:p+2,low:p-2,isOpen:false,instrument:'XAU/USD'};});}return {history:{bars_by_tf:frames}};}
for(const sign of [1,-1]){
 const b=bundle(sign),side=sign===1?'LONG':'SHORT';
 let r=env.sustainedTrendContext(b,now);assert.equal(r.direction,side);assert(r.intact);
 // Sharp short-frame retreat leaves the higher trend intact.
 for(const [i,bar] of b.history.bars_by_tf['5m'].entries()){const p=4400-sign*i;Object.assign(bar,{open:p,close:p,high:p+2,low:p-2});}
 r=env.sustainedTrendContext(b,now);assert(r.intact);assert.equal(r.phase,'PULLBACK');
 env.fiveMinuteConfirmation=()=>({dir:sign===1?'SHORT':'LONG',reason:'short move'});
 assert.equal(env.trendFollowingSignal(b,now).dir,'NEUTRAL');
 env.fiveMinuteConfirmation=()=>({dir:side,reason:'entry'});assert.equal(env.trendFollowingSignal(b,now).dir,side);
 // A break below/above the setup invalidates the hold, symmetrically.
 const last=b.history.bars_by_tf['15m'].at(-1),p=4200-sign*300;Object.assign(last,{open:p,close:p,high:p+2,low:p-2});
 assert.equal(env.sustainedTrendContext(b,now).intact,false);
 assert.equal(env.trendFollowingSignal(b,now).dir,'NEUTRAL');
}
const b=bundle(1);assert(!env.sustainedTrendContext(b,now+7200001).available);
b.history.bars_by_tf['1h'].at(-1).instrument='GC';assert(!env.sustainedTrendContext(b,now).available);
const future=bundle(1);future.history.bars_by_tf['1h'].push({...future.history.bars_by_tf['1h'].at(-1),openTime:now+3600000});assert(!env.sustainedTrendContext(future,now).available);
console.log('Sustained trend: long/short, pullback, entry alignment, setup break, stale/wrong/future data pass.');
