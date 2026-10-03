const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro,now=Date.parse('2026-10-02T10:00:00Z'),at=new Date(now).toISOString();
const ctx={now,spot:4000,spotFresh:true,direction:'LONG',atr:20,trend:'LONG',trend2:'LONG',mtf:'LONG',rsi:60,hist:1,adx:30,momentum:1};
const cost=isin=>({isin,source:'Synthetic tariff, not real DEGIRO fees',asOf:at,roundTripEur:2,financingDailyPct:.01,positionEur:1000,holdingDays:1,scenarioExplicit:true});
const p={isin:'DE000FC1CHB7',name:'Synthetic Gold Turbo',spot:4000,isinConfirmed:true,price:40,spread:.04,ko:3600,leverage:5,productDirection:'LONG',at,costs:cost('DE000FC1CHB7')};
const assess=changes=>b.evaluateProduct({...p,...ctx,...changes});
const rank=products=>b.rankProducts(products,ctx);
const base=assess({});assert(base.fit);assert.equal(base.costRisk.totalCostsPct,null);
assert.equal(base.score,100); // trading 1, financing .05 points; spread unweighted
const wide=assess({spread:.4});assert(wide.fit);assert.equal(wide.score,base.score);
for(const spread of [null,undefined,'',-1,0,.4,2,39,100]){const e=assess({spread});assert.equal(e.score,base.score);assert.equal(e.fit,base.fit);assert.equal(e.costRisk.parts.spread,0);}
assert(rank([{...p,spread:2}]).tradeable,'wide spread cannot trigger a gate');
assert(assess({spread:2,costs:{...p.costs,roundTripEur:49,financingDailyPct:0}}).fit,'spread excluded from the 5% weighted-cost gate');
for(const leverage of [1,5,6,10,15,20,40,100]){const e=assess({leverage});assert.equal(e.score,base.score);assert.equal(e.fit,base.fit);assert.equal(e.productScore,base.productScore);assert.equal(e.costRisk.parts.leverage,0);}
const high={...p,name:'High leverage, lower fees',leverage:30},low={...p,name:'Low leverage, higher fees',leverage:5,costs:{...p.costs,roundTripEur:10}};
assert.equal(assess(high).score,assess(low).score,'costs and leverage do not weight ranking');
for(const leverage of [5,30]){assert(!assess({leverage,ko:3990}).fit);assert(!assess({leverage,atr:300}).fit);}
for(const leverage of [null,'',0,-1])assert(!assess({leverage}).fit,'missing or invalid leverage remains a data failure');
assert(assess({ko:3920}).score<base.score);
for(const changes of [{ko:3980},{ko:4000},{ko:4100},{ko:null},{leverage:null},{price:null}])assert(!assess(changes).fit,JSON.stringify(changes));
assert(!assess({atr:300}).fit,'insufficient volatility buffer');
assert.equal(assess({atr:null}).score,base.score,'missing ATR has no data-quality deduction');
const unknown=assess({costs:null});assert.equal(unknown.score,base.score);
for(const costs of [null,{},cost(p.isin),{...cost(p.isin),roundTripEur:5000,financingDailyPct:100}]){const e=assess({costs});assert.equal(e.score,base.score);assert.equal(e.fit,base.fit);assert.equal(e.costRisk.totalCostsPct,null);}
assert.equal(assess({at:new Date(now-60000).toISOString()}).score,base.score);
assert.equal(assess({estimated:true}).score,base.score);
assert.equal(assess({at:null}).score,base.score);
const future={...p,isin:'DE000FG309G0',name:'Gold Future Turbo',productDirection:'LONG',ko:3800,costs:cost('DE000FG309G0')};
const qa={available:true,contract:'GCZ26',direction:'LONG',technicalSourceFamilies:1,checkedAt:at,expiresAt:new Date(now+180000).toISOString(),rsi:60,macdHistogram:1,atr:20,frames:{'5m':{available:true,ema20:3700},'15m':{available:true},'1h':{available:true,trend:'LONG',ema50:4000,ema200:3900},'4h':{available:true}}};
future.quote={isin:future.isin,productVerified:true,metadata:{underlyingType:'FUTURE',contract:'GCZ26'},futureResearch:{contract:'GCZ26',direction:'LONG',marketOpen:true,tradingEndAt:new Date(now+3600000).toISOString(),bid:39.96,ask:40,ko:3800,strike:3800,ratio:.1,usdEur:1,bidAt:at,askAt:at,fxDataAt:at,fxEffectiveAt:at,contractAnalysis:qa,calculatedFuture:{available:true,contract:'GCZ26',priceUsd:4000,comparisonErrorUsd:2,priceAt:at,referenceAt:at,validation:{ready:true,sampleCount:25,maxAbsoluteError:2}}}};
let c=b.conditionalCandidate(future,ctx,now);assert(c.ok,c.reason);assert(c.reasons.join(' ').includes('Future-Abweichung'));
const f=JSON.parse(JSON.stringify(future));f.quote.futureResearch.calculatedFuture.comparisonErrorUsd=70;
// Lower edge remains >KO (3930 >3800), but 200 <= 3*70: additional buffer rejects.
c=b.conditionalCandidate(f,ctx,now);assert(!c.ok);assert(c.reason.includes('dreifache'));
const short=JSON.parse(JSON.stringify(f));short.productDirection='SHORT';short.ko=4200;
Object.assign(short.quote.futureResearch,{direction:'SHORT',ko:4200,strike:4200});
Object.assign(short.quote.futureResearch.contractAnalysis,{direction:'SHORT',rsi:40,macdHistogram:-1});
short.quote.futureResearch.contractAnalysis.frames['5m'].ema20=4300;
assert(!b.conditionalCandidate(short,{...ctx,direction:'SHORT'},now).ok,'short receives same uncertainty protection');
const unvalidated=JSON.parse(JSON.stringify(future));unvalidated.quote.futureResearch.calculatedFuture.validation.ready=false;
assert(!b.conditionalCandidate(unvalidated,ctx,now).ok);
assert(!rank([{...p,ko:3990}]).tradeable);
assert(!b.rankProducts([p],{...ctx,direction:'NEUTRAL'}).tradeable);
assert(!assess({direction:'SHORT'}).fit);
// Main user-visible flow: complete evidence, unsafe cost => explicit Abwarten with reason.
const shot={isin:p.isin,direction:'LONG',currency:'EUR',bid:39.96,ask:40,sourceTime:'02/10/2026 12:00:00 CEST',evidence:{Geld:{value:39.96,source:'quote.jpg',at},Brief:{value:40,source:'quote.jpg',at},Hebel:{value:5,source:'quote.jpg',at},KO:{value:3600,source:'detail.jpg',at}},terms:Object.fromEntries(Object.entries({ratio:.1,strike:3600,underlying:'XAU/USD',type:'Turbo',maturity:'Open End',currency:'EUR',quanto:'Nein'}).map(([key,value])=>[key,{value,at,source:'detail.jpg'}]))};
const withShot={...p,snapshot:shot};
assert.equal(b.selectionWorkflow([withShot],ctx,{}).stage,'TOP3');
const blocked=b.selectionWorkflow([{...withShot,costs:{...p.costs,roundTripEur:51}}],ctx,{});
assert.equal(blocked.stage,'TOP3','legacy costs cannot block selection');
const missingTerms={...withShot,snapshot:{...shot,terms:{}}};assert.equal(b.selectionWorkflow([missingTerms],ctx,{}).groups.length,0);
const hostile=assess({costs:{...p.costs,source:'<script>bad</script>'}});
const rendered=b.renderSelectionWorkflow({...blocked,waiting:[{isin:p.isin,reason:hostile.reasons.join(' ')}]});assert(!rendered.includes('<script>'));
console.log('Cost/risk scenarios passed:',JSON.stringify({lowCosts:base.score,wideSpread:wide.score,unknownCosts:unknown.score,highLeverage:assess({leverage:15}).score,missingAtr:assess({atr:null}).score,neutral:'ABWARTEN',tightFuture:'ABWARTEN'}));

assert(!fs.readFileSync('degiro_assistant.js','utf8').includes('data-cost-save'));

for(const change of [{at:null},{estimated:true},{atr:null},{rankingUncertaintyUsd:2,rankingBasisUsd:4000}])assert.equal(assess(change).costRisk.parts.data,0);
