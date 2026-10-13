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
// A morning DEGIRO list screenshot proves only a seen ISIN, not an order quote.
const morningIsin='DE000SQ02JQ6',morning=Date.parse('2026-10-13T09:00:00+02:00');
const noon=Date.parse('2026-10-13T12:00:00+02:00'),late=Date.parse('2026-10-13T22:05:00+02:00');
const listArchive={storedAt:new Date(morning).toISOString(),files:[{name:'degiro-list.png'}],items:[{isin:morningIsin}]};
let listProof=b.degiroListObservation(morningIsin,listArchive,noon);
assert.equal(listProof.observed,true);
assert.equal(listProof.currentDay,true);
assert.equal(listProof.executable,false);
assert.equal(listProof.quoteConfirmed,false);
let listHtml=b.renderDegiroListEvidence({isin:morningIsin},noon,listArchive);
assert(listHtml.includes('ISIN heute erkannt'));
assert(listHtml.includes('kein Nachweis von aktueller Handelbarkeit'));
assert.equal(b.degiroListObservation(morningIsin,listArchive,late).currentDay,false);
assert(b.renderDegiroListEvidence({isin:morningIsin},late,listArchive).includes('älterer Liste'));
assert.equal(b.degiroListObservation(chfIsin,listArchive,noon).observed,false);
assert.equal(b.degiroListObservation(morningIsin,{...listArchive,storedAt:null},noon).observed,false);
assert.equal(b.degiroListObservation(morningIsin,{...listArchive,files:[]},noon).observed,false);
assert.equal(b.degiroListObservation(morningIsin,{...listArchive,items:[]},noon).observed,false);
console.log('Product value display: OK');

const auto=b.compactProductCard(p,['BNP-Kursabruf: Quellenantwort veraltet']);assert(auto.includes('derzeit keine neuen Bilder erforderlich'));
const actualMissing=b.compactProductCard(p,['Bezugsverhältnis fehlt']);assert(!actualMissing.includes('derzeit keine neuen Bilder erforderlich'));


// Only a broker-visible *market-data display* is proven by a DEGIRO product page.
// All unrelated personal account data is excluded from the test fixture.
const degiroText=[
 'Kursdaten','Zuletzt € 13,31   13/10/2026 15:23',
 'Geld € 13,31','Brief € 13,32','Geld Vol. 25K','Brief Vol. 25K',
 'Symbol | ISIN','DE000BOB0018','Börse','Societe Generale OTC'
].join('\n');
const observed=b.parseDegiroDisplayedQuote(degiroText,'DE000BOB0018');
assert(observed, 'DEGIRO market quote pair should be readable');
assert.equal(observed.bid,13.31);
assert.equal(observed.ask,13.32);
assert.equal(observed.venue,'Societe Generale OTC');
assert.equal(observed.sourceTime,'13/10/2026 15:23');
assert(observed.brokerDisplayConfirmed);
assert.strictEqual(observed.orderWindowVerified,false);
assert.strictEqual(observed.executionGuaranteed,false);
assert.strictEqual(observed.isExecutableQuote,false);
assert.strictEqual(observed.orderSubmitted,false);
assert.equal(b.parseDegiroDisplayedQuote(degiroText,'DE000FG4JXV7'),null);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replace('13/10/2026 15:23','13/10/2026 15:23\n14/10/2026 16:00'),'DE000BOB0018'),null);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replace('Brief € 13,32','Brief Vol. 25K'),'DE000BOB0018'),null);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replace('Börse\nSociete Generale OTC',''),'DE000BOB0018'),null);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replace('Kursdaten','Kurshistorie'),'DE000BOB0018'),null);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replace('Brief € 13,32','Brief € 12,99'),'DE000BOB0018'),null);
const quoteProduct={isin:'DE000BOB0018',snapshot:{isin:'DE000BOB0018',degiroDisplayedQuote:observed}};
const quoteHtml=b.renderDegiroDisplayedQuote(quoteProduct,Date.parse('2026-10-13T15:24:00+02:00'));
assert(quoteHtml.includes('13.31'));
assert(quoteHtml.includes('13.32'));
assert(quoteHtml.includes('Societe Generale OTC'));
assert(quoteHtml.includes('keine Orderannahme oder ausführbare Preisgarantie'));
assert(b.compactProductCard(quoteProduct).includes('DEGIRO zeigt Geld/Brief'));
assert(!b.compactProductCard({isin:'DE000FG4JXV7',snapshot:quoteProduct.snapshot}).includes('DEGIRO zeigt Geld/Brief'));
assert.equal(b.currentQuote({...quoteProduct,price:13.32},Date.parse('2026-10-13T15:24:00+02:00')),false);
const parsed=b.detailScreenshotData(degiroText,'DE000BOB0018');
assert(parsed.ok,parsed.reason);
assert(parsed.degiroDisplayedQuote?.brokerDisplayConfirmed);
assert.equal(parsed.degiroDisplayedQuote?.venue,'Societe Generale OTC');
assert.equal(parsed.ask,13.32);
assert.equal(parsed.bid,13.31);
const savedQuote=b.mergeScreenshotEvidence(null,parsed,'dated-market-screen.png');
const companion=b.mergeScreenshotEvidence(savedQuote,{
 isin:'DE000BOB0018',direction:'LONG',price:'13.31',leverage:'27.76',
 bid:null,ask:null,currency:'EUR',sourceTime:'',times:{},terms:{}
},'product-overview-no-bid-ask.png');
assert.equal(companion.bid,13.31);
assert.equal(companion.ask,13.32);
assert.equal(companion.price,13.32);
assert.equal(companion.leverage,27.76);
assert.equal(companion.degiroDisplayedQuote?.sourceTime,'13/10/2026 15:23');
assert.equal(companion.evidence.Geld?.value,13.31);
assert.equal(companion.evidence.Brief?.value,13.32);
assert(!b.currentQuote({isin:'DE000BOB0018',price:13.32,quote:{...companion}},Date.parse('2026-10-13T15:24:00+02:00')));

