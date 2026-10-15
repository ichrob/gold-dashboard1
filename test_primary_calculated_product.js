/* Calculated product bid/ask occupy the normal product-price slot,
   without becoming a broker quote or changing trading/approval rules. */
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const window={};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const bob=window.BobDegiro;
const isin='DE000FC1CHB7';
const now=Date.now(),at=seconds=>new Date(now-seconds*1000).toISOString();
const model={isin,underlying:'XAU/USD',direction:'LONG',ratio:0.1,
 strike:4030,ko:4037.98,verifiedSimpleTurbo:true,
 tradingEndAt:new Date(now+4*3600000).toISOString()};
const calculated={available:true,kind:'calculated-turbo',currency:'EUR',
 eligible:false,isDegiroQuote:false,direction:'LONG',
 bidEur:10.51,askEur:10.53,priceEur:10.53,
 ratio:0.1,strikeUsd:4030,goldUsd:4140,usdEur:0.89,
 referenceAt:at(180),referenceSkewSeconds:2,
 priceAt:at(12),goldAt:at(10),fxDataAt:at(12),fxEffectiveAt:at(11),
 validation:{ready:false,sampleCount:2}};
const meta={status:1,currency:'EUR',underlyingType:'SPOT',
 underlying:'XAU/USD',direction:'LONG',strike:4030,ko:4037.98,ratio:0.1};
const p={isin,index:1,name:'SG Gold Turbo',productDirection:'LONG',
 isinConfirmed:true,quote:{isin,productVerified:true,found:false,eligible:false,
 metadata:meta,productModel:model,calculatedProduct:calculated}};
const priced=bob.calculatedProductDisplay(p,now);
assert(priced,'Model qualified for display');
assert.strictEqual(priced.referenceOnly,true);
assert.strictEqual(priced.degiroExecutable,false);
assert.strictEqual(priced.ask,10.53);
const html=bob.renderPrimaryProductValues(p,now);
assert(html.includes('data-price-kind="calculated"'),html);
assert(html.includes('Produktkurs · ≈ errechnet'),html);
assert(html.includes('≈  Geld')||html.includes('≈ Geld'),html);
assert(html.includes('10.51'),html);
assert(html.includes('10.53'),html);
assert(html.includes('Quelle: Bob'),html);
assert(html.includes('Genauigkeit noch nicht ausreichend bestätigt'),html);
assert(html.includes('kein automatischer Stopp'),html);
assert(!html.includes('Aktueller Anbieterwert'),html);
assert.strictEqual(bob.currentQuote(p,now),false);
assert.strictEqual(bob.finalProductStatus(p,now).complete,false);

const patch=(path,val)=>{const x=structuredClone(p);x.quote={...x.quote};if(path==='quote')x.quote={...x.quote,...val};if(path==='meta')x.quote.metadata={...x.quote.metadata,...val};
 if(path==='model')x.quote.productModel={...x.quote.productModel,...val};
 if(path==='calc')x.quote.calculatedProduct={...x.quote.calculatedProduct,...val};return x;};
