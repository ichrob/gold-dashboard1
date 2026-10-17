const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const env={window:{},localStorage:{getItem:()=>null}};vm.createContext(env);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),env);
const rank=env.window.BobDegiro.applyLearnedRanking,now=1800000000000;
const policy={id:'product-ranking-v1',issuedAt:now,expiresAt:now+120000,maxScoreGap:5,variants:{EUR:'second',CHF:'third'}};
const cs=[['a',90],['b',89],['c',88],['d',85]].map(([isin,score])=>({isin,score,scope:'XAU/USD',direction:'LONG'}));
const products=cs.map(c=>({isin:c.isin,quote:{metadata:{currency:'EUR'}}}));
const names=x=>Array.from(x,c=>c.isin),before=JSON.stringify(cs);
assert.deepEqual(names(rank(cs,products,policy,now)),['b','a','c','d']);assert.equal(JSON.stringify(cs),before);
for(const p of [null,{...policy,id:'unknown'},{...policy,expiresAt:now},{...policy,issuedAt:now+1},{...policy,expiresAt:now+120001},{...policy,maxScoreGap:6}])assert.deepEqual(names(rank(cs,products,p,now)),['a','b','c','d']);
assert.deepEqual(names(rank(cs.map(c=>c.isin==='b'?{...c,score:84}:c.isin==='d'?{...c,score:83}:c),products,{...policy,variants:{EUR:'third'}},now)),['a','c','b','d']);
for(const change of [{indicative:true},{estimated:true},{scope:'FUTURE'},{direction:'SHORT'},{paperOnly:true}]){
 const input=cs.map(c=>c.isin==='b'?{...c,...change}:c);
 assert.deepEqual(names(rank(input,products,policy,now)),['c','b','a','d']);
}
const mixed=products.map(p=>p.isin==='b'?{...p,quote:{metadata:{currency:'CHF'}}}:p);
assert.deepEqual(names(rank(cs,mixed,policy,now)),['c','b','a','d']);
assert.deepEqual(names(rank(cs,products,{...policy,variants:{EUR:'third'}},now)),['c','a','b','d']);
assert.deepEqual(names(rank(cs.map(c=>({...c,paperOnly:true})),products,policy,now)),['a','b','c','d']);
console.log('Learned ranking: fixed variants, lease, currency/direction, admission and unchanged membership/scores pass');
