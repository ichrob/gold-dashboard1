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
const strict=b.productTermsStatus(p,now);assert(!strict.complete);assert(strict.reasons.some(r=>r.includes('datierter')));
assert(!strict.reasons.some(r=>r.includes('widerspricht Produktquelle')),'same displayed four decimals are not a conflict');
const research=b.productTermsStatus(p,now,true);assert(research.complete,JSON.stringify(research));assert.equal(research.warnings.length,2);
const context={now,spot:4200,spotFresh:true,direction:'SHORT',atr:15,trend:'SHORT',trend2:'SHORT',mtf:'SHORT',rsi:40,hist:-1,adx:30,momentum:-1};
const recommendations=b.indicativeRecommendations([p],context);assert.equal(recommendations.length,1);assert(recommendations[0].warning.includes('Gültigkeitsdatum nicht bestätigt'));assert(recommendations[0].warning.includes('Aufnahmeserie'));
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
assert(detailStatus.reasons.some(r=>r.includes('datierter Produktnachweis')),'actual validity gap remains');
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