for(const [name,field,change] of [
 ['wrong isin','quote',{isin:'DE000FG4JXV7'}],
 ['unverified','quote',{productVerified:false}],
 ['disabled source','quote',{sourceDisabled:true}],
 ['supplier error','quote',{sourceFailure:true}],
 ['source quote invalid','quote',{quoteFailureCode:'TIME_INVALID'}],
 ['knocked out','meta',{status:2}],
 ['wrong currency','meta',{currency:'CHF'}],
 ['future','meta',{underlyingType:'FUTURE'}],
 ['other gold','meta',{underlying:'GCZ26'}],
 ['quanto/direction mismatch','meta',{direction:'SHORT'}],
 ['changed strike','meta',{strike:4031}],
 ['changed KO','meta',{ko:4020}],
 ['changed ratio','meta',{ratio:.2}],
 ['invalid leverage model','model',{verifiedSimpleTurbo:false}],
 ['wrong model isin','model',{isin:'DE000FG4JXV7'}],
 ['expired model','model',{tradingEndAt:at(1)}],
 ['anchor too old','calc',{referenceAt:at(1900)}],
 ['gold time stale','calc',{goldAt:at(91)}],
 ['FX time stale','calc',{fxDataAt:at(90)}],
 ['no FX source time','calc',{fxEffectiveAt:null}],
 ['future estimated time','calc',{priceAt:new Date(now+10000).toISOString()}],
 ['source clock skew','calc',{referenceSkewSeconds:7}],
 ['negative bid','calc',{bidEur:-1}],
 ['crossed price','calc',{askEur:9}],
 ['unproven gold','calc',{goldUsd:0}],
 ['KO breached','calc',{goldUsd:4037}],
 ['wrong price kind','calc',{kind:'issuer-chart'}],
 ['wrong currency estimate','calc',{currency:'CHF'}],
 ['incorrect eligibility','calc',{eligible:true}],
 ['pretend DEGIRO','calc',{isDegiroQuote:true}],
 ['mismatch product terms','calc',{strikeUsd:4040}],
]){
 const x=patch(field,change);
 assert.strictEqual(bob.calculatedProductDisplay(x,now),null,name);
 assert(!bob.renderPrimaryProductValues(x,now).includes('data-price-kind="calculated"'),name);
}
const researchPrice=patch('calc',{anchorKind:'research-hybrid',
 referenceSource:'comdirect · SG LiveTrading',referenceSkewSeconds:25});
const researchDisplay=bob.calculatedProductDisplay(researchPrice,now);
assert(researchDisplay,'Time-aligned SG/comdirect research quote is displayable');
assert(researchDisplay.source.includes('SG/comdirect'));
assert.strictEqual(researchDisplay.referenceSource,'comdirect · SG LiveTrading');
assert.strictEqual(researchDisplay.referenceClockGapSeconds,25);
const researchHtml=bob.renderPrimaryProductValues(researchPrice,now);
assert(researchHtml.includes('Kalibrierung comdirect · SG LiveTrading'),researchHtml);
assert(researchHtml.includes('Originalzeitabstand 25 s'),researchHtml);
assert(researchHtml.includes('≈ errechnet'),researchHtml);
assert.strictEqual(bob.currentQuote(researchPrice,now),false);
assert(!bob.finalProductStatus(researchPrice,now).complete);
for(const skew of [30.001,45,90]){
 const unsafe=patch('calc',{anchorKind:'research-hybrid',
  referenceSource:'SG · Live-Chart',referenceSkewSeconds:skew});
 assert.strictEqual(bob.calculatedProductDisplay(unsafe,now),null,
  'Time-shifted anchor >30s cannot show as near-current price');
}

const originalAt=at(16);
const q={...p.quote,found:true,currency:'EUR',bid:10.61,ask:10.63,
 bidAt:originalAt,askAt:originalAt,source:'SG OTC',
 priceKind:'market-observation',isExecutableQuote:true};
const live=bob.renderPrimaryProductValues({...p,quote:q},now);
assert(live.includes('data-price-kind="observation"'));
assert(live.includes('10.61'));
assert(!live.includes('Produktkurs · ≈ errechnet'));
const oldAt=at(165);
const old=bob.renderPrimaryProductValues({...p,quote:{...q,bidAt:oldAt,askAt:oldAt}},now);
assert(old.includes('data-price-kind="calculated"'));
assert(old.includes('Letzter originaler Datenstand'));
const listOnly={isin,price:10.38,productDirection:'LONG',index:1,
 snapshot:{isin,currency:'EUR',bid:null,ask:null}};
assert.strictEqual(bob.calculatedProductDisplay(listOnly,now),null);
assert(!bob.renderPrimaryProductValues(listOnly,now).includes('data-price-kind="calculated"'));
assert(bob.renderPrimaryProductValues(listOnly,now).includes('Gespeicherter Produkt-/Listenpreis'));
console.log('Primary product price display: verified model, original preference, 29 strict negatives and list-only failsafe passed');
