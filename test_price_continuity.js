const assert=require('assert'),fs=require('fs'),vm=require('vm');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={renderProductDirectionStatus,'),{window});
const render=window.BobDegiro.renderPrimaryProductValues;
const now=Date.now(),at=s=>new Date(now-s*1000).toISOString();
const isin='DE000FC1CHB7';
const metadata={status:1,currency:'EUR',underlyingType:'SPOT',underlying:'XAU/USD',direction:'LONG',ratio:.1,strike:4000,ko:4000};
const c={state:'calculated',kind:'intrinsic',price:13.8,leverage:27.66,goldUsd:4150,usdEur:.92,currency:'EUR',at:at(5),goldAt:at(5),fxDataAt:at(5),fxEffectiveAt:at(5),eligible:false,degiroExecutable:false,source:'Bob',note:'Theoretischer innerer Wert ohne Spread',model:{...metadata,isin,verifiedSimpleTurbo:true,tradingEndAt:at(-3600)}};
const p={isin,index:1,quote:{isin,productVerified:true,eligible:false,metadata,priceContinuity:c}};
let html=render(p,now);
assert(html.includes('Berechneter Kurs aktuell'));
assert(html.includes('Theoretischer Produktwert'));
assert(!html.includes(' Geld '));assert(!html.includes(' Brief '));
assert(html.includes('Berechneter Hebel'));
assert.strictEqual(p.quote.eligible,false);
for(const mutate of [x=>x.quote.priceContinuity.goldAt=at(90),x=>x.quote.metadata.ko=4200,x=>x.quote.priceContinuity.model.isin='wrong',x=>x.quote.metadata.currency='CHF']){
 const x=structuredClone(p);mutate(x);assert(!render(x,now).includes('Theoretischer Produktwert'));
}
const o=structuredClone(p);o.quote.priceContinuity={state:'original',currency:'EUR',bid:13.8,ask:13.82,at:at(3),source:'BNP',eligible:false,degiroExecutable:false};
html=render(o,now);assert(html.includes('Originalkurs aktuell'));assert(!html.includes('Theoretischer Produktwert'));
assert(render(o,now+120000).includes('Keine aktuelle Berechnungsgrundlage'));
console.log('Continuity display: model, original recovery and stale/identity/currency/KO rejection passed');

const card=window.BobDegiro.renderProductDirectionStatus;
assert(card(p,now).includes('Berechneter Kurs aktuell'));
assert(!card(p,now).includes('Veraltete Werte'));
assert(card(o,now).includes('Originalkurs aktuell'));
assert(card(o,now).includes('DEGIRO-Ausführung separat'));
assert(!card(o,now+120000).includes('Originalkurs aktuell'));
const source=fs.readFileSync('degiro_assistant.js','utf8');
const help={researchResults:new Map(),pendingQuotes:new Set(),productProblemLabels:()=>['Kurszeit'],productFieldStates:()=>({}),n:()=>null,analysisContinuityStatus:()=>({label:'Berechneter Kurs aktuell',calculated:true})};
vm.createContext(help);vm.runInContext(source.slice(source.indexOf('function productHelpState('),source.indexOf('function renderProductHelp(')),help);
assert(help.productHelpState(p).status.includes('Berechneter Kurs aktuell'));
help.productProblemLabels=()=>['KO-Nachweis'];
assert(help.productHelpState(p).manual,'KO gap is not hidden by a current price');
console.log('Card header and direction status use the same current analysis basis');
