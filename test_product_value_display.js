const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro,isin='DE000SQ02JQ6',now=Date.now(),at=new Date(now-1000).toISOString();
const p={isin,index:0,price:100,quote:{isin,productVerified:true,found:false,analysisQuote:{currency:'EUR',bid:180.2,ask:180.21,bidAt:at,askAt:at,source:'SG',priceKind:'issuer-chart'},leverage:2.0447,leverageAt:at}};
let f=b.productFieldStates(p,now);
assert.equal(f.ask.value,180.21);assert.equal(f.bid.value,180.2);assert.equal(f.leverage.value,2.0447);
assert(b.compactProductCard(p).includes('Analysewerte vorhanden · ausführbarer Kurs separat offen'));
// A displayed DEGIRO list/reference price is not a confirmed issuer ask.
const listOnly={isin:'DE000FG7K3G2',index:9,productDirection:'SHORT',price:6.58,leverage:56.4793};
const listFields=b.productFieldStates(listOnly,now);
assert.equal(listFields.bid.state,'fehlt');
assert.equal(listFields.ask.state,'fehlt');
assert.equal(listFields.leverage.value,56.4793);
const listCard=b.compactProductCard(listOnly);
assert(listCard.includes('Gespeicherter Produkt-/Listenpreis: 6.58 EUR'),listCard);
assert(listCard.includes('Fehlende Kurswerte: Geld, Brief'),listCard);
assert(!listCard.includes('✓</span> Brief 6.58'),listCard);
const separatelySourced={...listOnly,snapshot:{isin:listOnly.isin,currency:'EUR',
 bid:null,ask:6.58,evidence:{Brief:{value:6.58,source:'DEGIRO-Kursansicht',at}}}};
assert.equal(b.productFieldStates(separatelySourced,now).bid.state,'fehlt');
assert.equal(b.productFieldStates(separatelySourced,now).ask.value,6.58);

// A correct shared time is not red merely because another field is absent.
const timedOnly={isin,index:1,quote:{isin,productVerified:true,found:false,eligible:false,
  metadata:{status:1},analysisQuote:{bid:8,ask:8.02,currency:'EUR',priceKind:'issuer-chart',
  source:'SG',bidAt:at,askAt:at}}};
const timeStatus=b.productObservedTimeStatus(timedOnly,now);
assert.equal(timeStatus.confirmed,true);
assert.equal(timeStatus.confirmedCount,2);
assert.deepEqual(Array.from(timeStatus.missing),['Hebel']);
assert(b.compactProductCard(timedOnly).includes('Zeitbezug für 2 vorhandene Kurs-/Hebelwerte bestätigt'));
assert(!b.finalProductStatus(timedOnly,now).complete);
assert.equal(b.productObservedTimeStatus(listOnly,now).confirmed,false);
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
// An undated SG issuer gearing is a known reference number, not a missing
// value or a dated leverage proof. Its issuer snapshot retrieval timestamp
// cannot change the trade eligibility gate or create leverageAt.
const researchIsin='DE000FG7N6Z2';
const sgReference={
 isin:researchIsin,index:7,isinConfirmed:true,productDirection:'LONG',
 quote:{isin:researchIsin,productVerified:true,found:false,eligible:false,
  metadata:{status:1,direction:'LONG',underlyingType:'SPOT',underlying:'XAU/USD'},
  analysisQuote:{bid:4.91,ask:4.92,currency:'EUR',
   priceKind:'issuer-chart',isExecutableQuote:false,bidAt:at,askAt:at},
  issuerLeverageReference:{value:72.9254,dated:false,sourceAt:null,retrievedAt:at}}
};
const refFields=b.productFieldStates(sgReference,now);
assert.equal(refFields.leverage.state,'fehlt');
assert(refFields.leverage.value == null);
const refHtml=b.compactProductCard(sgReference);
assert(refHtml.includes('SG-Hebelreferenz vorhanden · eigene Quellenzeit fehlt'),refHtml);
assert(refHtml.includes('72.9254'),refHtml);
assert(refHtml.includes('Aktueller Hebel nicht zeitlich bestätigt'),refHtml);
assert(refHtml.includes('keine SG-Hebelquellenzeit'),refHtml);
assert(!refHtml.includes('Daten vollständig'),refHtml);
assert(!b.currentQuote(sgReference,now));

