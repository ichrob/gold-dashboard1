const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const extract=name=>{
 const start=script.indexOf('window.'+name+'=function');
 assert(start>=0,'Missing '+name);
 const end=script.indexOf('\n};',start);
 assert(end>start,'Malformed '+name);
 return script.slice(start,end+3);
};
const env={window:{},Date,Intl,Object,Number};vm.createContext(env);
vm.runInContext(extract('BobWeekendPause')+'\n'+extract('BobDegiroPhase'),env);
const at=(iso)=>Date.parse(iso);
const phase=env.window.BobDegiroPhase;
const cases=[
 ['2026-10-12T05:29:00Z','night'],['2026-10-12T05:30:00Z','preparation'],
 ['2026-10-12T05:59:00Z','preparation'],['2026-10-12T06:00:00Z','trading'],
 ['2026-10-12T19:59:00Z','trading'],['2026-10-12T20:00:00Z','night'],
 ['2026-10-09T20:59:00Z','trading'],['2026-10-09T21:00:00Z','night'],
 ['2026-10-09T22:00:00Z','weekend'],['2026-10-11T21:59:00Z','weekend'],
 ['2026-10-26T06:30:00Z','preparation'],['2026-10-26T07:00:00Z','trading']
];
for(const [iso,want] of cases)assert.equal(phase(at(iso)),want,iso);
assert(html.includes('phase===\'trading\'||phase===\'preparation\''));
assert(html.includes('phase===\'night\'&&!activeTrade?300000:30000'));
console.log('DEGIRO night UI: 08–22 trading, 07:30 prewarm, DST and active-trade speed: OK');
