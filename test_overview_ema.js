const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
const env={Date,Number,Set,ema:(a,n)=>a.slice(-n).reduce((s,v)=>s+v,0)/n,rsiS:()=>50,macdValues:()=>({hist:0}),intradayCollective:()=>0,dataAge:(t,limit,now)=>({fresh:now-t<=limit})};
vm.createContext(env);
vm.runInContext(html.slice(html.indexOf('function timeframeScore('),html.indexOf('// Optional closed-minute experiment.')),env);
vm.runInContext(html.slice(html.indexOf('function overviewTrendContext('),html.indexOf('function updateQuick(){')),env);
const now=1800000000000;
function bars(n,step){const end=Math.floor(now/step)*step;return Array.from({length:n},(_,i)=>({openTime:end-(n-i)*step,open:4000+i,close:4001+i,high:4002+i,low:3999+i,isOpen:false,instrument:'XAU/USD'}));}
let h={'5m':bars(290,300000),'15m':bars(193,900000)};
assert(env.overviewTrendContext(h,'15m',now).includes('5m · EMA200 (Ersatzkontext; 15m nicht verfügbar)'));
h['15m']=bars(220,900000);assert.equal(env.overviewTrendContext(h,'15m',now),'Bullish · 15m · EMA200');
h['15m']=bars(193,900000);
for(const mutate of [b=>b.forEach(x=>x.instrument='GC=F'),b=>b.forEach(x=>x.openTime-=86400000),b=>b.forEach(x=>x.observedOnly=true),b=>b.at(-1).openTime+=600000,b=>b.at(-1).high=1]){
 const bad=JSON.parse(JSON.stringify(h));mutate(bad['5m']);assert(env.overviewTrendContext(bad,'15m',now).includes('nicht verfügbar · Historie'));
}
assert(env.overviewTrendContext({},'15m',now).includes('nicht verfügbar'));
assert(html.indexOf('$("quickTrend").textContent=overviewTrendContext')<html.indexOf('if(window.BobSession?.expired())',html.indexOf('function updateQuick(){')));
console.log('Overview EMA context: preferred, explicit fallback, stale, foreign, observed, future and invalid histories checked');