// A missing numeric SG source field is not cured by attaching a timestamp.
const noIssuerReference=structuredClone(sgReference);
delete noIssuerReference.quote.issuerLeverageReference;
noIssuerReference.quote.importActive=true;
const withoutReferenceHtml=b.compactProductCard(noIssuerReference);
assert(withoutReferenceHtml.includes('SG-Referenzhebel: Von der automatisch abgefragten SG-Quelle nicht geliefert'),withoutReferenceHtml);
assert(withoutReferenceHtml.includes('Ein gemeinsamer Zeitbezug belegt nur vorhandene Werte'),withoutReferenceHtml);
assert(!b.currentQuote(noIssuerReference,now));

// A verified common collection time is visible but not a tradeable gearing clock.
const linkedSg=structuredClone(sgReference);
linkedSg.quote.metadata.status=1;
linkedSg.quote.chartEvidence={pointAt:at,bid:4.91,ask:4.92,currency:'EUR'};
linkedSg.quote.sharedTimeContext={at,isin:researchIsin,kind:'issuer-collection',
 timeOrigin:'SG-Chartzeit',fields:['Geld','Brief','Referenzhebel']};
linkedSg.quote.issuerLeverageReference.sharedContextAt=at;
linkedSg.quote.issuerLeverageReference.eligible=false;
linkedSg.quote.sharedTimeContext.fields=['Geld','Brief','Referenzhebel','ko','ratio','currency'];
linkedSg.quote.sharedValueObservations={
 Geld:{value:4.91,contextAt:at,isin:researchIsin},
 Brief:{value:4.92,contextAt:at,isin:researchIsin},
 ko:{value:4075,contextAt:at,isin:researchIsin},
 ratio:{value:0.1,contextAt:at,isin:researchIsin},
 currency:{value:'EUR',contextAt:at,isin:researchIsin},
 'Referenzhebel':{value:72.9254,contextAt:at,isin:researchIsin}
};
for(const [field,value] of Object.entries({'Geld':4.91,'Brief':4.92,ko:4075,
 ratio:0.1,currency:'EUR',Hebel:72.9254})){
 const evidence=b.sharedProductFieldTime(linkedSg,field,value,now);
 assert(evidence&&evidence.valid,field);
 assert.equal(evidence.at,at);
 assert.equal(evidence.kind,'issuer-collection');
}
assert.equal(b.sharedProductFieldTime(linkedSg,'ko',4076,now),null);
const linkedFields=b.productFieldStates(linkedSg,now);
assert.equal(linkedFields.leverage.value,72.9254);
assert.equal(linkedFields.leverage.at,at);
assert(linkedFields.leverage.state.includes('gemeinsamer SG-Zeitbezug'),linkedFields.leverage.state);
assert.equal(linkedFields.leverage.kind,'issuer-reference');
const linkedHtml=b.compactProductCard(linkedSg);
assert(linkedHtml.includes('SG-Referenzhebel (gemeinsamer Zeitbezug)'),linkedHtml);
assert(linkedHtml.includes('Gemeinsamer Hebel-Zeitbezug bestätigt'),linkedHtml);
assert(linkedHtml.includes('72.9254'),linkedHtml);
assert(!b.currentQuote(linkedSg,now));
// FX may be older than the source chart; the issuer context stays native.
const convertedLinked=structuredClone(linkedSg);
convertedLinked.quote.nativeChartEvidence={...linkedSg.quote.chartEvidence,currency:'CHF'};
convertedLinked.quote.chartEvidence.pointAt=new Date(now-30000).toISOString();
assert.equal(b.sharedProductFieldTime(convertedLinked,'Hebel',72.9254,now).at,at);
assert(!b.currentQuote(convertedLinked,now));
convertedLinked.quote.nativeChartEvidence.pointAt=new Date(now-5000).toISOString();
assert.equal(b.sharedProductFieldTime(convertedLinked,'Hebel',72.9254,now),null);
const badChartTime=structuredClone(linkedSg);
badChartTime.quote.chartEvidence.pointAt=new Date(now-5000).toISOString();
assert.equal(b.productFieldStates(badChartTime,now).leverage.state,'fehlt');
const badIsin=structuredClone(linkedSg);
badIsin.quote.sharedTimeContext.isin='DE000FG4JXV7';
assert.equal(b.productFieldStates(badIsin,now).leverage.state,'fehlt');
const outdatedLinked=structuredClone(linkedSg);
const older=new Date(now-600000).toISOString();
outdatedLinked.quote.chartEvidence.pointAt=older;
outdatedLinked.quote.sharedTimeContext.at=older;
outdatedLinked.quote.issuerLeverageReference.sharedContextAt=older;
assert(b.productFieldStates(outdatedLinked,now).leverage.state.includes('veraltet'));
assert.equal(b.productFieldStates(outdatedLinked,now).leverage.value,72.9254);

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
assert(listHtml.includes('✓ In deiner DEGIRO-Liste vorhanden'));
assert(!listHtml.includes('kein Nachweis'));
assert.equal(b.degiroListObservation(morningIsin,listArchive,late).currentDay,false);
assert(b.renderDegiroListEvidence({isin:morningIsin},late,listArchive).includes('älterer DEGIRO-Liste'));
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


