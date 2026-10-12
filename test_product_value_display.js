const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro,isin='DE000SQ02JQ6',now=Date.now(),at=new Date(now-1000).toISOString();
const p={isin,index:0,price:100,quote:{isin,productVerified:true,found:false,analysisQuote:{currency:'EUR',bid:180.2,ask:180.21,bidAt:at,askAt:at,source:'SG',priceKind:'issuer-chart'},leverage:2.0447,leverageAt:at}};
let f=b.productFieldStates(p,now);
assert.equal(f.ask.value,180.21);assert.equal(f.bid.value,180.2);assert.equal(f.leverage.value,2.0447);
assert(b.compactProductCard(p).includes('Analysewerte vorhanden · ausführbarer Kurs separat offen'));
const shot={isin,index:1,snapshot:{isin,currency:'EUR',bid:10,ask:10.01,sourceTime:at,evidence:{Hebel:{value:5,at,source:'image'}}}};
f=b.productFieldStates(shot,now);assert.equal(f.ask.value,10.01);assert.equal(f.leverage.value,5);
assert(b.compactProductCard({isin,index:2}).includes('Fehlende Kurswerte: Geld, Brief, Hebel'));
assert.equal(b.productFieldStates({...shot,snapshot:{...shot.snapshot,isin:'DE000FG5GUN3'}},now).ask.state,'fehlt');
assert.equal(b.productFieldStates({...shot,snapshot:{...shot.snapshot,currency:'CHF'}},now).ask.state,'fehlt');
const stale=JSON.parse(JSON.stringify(p));stale.quote.analysisQuote.bidAt=stale.quote.analysisQuote.askAt=new Date(now-3600000).toISOString();
assert.equal(b.productFieldStates(stale,now).ask.state,'veraltet');
const prior={isin,productVerified:true,found:true,currency:'EUR',bid:12,ask:12.1,bidAt:at,askAt:at,metadata:{status:1}};
const failed=b.retainProductResearch(prior,{isin,sourceFailure:true},isin);
const preserved=b.productFieldStates({isin,quote:failed},now);
assert.equal(preserved.bid.value,12);assert.equal(preserved.ask.value,12.1);
assert(preserved.ask.state.includes('unbestätigt'));
assert(!b.compactProductCard({isin,quote:failed}).includes('Aktueller Anbieterwert'));
assert.equal(b.currentQuote({isin,quote:failed},now),false);
const partial=b.retainProductResearch(prior,{isin,productVerified:true,found:false,metadata:{status:1}},isin);
assert.equal(b.productFieldStates({isin,quote:partial},now).bid.value,12);
const ended=b.retainProductResearch(prior,{isin,productVerified:true,found:false,metadata:{status:2}},isin);
assert.equal(ended.referenceQuote,undefined);
// Native CHF evidence stays visible without EUR conversion. This is explicitly
// an issuer chart for research, never a claimed executable DEGIRO quote.
const chfIsin='DE000FG8NHQ3';
const chf={isin:chfIsin,index:8,quote:{isin:chfIsin,productVerified:true,
 found:false,eligible:false,fresh:false,metadata:{status:1,direction:'SHORT'},
 nativeChartEvidence:{bid:16.39,ask:16.41,pointAt:at,currency:'CHF'},
 leverage:25.4,leverageAt:at,leverageEstimated:true,
 leverageCalculation:{available:true,inputs:{quoteCurrency:'CHF',askNative:16.41,askAt:at}}}};
const chfFields=b.productFieldStates(chf,now);
assert.equal(chfFields.bid.value,16.39);
assert.equal(chfFields.ask.value,16.41);
assert.equal(chfFields.leverage.value,25.4);
const chfCard=b.compactProductCard(chf);
assert(chfCard.includes('16.39'),chfCard);
assert(chfCard.includes('16.41'),chfCard);
assert(chfCard.includes('CHF'),chfCard);
assert(chfCard.includes('SG-Chartbeobachtung'),chfCard);
assert(chfCard.includes('kein bestätigter Ausführungskurs'),chfCard);
assert(chfCard.includes('rechnerische Näherung'),chfCard);
assert(chfCard.includes('Analysewerte vorhanden'),chfCard);
assert.equal(b.currentQuote(chf,now),false);
const oldChf=structuredClone(chf);
oldChf.quote.nativeChartEvidence.pointAt=new Date(now-600000).toISOString();
assert(b.compactProductCard(oldChf).includes('nicht aktuell'));
assert.equal(b.productFieldStates(oldChf,now).ask.state,'veraltet');
console.log('Product value display: OK');

const auto=b.compactProductCard(p,['BNP-Kursabruf: Quellenantwort veraltet']);assert(auto.includes('derzeit keine neuen Bilder erforderlich'));
const actualMissing=b.compactProductCard(p,['Bezugsverhältnis fehlt']);assert(!actualMissing.includes('derzeit keine neuen Bilder erforderlich'));
