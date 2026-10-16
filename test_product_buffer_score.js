const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro,base={spot:4000,price:20,ko:3800,leverage:20,atr:20,productDirection:'LONG',direction:'LONG',trend:'LONG',trend2:'LONG',hist:1,rsi:60};
const evaluate=x=>b.evaluateProduct({...base,...x});
// The former plateau at 5% no longer makes materially different buffers equal.
const values=[80,120,200,300,400,600].map(d=>evaluate({ko:4000-d}));
for(let i=1;i<values.length;i++)assert(values[i].score>values[i-1].score);
for(const v of values){assert(v.score>=0&&v.score<100);assert.equal(v.costRisk.scoreModel.probability,false);assert(v.reasons.some(x=>x.includes('keine Gewinnwahrscheinlichkeit')));}
for(const d of [80,120,200,400])assert.equal(evaluate({ko:4000-d}).score,evaluate({ko:4000+d,productDirection:'SHORT',direction:'SHORT',trend:'SHORT',trend2:'SHORT',hist:-1,rsi:40}).score);
assert(evaluate({atr:80}).score<evaluate({atr:20}).score,'larger gold fluctuations reduce relative buffer');
assert.equal(evaluate({atr:null}).score,evaluate({atr:20}).score,'no missing-data penalty');
assert.equal(evaluate({atr:null}).costRisk.scoreModel.atrIncluded,false);
for(const x of [{leverage:100},{spread:50},{at:null},{estimated:true},{costs:{roundTripEur:500}}])assert.equal(evaluate(x).score,evaluate({}).score);
// No altered admission thresholds: KO guard still blocks at <=1.5%/1.5ATR.
for(const d of [20,59,60])assert(!evaluate({ko:4000-d}).fit);
for(const d of [61,75,80,120,200])assert(evaluate({ko:4000-d}).fit);
assert(!evaluate({ko:3800,atr:140}).fit);
assert(!evaluate({ko:4001}).fit);
const up=evaluate({}),conflict=evaluate({trend:'SHORT',trend2:'SHORT',hist:-1,rsi:40});
assert.equal(up.score,conflict.score,'market setup remains separate from product buffer');
assert(up.setupScore>conflict.setupScore);
const product=ko=>({...base,ko,isin:'DE000FC1CHB7',name:'Gold turbo'});
assert.equal(b.rankProducts([product(3800),product(3600)],{direction:'LONG',trend:'LONG',trend2:'LONG',hist:1,rsi:60}).candidates[0].ko,3600);
console.log('Continuous product buffer score: monotonic, symmetric, ATR-aware, transparent, eligibility unchanged');