// Native CHF broker observations stay CHF and never become EUR execution prices.
const chfDisplay=degiroText.replaceAll('€','CHF');
const chfObserved=b.parseDegiroDisplayedQuote(chfDisplay,'DE000BOB0018');
assert(chfObserved,'CHF bid/ask must be recognized');
assert.equal(chfObserved.currency,'CHF');
assert.equal(chfObserved.bid,13.31);
assert.equal(chfObserved.ask,13.32);
const chfParsed=b.detailScreenshotData(chfDisplay,'DE000BOB0018');
assert(chfParsed.ok,chfParsed.reason);
assert.equal(chfParsed.currency,'CHF');
assert.equal(chfParsed.price,'');
assert.equal(chfParsed.degiroDisplayedQuote.currency,'CHF');
const chfDisplayCard={isin:'DE000BOB0018',snapshot:chfParsed};
assert(b.renderDegiroDisplayedQuote(chfDisplayCard).includes('13.32 CHF'));
assert.equal(b.currentQuote(chfDisplayCard),false);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replace('Brief €','Brief CHF'),'DE000BOB0018'),null);
assert.equal(b.parseDegiroDisplayedQuote(degiroText.replaceAll('€','USD'),'DE000BOB0018'),null);

const calcProduct={isin:researchIsin,leverage:10,quote:{isin:researchIsin,productVerified:true,
 metadata:{status:1,simpleNonQuantoTurbo:true,ratio:.01},leverageCalculation:{available:true,fresh:true,value:10,at,
 inputs:{basisPriceUsd:4000,usdEur:1,ratio:.01,askNative:4,quoteCurrency:'CHF',askAt:at,basisAt:at,fxDataAt:at,fxEffectiveAt:at}}}};
assert.equal(b.calculatedLeverageEvidence(calcProduct,now).value,10);
assert.equal(b.calculatedLeverageEvidence(calcProduct,now+301000),null);
calcProduct.quote.leverageCalculation.value=11;calcProduct.leverage=11;
assert.equal(b.calculatedLeverageEvidence(calcProduct,now),null);

// Visually reviewed user original 1000073369.jpg, including independent Symbol.
const reviewedChf=`Kursdaten
Zuletzt CHF 16,95 16/10/2026 18:51
Geld CHF 16,95 Brief CHF 16,97
Geld Vol. 5K Brief Vol. 5K
Schluss CHF 15,88
Hoch CHF 19,06
Tief CHF 14,16
Symbol | ISIN
159788766 | DE000FG8NHQ3
Börse Societe Generale OTC`;
for(const alias of ['DE000FG8NHQ3','DEOOOFGSNHQ3','DE000FGSNHQ3']){
 const raw=reviewedChf.replace('DE000FG8NHQ3',alias);
 const parsed=b.detailScreenshotData(raw,'DE000FG8NHQ3');
 assert(parsed.ok,parsed.reason);
 assert.equal(parsed.degiroDisplayedQuote.venue,'Societe Generale OTC');
 assert.equal(parsed.degiroDisplayedQuote.bid,16.95);
 assert.equal(parsed.degiroDisplayedQuote.ask,16.97);
 assert.equal(parsed.degiroDisplayedQuote.currency,'CHF');
 assert.equal(parsed.degiroDisplayedQuote.sourceTime,'16/10/2026 18:51');
 assert.equal(parsed.degiroDisplayedQuote.isExecutableQuote,false);
 assert(!b.detailScreenshotData(raw,'DE000FG34XV8').ok);
}
const confusedChf=reviewedChf.replace('DE000FG8NHQ3','DEOOOFGSNHQ3');
for(const bad of [confusedChf.replace('159788766','159788767'),confusedChf.replace('Societe Generale OTC','Other Venue'),confusedChf+'\nISIN DE000FG34XV8']){
 assert(!b.detailScreenshotData(bad,'DE000FG8NHQ3').ok,'Do not guess identity without matching independent evidence');
}
