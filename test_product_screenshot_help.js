const assert=require('assert'),fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('degiro_assistant.js','utf8');
const context={window:{},navigator:{userAgent:'Android'}};
vm.runInNewContext(source,context);
const p={isin:'DE000FC1CHB7',name:'SG Gold',index:1};
const card=context.window.BobDegiro.compactProductCard(p);
assert(card.includes('data-product-problems'),card);
assert(card.includes('(Hebel')||card.includes(', Hebel'),card);
assert(card.indexOf('data-screenshot-sources')<card.indexOf('data-product-status'));
assert(card.includes('intent://trader.degiro.nl/#Intent;scheme=https;package=nl.degiro.trader;'));
assert(card.includes('S.browser_fallback_url=https%3A%2F%2Ftrader.degiro.nl%2F'));
assert(card.indexOf('DEGIRO-App öffnen')<card.indexOf('SG-Produkt öffnen'));
assert(card.includes('Falls sich nur die Webseite öffnet'));
context.navigator.userAgent='Desktop';
const desktop=context.window.BobDegiro.compactProductCard(p);
assert(!desktop.includes('intent:'));
assert(desktop.includes('href="https://trader.degiro.nl/"'));
const factor=context.window.BobDegiro.compactProductCard({...p,name:'FAKTOR Gold'});
assert(!factor.includes('data-screenshot-sources'));
// Keep market/ranking reasons out of the data problem labels.
const helpers={finalProductStatus:()=>({complete:false,reasons:['Hebel mit Zeitstempel fehlt','Geld/Brief Kurszeit fehlt','Basispreis fehlt']}),
 knockoutStatus:()=>false,compactProductExclusion:()=>false};
vm.createContext(helpers);
vm.runInContext(source.slice(source.indexOf('function productProblemLabels('),source.indexOf('function renderProductProblemSummary(')),helpers);
assert.deepEqual(Array.from(helpers.productProblemLabels(p)),['Hebel','Kurszeit','Kursnachweis','Basispreis']);
helpers.finalProductStatus=()=>({complete:true,reasons:[]});
assert.equal(helpers.productProblemLabels(p).length,0);
console.log('Screenshot help: evidence labels, Android fallback, source order, desktop and exclusions passed');
