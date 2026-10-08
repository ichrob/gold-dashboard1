const fs=require('fs'),vm=require('vm'),assert=require('assert');
const fixtures=JSON.parse(fs.readFileSync('test_fixtures/sg_swiss_fg34xv8_20261007.json','utf8'));
const ctx={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,isin='DE000FG34XV8';
for(const f of fixtures)for(const pass of f.passes){
 const x=b.detailScreenshotData(pass.text,isin);assert(x.ok,x.reason);
 assert.equal(x.currency,'CHF');assert.equal(x.price,'','native CHF is never a EUR product price');
 if(f.image==='1000071159.jpg'){
  assert.equal(x.terms.strike.value,4524.4731);assert.equal(x.terms.ko.value,4524.4731);
  assert.equal(x.terms.ko.displayDecimals,4);assert.equal(x.terms.ratio.value,.1);
  assert.equal(x.leverage,'9.533');assert.equal(x.direction,'SHORT');
  assert.equal(x.terms.strike.at,null);assert.equal(x.terms.strike.dateText,null);
  assert.equal(x.bid,null,'undated browser-title quotes are not body quotes');
 }else{
  assert.equal(x.identityBasis,'Valor');assert.equal(x.identityValor,'159787428');
  const newer=f.image==='1000071157.jpg';
  assert.equal(x.bid,newer?35.72:35.67);assert.equal(x.ask,newer?35.73:35.68);
  if(newer)assert.equal(x.sourceTime,'07.10.2026 16:21:28');
  else assert(x.times.quote.present,'unreadable original time remains present, never borrowed');
 }
 assert(!b.detailScreenshotData(pass.text,'DE000FG7EPT1').ok);
 assert(!b.detailScreenshotData(pass.text.replaceAll('159787428','159787429'),isin,{isin,basis:'opened-product'}).ok);
}
const text=fixtures[0].passes[0].text;
assert.equal(b.unconfirmedOcrFields(text,fixtures[0].passes.map(p=>p.text)).length,0);
for(const bad of ["4'52.4731","45'24.4731","4'524.O731"]){assert.equal(b.strictOcrNumber(bad),null);assert(b.parseProductTerms('sg-zertifikate.ch\nStrike '+bad+' USD').error);}
assert.equal(b.strictOcrNumber("4’524.4731"),4524.4731);
const rawQuote=fixtures[1].passes[0].text;
assert(!b.detailScreenshotData(rawQuote+'\nISIN DE000FG7EPT1',isin).ok);
const outcomes=fixtures.map(f=>({ok:true,name:f.image,raw:f.reviewedText||f.passes[0].text,data:b.detailScreenshotData(f.reviewedText||f.passes[0].text,isin)}));
const series=b.linkScreenshotSeries(outcomes);assert(series);
assert.equal(series.text,'07.10.2026 16:21:24');
assert.equal(outcomes[0].data.times.leverage.at,'2026-10-07T14:21:24.000Z');assert(outcomes[0].data.times.leverage.fromSeries);
assert.equal(outcomes[1].data.sourceTime,'07.10.2026 16:21:28');assert.equal(outcomes[2].data.sourceTime,'07.10.2026 16:21:24');
let snapshot;
for(const o of [outcomes[0],outcomes[2],outcomes[1]])snapshot=b.mergeScreenshotEvidence(snapshot,o.data,o.name);
assert.equal(snapshot.bid,35.72);assert.equal(snapshot.ask,35.73);assert.equal(snapshot.price,'');
assert.equal(snapshot.evidence.Brief.currency,'CHF');assert.equal(snapshot.evidence.Hebel.value,'9.533');assert(snapshot.evidence.Hebel.fromSeries);
assert.equal(snapshot.terms.ko.at,null);assert.equal(snapshot.terms.ko.dateText,null);assert.equal(snapshot.terms.strike.at,null);
assert(b.screenshotSummary(snapshot).includes('Brief CHF'));
const now=Date.parse('2026-10-07T14:22:00Z'),at='2026-10-07T14:21:28Z';
const conditions=Object.fromEntries(Object.entries({underlying:'XAU/USD',currency:'CHF',type:'BEST Turbo-Optionsscheine',maturity:'Open End',ratio:.1}).map(([key,value])=>[key,{value,at:null,conditionVerified:true,source:'SG',reviewedAt:at}]));
const quote={isin,productVerified:true,metadata:{status:1,direction:'SHORT',underlyingType:'SPOT',ko:4524.473138,termsDated:false},source:'SG',checkedAt:at,conditions,currency:'EUR',ask:38.2311,currencyConversion:{fromCurrency:'CHF',toCurrency:'EUR',rate:1.07,at},price:38.2311,askAt:at,analysisMaxAgeSeconds:300};
const p={isin,isinConfirmed:true,productDirection:'SHORT',price:38.2311,ko:4524.4731,leverage:9.533,snapshot,quote};
assert(b.automaticIdentity(p));
const strict=b.productTermsStatus(p,now);assert(strict.complete,JSON.stringify(strict));
assert(!strict.reasons.some(r=>r.includes('widerspricht Produktquelle')),'same displayed four decimals are not a conflict');
const research=b.productTermsStatus(p,now,true);assert(research.complete,JSON.stringify(research));assert.equal(research.warnings.length,0);
const context={now,spot:4200,spotFresh:true,direction:'SHORT',atr:15,trend:'SHORT',trend2:'SHORT',mtf:'SHORT',rsi:40,hist:-1,adx:30,momentum:-1};
const recommendations=b.indicativeRecommendations([p],context);assert.equal(recommendations.length,1);assert(recommendations[0].warning.includes('Aufnahmeserie'));
assert(!b.finalProductStatus(p,now).complete);assert(!b.analysisReleaseQuote(p,now));assert(!b.currentQuote(p,now));
assert.equal(b.indicativeRecommendations([p],{...context,direction:'NEUTRAL'}).length,0);
for(const change of [
 {ko:4524.63},
 {price:35.73},
 {quote:{...quote,metadata:{...quote.metadata,ko:4524.4738}}},
 {quote:{...quote,metadata:{...quote.metadata,status:2}}},
 {quote:{...quote,currencyConversion:null}},
 {snapshot:{...snapshot,terms:{...snapshot.terms,strike:undefined}}},
 {snapshot:{...snapshot,terms:{...snapshot.terms,strike:{...snapshot.terms.strike,conflict:true}}}}
])assert.equal(b.indicativeRecommendations([{...p,...change}],context).length,0,JSON.stringify(change));
// The exact reviewed image matches only its SHA; filenames and edits never do.
(async()=>{
 const fixture=fixtures[2];
 ctx.crypto={subtle:{digest:async()=>Uint8Array.from(Buffer.from(fixture.sha256,'hex')).buffer}};
 assert.equal(await b.reviewedImageText({arrayBuffer:async()=>new ArrayBuffer(0)}),fixture.reviewedText);
 ctx.crypto=require('crypto').webcrypto;
 assert.equal(await b.reviewedImageText({name:fixture.image,arrayBuffer:async()=>Buffer.from('different pixels')}),null);
 console.log('Swiss original images: Valor, CHF isolation, precision, series clocks and labelled indicative analysis passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

// Native currency is an informational import result, not a partial failure.
const successSummary=b.screenshotBatchSummary(outcomes.map(o=>({...o,reason:'zugeordnet'})));
assert(successSummary.startsWith('✓ 3 von 3'));assert(!successSummary.includes('teilweise'));
assert(outcomes[1].data.importNotes.some(s=>s.includes('CHF-Originalkurse')));
assert(b.screenshotBatchSummary([{ok:true,data:{importWarnings:['Brief fehlt']},name:'partial',reason:'partial'}]).includes('teilweise'));
const upload=b.renderUploadMissing(p,{reasons:['Basispreis in USD: Wert eingelesen; gültiger datierter Nachweis fehlt oder ist älter als 24 Stunden','Knock-out-Schwelle: datierter Produktnachweis fehlt oder älter als 24 Stunden','CHF-Kursbild vorhanden; zeitlich passende EUR-Umrechnung für diesen Nachweis fehlt']});
assert(upload.includes('Für die Live-Freigabe noch offen'));assert(upload.includes('Wert aus dem Bild übernommen'));assert(!upload.includes('direkt daneben'));assert(!upload.includes('Geld und Brief in EUR'));
assert(b.missingValueLocation('Basispreis fehlt',{}).includes('Stammdaten'));
assert(!b.finalProductStatus(p,now).complete,'presentation must not relax live gates');

// Screenshot retention is not live freshness; series timing is explicitly inferred.
const later=now+34*60000;
const snapshotFields=b.productFieldStates(p,later);
assert.equal(snapshotFields.leverage.state,'Momentaufnahme · innerhalb Nachweisfrist (14 h)');
assert(snapshotFields.leverage.fromSeries);
assert.equal(b.productFieldStates(p,now+15*3600000).leverage.state,'veraltet');
const detailStatus=b.selectionDetailStatus(p,now);
assert(!detailStatus.reasons.some(r=>r.startsWith('KO-Barriere mit')),'display rounding must not create a second KO gap');
assert(!detailStatus.reasons.some(r=>r.includes('datierter Produktnachweis')),'series is accepted for term validity');
const koReason='KO-Barriere mit gültigem Nachweis oder festen Screenshotwert bestätigen';
const card=b.compactProductCard(p,['Knock-out-Schwelle: datierter Produktnachweis fehlt oder älter als 24 Stunden',koReason]);
assert.equal((card.match(/<strong>KO-Barriere: Gültigkeitsnachweis offen<\/strong>/g)||[]).length,1);
assert(!card.includes('KO-Barriere: gültiger Nachweis (Stammdaten)'));
assert(card.includes('Zeitbezug der Aufnahmeserie'));
assert(!b.productTermsStatus({...p,ko:4524.63},now).complete,'real KO mismatch remains blocked');

// Secondary evidence fills term validity without granting a quote or market signal.
const secondaryConditions={...quote.conditions,...Object.fromEntries(['strike','ko'].map(key=>[key,{value:4524.4731,source:'https://www.finanzen.ch/derivate/'+isin.toLowerCase(),dateText:'07.10.2026',reviewedAt:at,at:null,conditionVerified:true,secondary:true}]))};
const secondaryProduct={...p,quote:{...quote,conditions:secondaryConditions,metadata:{...quote.metadata,termsDated:true,termsDate:'07.10.2026'}}};
assert(b.productTermsStatus(secondaryProduct,now).complete,JSON.stringify(b.productTermsStatus(secondaryProduct,now)));
assert(!b.finalProductStatus(secondaryProduct,now).complete,'currency/quote evidence still required');
const secondaryUi=b.renderSecondaryValidity({secondaryValidity:{state:'open',sources:[{provider:'finanzen.ch',state:'observed',terms:{ko:{value:4526.54,assessment:'Abweichender Wert; nicht übernommen',dateText:null}}}]}});
assert(secondaryUi.includes('Abweichender Wert'));assert(secondaryUi.includes('nicht angegeben'));
assert(b.renderSecondaryValidity({secondaryValidity:{state:'checking',sources:[]}}).includes('Hintergrund'));

assert(b.productDataStatus(p,now).complete,JSON.stringify(b.productDataStatus(p,now)));
assert.equal(b.productCompletionBadge(p,now),'','the redundant completion badge was intentionally removed');
assert(!b.finalProductStatus(p,now).complete,'analysis completeness must not grant live release');
assert(!b.productDataStatus(p,now+15*3600000).complete,'expired series');
for(const mutate of [
 x=>x.snapshot.captureSeries=null,
 x=>x.snapshot.terms.strike.source='older.jpg',
 x=>x.snapshot.times.quote={present:true,text:'invalid'},
 x=>x.snapshot.evidence.Hebel.at='2026-10-06T14:21:28Z',
 x=>x.snapshot.isin='DE000PJ9NCK0',
 x=>x.ko=4524.63,
 x=>x.quote.currencyConversion=null
]){const bad=JSON.parse(JSON.stringify(p));mutate(bad);assert(!b.productDataStatus(bad,now).complete,'invalid data must stay incomplete');}
console.log('Series analysis completeness separated from live validity, with identity, timing, currency and conflict checks');

ctx.Date=class extends Date {static now(){return now;}};
const neutralCard=b.compactProductCard(p,b.finalProductStatus(p,now).reasons,'Marktsignal neutral');
assert(!neutralCard.includes('data-series-complete'));
assert(neutralCard.includes('Aktualität nicht bestätigt'));
assert(neutralCard.includes('Aktuelle Auswahl:</b> nicht ausgewählt'));
assert(neutralCard.includes('Marktsignal neutral'));
assert(neutralCard.includes('Live-Freigabe'));
assert(!neutralCard.includes('datierter Hebel weiterhin erforderlich'));

const validity=b.renderTermSeriesValidity(p,now);
assert(validity.includes('Basispreis: Seriennachweis für Bob gültig'));
assert(validity.includes('KO-Schwelle: Seriennachweis für Bob gültig'));
assert(!b.productTermsStatus({...p,snapshot:{...snapshot,captureSeries:null}},now).complete);
assert(!b.productTermsStatus(p,now+25*3600000).complete);
for(const mutate of [
 x=>x.snapshot.captureSeries.members=['other.jpg'],
 x=>x.snapshot.terms.strike.dateText='06.10.2026',
 x=>x.snapshot.terms.strike.conflict=true,
 x=>x.snapshot.terms.ko.revoked=true
]){const bad=JSON.parse(JSON.stringify(p));mutate(bad);assert(!b.productTermsStatus(bad,now).complete);}
const auto=JSON.parse(JSON.stringify(p));delete auto.snapshot;auto.ko=4524.473138;
for(const key of ['strike','ko'])auto.quote.conditions[key]={value:4524.473138,source:'SG',at:null,conditionVerified:false,validitySeries:{policy:'declared-series-v1',origin:'automatic',isin,source:'SG',observedAt:at}};
assert(b.productTermsStatus(auto,now).complete,JSON.stringify(b.productTermsStatus(auto,now)));
assert(b.renderTermSeriesValidity(auto,now).includes('automatischen Abrufserie'));
assert(!b.finalProductStatus(auto,now).complete,'term validity alone is not a quote release');
for(const mutate of [
 x=>x.quote.conditions.strike.validitySeries.isin='DE000PJ9NCK0',
 x=>x.quote.conditions.strike.validitySeries.observedAt='2026-10-06T12:00:00Z',
 x=>x.quote.conditions.ko.validitySeries.observedAt='2026-10-08T12:00:00Z',
 x=>x.quote.conditions.strike.dateText='06.10.2026',
 x=>x.quote.conditions.ko.validitySeries.source='other',
 x=>x.quote.productVerified=false
]){const bad=JSON.parse(JSON.stringify(auto));mutate(bad);assert(!b.productTermsStatus(bad,now).complete);}

assert(b.finalProductStatus(auto,now,{isin,reviewed:true,paired:true,source:'reference',venue:'test',bid:38.22,ask:38.23,quoteAt:at}).complete,'accepted automatic series satisfies live term gate when separate quote evidence is valid');

// Real row refresh: API replaces rounded screenshot KO, then rankUI derives identity.
const refreshed=JSON.parse(JSON.stringify(p));refreshed.ko=4524.473138;
for(const key of ['strike','ko'])refreshed.quote.conditions[key]=JSON.parse(JSON.stringify(auto.quote.conditions[key]));
refreshed.isinConfirmed=b.automaticIdentity(refreshed);
assert(refreshed.isinConfirmed,'API full precision must preserve screenshot product identity');
assert(b.productDataStatus(refreshed,now).complete,'real refreshed row stays complete');
assert(!b.finalProductStatus(refreshed,now).reasons.some(r=>/Produktzuordnung|Basispreis|Knock-out-Schwelle/.test(r)));
assert(b.finalProductStatus(refreshed,now).reasons.some(r=>r.includes('CHF-Kursbild')),'independent FX evidence is not bypassed');
const roundedWithoutApi=JSON.parse(JSON.stringify(p));roundedWithoutApi.ko=4524.473138;delete roundedWithoutApi.quote;
assert(b.automaticIdentity(roundedWithoutApi),'recorded display precision establishes numeric equivalence');
assert(!b.automaticIdentity({...roundedWithoutApi,ko:4524.63}),'real KO discrepancy remains rejected');
const updated=JSON.parse(JSON.stringify(refreshed));updated.ko=4525;
updated.quote.metadata.ko=4525;updated.quote.conditions.ko.value=4525;
assert(b.automaticIdentity(updated),'accepted fresh automatic term series can update a mutable barrier');
updated.quote.conditions.ko.validitySeries.observedAt='2026-10-05T12:00:00Z';
assert(!b.automaticIdentity(updated),'expired observations cannot justify a changed barrier');
assert(!b.automaticIdentity({...refreshed,productDirection:'LONG'}));
console.log('Actual refresh identity: rounded KO, accepted automatic updates, expiry and conflicts passed');

// Current native quote + dated FX supersedes the historical image quote only.
const chfCurrent=JSON.parse(JSON.stringify(refreshed));
const nativeBid=34.52,nativeAsk=34.53,fxRate=.9/.84;
chfCurrent.price=nativeAsk*fxRate;
chfCurrent.quote.nativeChartEvidence={currency:'CHF',bid:nativeBid,ask:nativeAsk,pointAt:at};
chfCurrent.quote.currencyConversion={fromCurrency:'CHF',toCurrency:'EUR',rate:fxRate,source:'exchangerate.dev',at,nativeAt:at,evidence:{base:'USD',eur:.9,chf:.84,dataAt:at,eurAt:at,chfAt:at,eurSource:'live',chfSource:'live',marketSession:'open'}};
chfCurrent.quote.analysisQuote={currency:'EUR',bid:nativeBid*fxRate,ask:chfCurrent.price,price:chfCurrent.price,bidAt:at,askAt:at,source:'SG converted chart',priceKind:'issuer-chart',isExecutableQuote:false};
chfCurrent.quote.price=chfCurrent.price;
const originalSnapshot=JSON.stringify(chfCurrent.snapshot);
assert(b.currentConvertedChfEvidence(chfCurrent,now));
assert(b.finalProductStatus(chfCurrent,now).complete,JSON.stringify(b.finalProductStatus(chfCurrent,now)));
const currentContext={...context,now};
const chfCandidate=b.conditionalCandidate(chfCurrent,currentContext,now);
assert(chfCandidate.ok,JSON.stringify(chfCandidate));
assert(chfCandidate.priceKind.includes('Hebel aus Momentaufnahme'));
assert(chfCandidate.warnings.some(s=>s.includes('kein aktueller berechneter Hebel')));
assert(b.selectionWorkflow([chfCurrent],currentContext,{}).approved);
assert(!b.selectionWorkflow([chfCurrent],{...currentContext,direction:'NEUTRAL'},{}).approved);
assert(!b.selectionWorkflow([{...chfCurrent,ko:4201}],currentContext,{}).approved);
assert(!b.currentQuote(chfCurrent,now),'analysis approval never claims executable quote');
assert.equal(JSON.stringify(chfCurrent.snapshot),originalSnapshot,'historical screenshot remains unmodified');
assert(b.compactProductCard(chfCurrent,[]).includes('data-current-chf-proof'));
assert(!b.currentConvertedChfEvidence(chfCurrent,now+301000));
for(const mutate of [
 x=>x.quote.currencyConversion.evidence.chfAt='2026-10-07T14:19:00Z',
 x=>x.quote.currencyConversion.evidence.chfAt='2026-10-07T14:23:00Z',
 x=>x.quote.currencyConversion.evidence.chfSource='cached',
 x=>x.quote.currencyConversion.evidence=null,
 x=>x.quote.currencyConversion.rate=1.2,
 x=>x.quote.analysisQuote.ask+=.1,
 x=>x.quote.nativeChartEvidence.ask+=.1,
 x=>x.snapshot.evidence.Hebel.at='2026-10-06T12:00:00Z',
 x=>x.snapshot.evidence.Hebel.value=99,
 x=>x.snapshot.isin='DE000PJ9NCK0',
 x=>x.quote.metadata.status=2,
 x=>x.quote.productVerified=false
]){const bad=JSON.parse(JSON.stringify(chfCurrent));mutate(bad);assert(!b.currentConvertedChfEvidence(bad,now));}
console.log('Current CHF/FX selection: coherent timestamps and arithmetic, snapshot preservation, market/risk gates passed');
