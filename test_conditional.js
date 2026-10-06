const fs=require('fs'),vm=require('vm'),assert=require('assert');const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});const b=window.BobDegiro;
const now=Date.now(),at=s=>new Date(now+s*1000).toISOString();
const ctx={now,spotFresh:true,spot:4000,direction:'LONG',trend:'LONG',trend2:'LONG',mtf:'LONG',rsi:60,hist:1,adx:30,momentum:1,atr:20};
const quality={ready:true,sampleCount:21,bid:{maxAbsoluteError:.02},ask:{maxAbsoluteError:.02}};
const p={isin:'DE000FC1CHB7',isinConfirmed:true,quote:{isin:'DE000FC1CHB7',productVerified:true,metadata:{ko:3500},productModel:{verifiedSimpleTurbo:true,isin:'DE000FC1CHB7',underlying:'XAU/USD',direction:'LONG',ko:3500,strike:3500,ratio:.1,tradingEndAt:at(3600)},calculatedProduct:{available:true,validation:quality,priceAt:at(0),goldAt:at(0),fxDataAt:at(0),fxEffectiveAt:at(0),referenceAt:at(-180),direction:'LONG',ratio:.1,strikeUsd:3500,goldUsd:4000,usdEur:.88,askEur:44.1,bidEur:44,comparisonErrorEur:.02}}};
assert(b.conditionalCandidate(p,ctx,now).ok);assert(!b.rankConditional([p],ctx).groups[0].favorite);assert(!b.rankConditional([p],ctx).tradeable);
for(const change of [c=>c.validation.ready=false,c=>c.comparisonErrorEur=.001,c=>c.fxDataAt=at(-61),c=>c.strikeUsd=3499,c=>c.askEur=.01]){const bad=JSON.parse(JSON.stringify(p));change(bad.quote.calculatedProduct);assert(!b.conditionalCandidate(bad,ctx,now).ok);}
const same={...p,isin:'DE000PJ9NCK0',quote:JSON.parse(JSON.stringify(p.quote))};same.quote.isin=same.isin;same.quote.productModel.isin=same.isin;
assert(!b.rankConditional([p,same],ctx).groups[0].favorite);
const pending=JSON.parse(JSON.stringify(same));pending.quote.calculatedProduct.validation.ready=false;assert(!b.rankConditional([p,pending],ctx).groups[0].favorite);
const f={isin:'DE000FG309G0',isinConfirmed:true,quote:{isin:'DE000FG309G0',productVerified:true,metadata:{underlyingType:'FUTURE',contract:'GCZ26'},futureResearch:{contract:'GCZ26',direction:'SHORT',marketOpen:true,tradingEndAt:at(3600),bidAt:at(0),askAt:at(0),fxDataAt:at(0),fxEffectiveAt:at(0),bid:44,ask:44.1,ko:4500,strike:4500,ratio:.1,usdEur:.88,calculatedFuture:{available:true,contract:'GCZ26',priceUsd:4000,comparisonErrorUsd:2,priceAt:at(0),referenceAt:at(-900),validation:{ready:true,sampleCount:21,maxAbsoluteError:2}},contractAnalysis:{available:true,contract:'GCZ26',direction:'SHORT',technicalSourceFamilies:1,checkedAt:at(0),expiresAt:at(180),rsi:40,macdHistogram:-1,atr:20,frames:{'5m':{available:true,ema20:4010},'15m':{available:true,trend:'SHORT'},'1h':{available:true,trend:'SHORT',ema50:4020,ema200:4050},'4h':{available:true}}}}}};
assert(b.conditionalCandidate(f,ctx,now).ok); // Own short future can coexist with long spot; no inherited direction.
assert(!b.currentQuote(f,now));assert.strictEqual(b.rankConditional([p,f],ctx).groups.length,2);
for(const change of [r=>r.contractAnalysis.contract='GCG27',r=>r.contractAnalysis.expiresAt=at(-1),r=>r.contractAnalysis.frames['15m'].available=false,r=>r.calculatedFuture.priceUsd=4499,r=>r.tradingEndAt=undefined]){const bad=JSON.parse(JSON.stringify(f));change(bad.quote.futureResearch);assert(!b.conditionalCandidate(bad,ctx,now).ok);}
assert(b.renderConditional(b.rankConditional([p,f],ctx)).includes('DEGIRO-Briefkurs'));
console.log('Conditional comparison tests: OK');

const no4h=JSON.parse(JSON.stringify(f));no4h.quote.futureResearch.contractAnalysis.frames['4h']={available:false,direction:'LONG',trend:'LONG'};assert(b.conditionalCandidate(no4h,ctx,now).ok);
