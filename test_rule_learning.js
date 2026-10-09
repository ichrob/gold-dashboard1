const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
// Compile every inline script, then exercise the exact shared entry filter.
for(const m of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
const source=html.slice(html.indexOf('function applyLearningFilter('),html.indexOf('async function refreshLearningPolicy('));
const now=1800000000000,env={window:{},Date,Number,adxCalc:()=>26};vm.createContext(env);vm.runInContext(source,env);
const policy={campaign:'entry-filter-v1-20261009',base:'intraday-trend-follow-v7',variant:'baseline',version:'test',issuedAt:now,expiresAt:now+120000};
const bundle={history:{bars_by_tf:{'5m':Array.from({length:100},(_,i)=>({openTime:now-(i+1)*300000,isOpen:false}))}}};
const filter=(d,p=policy)=>env.applyLearningFilter({dir:d,reason:'original'},bundle,p,now);
for(const d of ['LONG','SHORT']){
 assert.equal(filter(d).dir,d);
 assert.equal(filter(d,{...policy,variant:'adx25'}).dir,d);
 assert.equal(filter(d,{...policy,variant:'adx30'}).dir,'NEUTRAL');
 assert.equal(filter(d,{...policy,expiresAt:now}).dir,'NEUTRAL');
 assert.equal(filter(d,null).baseDirection,d);
 assert.equal(filter(d,null).dir,'NEUTRAL');
 assert.equal(filter(d,{...policy,base:'unknown'}).dir,'NEUTRAL');
 env.adxCalc=()=>NaN;assert.equal(filter(d,{...policy,variant:'adx25'}).dir,'NEUTRAL');env.adxCalc=()=>26;
}
assert.equal(filter('NEUTRAL',{...policy,variant:'adx25'}).dir,'NEUTRAL');
console.log('Shared filter: LONG/SHORT thresholds, unavailable/expired policies, missing ADX and neutral verified.');
