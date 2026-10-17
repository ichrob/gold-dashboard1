const assert=require('node:assert/strict');
const {match,plan,difference}=require('./video_evidence.js');
const image={at:20,lines:[{text:'RSI 61.8'}]};
assert.equal(match(image,[{at:21,text:'Der RSI liegt bei 61.8.'}]).matched,true);
assert.equal(match(image,[{at:21,text:'Gold liegt bei 61.8.'}]).matched,false);
assert.equal(match(image,[{at:80,text:'RSI 61.8'}]),null);
for(const duration of [1,60,7200]){
 const p=plan(duration,[{at:20},{at:200},{at:400}]);assert(p.times.length<=57);assert(p.times.every(t=>t>=0&&t<duration));
}
assert.equal(difference(new Uint8Array([0,0,0,255]),new Uint8Array([255,255,255,255])),255);
console.log('Video evidence matching and bounded sampling passed');
