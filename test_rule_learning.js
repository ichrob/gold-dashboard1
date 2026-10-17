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
assert.equal(filter('LONG',{...policy,campaign:'entry-filter-v2-guarded',variant:'adx30'}).dir,'NEUTRAL');
assert.equal(filter('SHORT',{...policy,campaign:'entry-filter-v2-guarded'}).dir,'SHORT');
assert.equal(filter('LONG',{...policy,campaign:'entry-filter-v2-guarded',variant:'adx10'}).dir,'NEUTRAL');
assert.equal(filter('NEUTRAL',{...policy,variant:'adx25'}).dir,'NEUTRAL');
console.log('Shared filter: LONG/SHORT thresholds, unavailable/expired policies, missing ADX and neutral verified.');

const protectedState={dir:'LONG',reason:'original',stop:99,target:110,maxLoss:5,koProtected:true};
const before=JSON.stringify(protectedState);
const changed=env.applyLearningFilter(protectedState,bundle,{...policy,campaign:'entry-filter-v2-guarded',variant:'adx30'},now);
for(const key of ['stop','target','maxLoss','koProtected'])assert.deepEqual(changed[key],protectedState[key]);
assert.equal(JSON.stringify(protectedState),before);
