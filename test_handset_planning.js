'use strict';
const assert=require('node:assert/strict'),{evaluate}=require('./handset_planning');
const now=Date.parse('2026-11-13T10:00:00Z'),at=new Date(now-10000).toISOString(),isin='DE000FG14AV8';
function fixture(direction='LONG',currency='CHF'){
 const sign=direction==='LONG'?1:-1,ko=4200-sign*300;
 const q={isin,found:true,productVerified:true,currency,source:'fixture',bid:20,ask:20.1,bidAt:at,askAt:at,isExecutableQuote:true,
  metadata:{status:1,currency,direction},productModel:{isin,verifiedSimpleTurbo:true,underlying:'XAU/USD',direction,ko,strike:ko,ratio:.1}};
 return {now,products:[{isin,productDirection:direction,ko}],quotes:{[isin]:q},
  plans:{[direction]:{available:true,direction,entry:4200,stop:4200-sign*30,target:4200+sign*60,atr:10,at}},
  spots:{usd_chf_meta:{rate:.9,fetchedAt:at},usd_eur_meta:{rate:.9,fetchedAt:at}},
  config:{budgetCHF:1000,riskCHF:100,feesCHF:8,trailAtr:1.5,minRR:2},
  report:{status:'ok',lastCheckedAt:at,items:[{isin,state:'analysis-evidence-complete',handsetObservation:{
   code:'PARTIAL',researchOnly:true,verified:false,tradeApproved:false,executionConfirmed:false,sourceTime:null,observedAt:at,
   fields:{Geld:'20,20',Brief:'20,30',Währung:currency,Handelsplatz:'SG OTC',Anzeigezeit:'13/11/2026 10:00',Hinweis:'Keine Aussage zur Handelbarkeit'}}}]}};
}
for(const direction of ['LONG','SHORT'])for(const currency of ['CHF','EUR']){
 const input=fixture(direction,currency),before=JSON.stringify(input),x=evaluate(input).items[0];
 assert(x.available,JSON.stringify(x));
 assert.equal(x.quantity,30);assert(Math.abs(x.totalCHF-617)<1e-8);
 assert(Math.abs(x.lossCHF-98)<1e-8);assert(Math.abs(x.modelStop-17.3)<1e-8);
 assert.equal(x.sourceAt,null);assert.equal(x.copyAllowed,false);assert.equal(x.rankingPenalty,false);
 assert.equal(JSON.stringify(input),before);
}
for(const change of [x=>x.config=null,x=>x.plans={},x=>x.spots={},
 x=>x.report.items[0].state='terminated',x=>x.quotes[isin].metadata.status=2,
 x=>x.quotes[isin].productModel.verifiedSimpleTurbo=false,
 x=>x.quotes[isin].bidAt=new Date(now-100000).toISOString(),
 x=>x.report.items[0].handsetObservation.observedAt=new Date(now-15*3600000).toISOString()]){
 const input=fixture('LONG','EUR');change(input);assert.equal(evaluate(input).items[0].available,false);
}
const noScreen=fixture();delete noScreen.report.items[0].handsetObservation;
const unconfirmed=evaluate(noScreen).items[0];
assert.equal(unconfirmed.available,false);
assert.equal(unconfirmed.entryApproved,false);
assert.equal(unconfirmed.copyAllowed,false);
assert.equal(unconfirmed.planState,'reference-calculated');
assert(unconfirmed.modelStop>0&&unconfirmed.modelTarget>0);
assert(unconfirmed.reasons.some(r=>/Lesebeleg/.test(r)));
// A current derived quote supports per-product paper planning without
// pretending a missing original dealer bid/ask or handset proof exists.
const synthetic=fixture('LONG','EUR');
delete synthetic.report.items[0].handsetObservation;
delete synthetic.quotes[isin].bid;
delete synthetic.quotes[isin].ask;
synthetic.quotes[isin].found=false;
synthetic.spots.xaus=4200;
synthetic.spots.is_genuine_xauusd_spot=true;
synthetic.spots.spot_price_as_of=at;
synthetic.quotes[isin].productModel.tradingEndAt=new Date(now+3600000).toISOString();
synthetic.quotes[isin].calculatedProduct={
 kind:'calculated-turbo',available:true,currency:'EUR',direction:'LONG',
 bidEur:20,askEur:20.1,goldUsd:4200,usdEur:.9,ratio:.1,strikeUsd:3900,
 priceAt:at,goldAt:at,fxDataAt:at,fxEffectiveAt:at,calculatedAt:at,
 referenceAt:new Date(now-180000).toISOString(),validation:{ready:false}};
const prior=JSON.stringify(synthetic),modeled=evaluate(synthetic).items[0];
assert.equal(JSON.stringify(synthetic),prior);
assert.equal(modeled.available,false);
assert.equal(modeled.entryApproved,false);
assert.equal(modeled.copyAllowed,false);
assert.equal(modeled.simulationPlanningUsable,true);
assert.equal(modeled.simulationFillAllowed,false);
assert.equal(modeled.modelMode,'anchored-estimate');
assert.equal(modeled.planState,'model-only-reference');
assert.equal(modeled.modelEntry,20.1);
assert.equal(modeled.modelStop,17.3);
assert.equal(modeled.modelTarget,25.4);
const intrinsic=JSON.parse(prior);
delete intrinsic.quotes[isin].calculatedProduct;
const planOnly=evaluate(intrinsic).items[0];
assert.equal(planOnly.modelMode,'intrinsic-only');
assert.equal(planOnly.modelStop,24.3);
assert.equal(planOnly.simulationFillAllowed,false);
const tooOld=JSON.parse(prior);
tooOld.spots.spot_price_as_of=new Date(now-70000).toISOString();
assert.equal(evaluate(tooOld).items[0].simulationPlanningUsable,false);
const terminatedModel=JSON.parse(prior);
terminatedModel.report.items[0].state='terminated';
assert.equal(evaluate(terminatedModel).items[0].modelStop,null);
// Gold-denominated stop/target remains informative when product terms cannot
// yield a verified EUR/CHF stop. It never becomes a product entry price.
const goldOnly=fixture('LONG','EUR');
goldOnly.spots.xaus=4200;
goldOnly.spots.is_genuine_xauusd_spot=true;
goldOnly.spots.spot_price_as_of=at;
delete goldOnly.quotes[isin].productModel;
goldOnly.quotes[isin].handsetModelCheck={
 code:'DATED_TERMS_MISSING',reason:'Originale datierte Vertragsbedingungen fehlen',
 unconfirmedTerms:['ko','strike']};
const goldOriginal=JSON.stringify(goldOnly),goldRow=evaluate(goldOnly).items[0];
assert.equal(JSON.stringify(goldOnly),goldOriginal);
assert.equal(goldRow.planState,'reference-unavailable');
assert.equal(goldRow.modelStop,null);
assert.equal(goldRow.goldReference.state,'available');
assert.equal(goldRow.goldReference.unit,'USD/oz');
assert.equal(goldRow.goldReference.stop,4170);
assert.equal(goldRow.goldReference.target,4260);
assert.equal(goldRow.modelEvidenceCode,'DATED_TERMS_MISSING');
assert.equal(goldRow.modelEstimateReason,'Originale datierte Vertragsbedingungen fehlen');
assert.equal(goldRow.entryApproved,false);
assert.equal(goldRow.simulationFillAllowed,false);
const oldGold=JSON.parse(goldOriginal);
oldGold.spots.spot_price_as_of=new Date(now-70000).toISOString();
assert.equal(evaluate(oldGold).items[0].goldReference.state,'unavailable');
const wrongGold=JSON.parse(goldOriginal);
wrongGold.spots.xaus=4100;
assert.equal(evaluate(wrongGold).items[0].goldReference.state,'unavailable');
const uncertainIssuer=JSON.parse(goldOriginal);
uncertainIssuer.report.items[0].state='incomplete';
assert.equal(evaluate(uncertainIssuer).items[0].goldReference.state,'unavailable',
 'transient issuer status must not obtain even a display reference');
const issuerStopped=JSON.parse(goldOriginal);
issuerStopped.report.items[0].state='terminated';
assert.equal(evaluate(issuerStopped).items[0].goldReference,undefined);
const missing=fixture();missing.config=null;
const row=evaluate(missing).items[0];assert(row.modelStop>0);assert.equal(row.available,false);
console.log('Server handset scenarios: shared LONG/SHORT stops, EUR/CHF costs, missing config/FX, terminal/stale guards, no input mutation passed');

// The automatic tariff is a per-product reserve, never a silent zero/default.
const auto=fixture('LONG','EUR');
auto.config={...auto.config,feesCHF:null,feeProfile:'CH_STANDARD',fxMode:'AUTO_CHF'};
const automatic=evaluate(auto).items[0];
assert.equal(automatic.feeAssessment.feesCHF,6); // EUR 1 roundtrip + CHF 5 FX capital reserve.
assert.equal(automatic.feeAssessment.estimated,true);
assert(automatic.available);
assert(automatic.lossCHF<=auto.config.riskCHF&&automatic.totalCHF<=auto.config.budgetCHF);
assert.equal(auto.config.feesCHF,null);
for(const venue of ['SOCIETE GENERALE OTC','BNP OTC']){
 const input=JSON.parse(JSON.stringify(auto));input.report.items[0].handsetObservation.fields.Handelsplatz=venue;
 assert.equal(evaluate(input).items[0].feeAssessment.feesCHF,6);
}
for(const change of [x=>x.config.feeProfile='unknown',x=>x.config.fxMode='unknown',
 x=>x.report.items[0].handsetObservation.fields.Handelsplatz='Swiss DOTS',
 x=>x.report.items[0].handsetObservation.fields.Handelsplatz='Société Générale',
 x=>x.report.items[0].handsetObservation.fields.Handelsplatz='SG OTC / Frankfurt',
 x=>x.spots={},x=>x.now=Date.parse('2026-12-14T00:00:00Z')]){
 const input=JSON.parse(JSON.stringify(auto));change(input);
 const output=evaluate(input).items[0];
 assert.equal(output.feeAssessment.available,false);assert.equal(output.feeAssessment.feesCHF,null);
 assert.equal(output.available,false);assert.equal(output.rankingPenalty,false);
}
const frankfurt=JSON.parse(JSON.stringify(auto));
frankfurt.report.items[0].handsetObservation.fields.Handelsplatz='Zertifikate-Börse Frankfurt';
frankfurt.config.fxMode='NO_CONVERSION';
assert.equal(evaluate(frankfurt).items[0].feeAssessment.feesCHF,6);
const chf=JSON.parse(JSON.stringify(auto));
chf.report.items[0].handsetObservation.fields['Währung']='CHF';
assert.equal(evaluate(chf).items[0].feeAssessment.feesCHF,1);
const manual=JSON.parse(JSON.stringify(auto));manual.config.feesCHF=0;manual.config.feeProfile='unknown';
assert.equal(evaluate(manual).items[0].feeAssessment.feesCHF,0);
console.log('Automatic CH tariff: venue-specific roundtrip, processing, FX reserve, unknown/stale rejection, manual override passed');

const unresolved=JSON.parse(JSON.stringify(auto));
unresolved.config.feeProfile='unknown';unresolved.config.fxMode='unknown';
const saved=JSON.stringify(unresolved),conditional=evaluate(unresolved);
assert.equal(conditional.available,0);assert.equal(conditional.conditionalAvailable,1);
assert.equal(conditional.items[0].automaticScenarios.length,2);
assert.deepEqual(Array.from(conditional.items[0].automaticScenarios,s=>s.feeAssessment.feesCHF),[1,6]);
for(const scenario of conditional.items[0].automaticScenarios){
 assert(scenario.available);assert.equal(scenario.copyAllowed,false);assert.equal(scenario.settingsConfirmed,false);
 assert.equal(scenario.orderSubmitted,false);assert.equal(scenario.rankingPenalty,false);
 assert(scenario.totalCHF<=unresolved.config.budgetCHF);assert(scenario.lossCHF<=unresolved.config.riskCHF);
 assert.equal(scenario.assumptions.length,2);
}
assert.equal(JSON.stringify(unresolved),saved);
for(const change of [x=>x.plans={},x=>x.report.items[0].state='terminated',
 x=>x.report.items[0].handsetObservation.fields.Handelsplatz='Swiss DOTS',
 x=>x.now=Date.parse('2026-12-14T00:00:00Z'),x=>x.spots={}]){
 const input=JSON.parse(saved);change(input);
 const result=evaluate(input);assert.equal(result.conditionalAvailable,0);
 assert(result.items[0].automaticScenarios.every(s=>!s.available));
}
assert.equal(evaluate(manual).items[0].automaticScenarios.length,0);
assert.equal(evaluate(missing).items[0].automaticScenarios.length,0);
console.log('Automatic conditional scenarios: both FX modes, no config mutation, original stop/KO/quote guards and no approval promotion passed');

// Venue is optional for research. Unknown venue produces explicit tariff
// alternatives, never a silently selected broker route or a zero fee.
for(const direction of ['LONG','SHORT'])for(const currency of ['EUR','CHF']){
 const input=fixture(direction,currency);
 input.config={...input.config,feesCHF:null,feeProfile:'CH_STANDARD',fxMode:'AUTO_CHF'};
 delete input.report.items[0].handsetObservation.fields.Handelsplatz;
 const before=JSON.stringify(input),output=evaluate(input),row=output.items[0];
 assert.equal(output.conditionalAvailable,1);
 assert.equal(row.available,false);
 assert.equal(row.feeAssessment.available,false);
 assert.deepEqual(Array.from(row.automaticScenarios,s=>s.feeAssessment.feesCHF),currency==='CHF'?[1,6]:[6,11]);
 for(const scenario of row.automaticScenarios){
  assert(scenario.available);
  assert(scenario.assumptions.some(s=>s.includes('Handelsplatz unbestätigt')));
  assert.equal(scenario.feeAssessment.venue,null);
  assert.equal(scenario.feeAssessment.venueConfirmed,false);
  assert.equal(scenario.copyAllowed,false);
  assert.equal(scenario.entryApproved,false);
  assert.equal(scenario.orderSubmitted,false);
  assert.equal(scenario.rankingPenalty,false);
  assert(scenario.totalCHF<=input.config.budgetCHF);
  assert(scenario.lossCHF<=input.config.riskCHF);
 }
 assert.equal(JSON.stringify(input),before);
 for(const mutate of [x=>x.spots={},x=>x.plans={},
  x=>x.report.items[0].state='terminated',
  x=>x.report.items[0].handsetObservation.fields.Brief='',
  x=>x.report.items[0].handsetObservation.fields.Handelsplatz='Swiss DOTS',
  x=>x.report.items[0].handsetObservation.fields.Handelsplatz='SG OTC / Frankfurt',
  x=>x.now+=31*86400000]){
  const bad=JSON.parse(before);mutate(bad);
  assert.equal(evaluate(bad).conditionalAvailable,0);
 }
 input.config.feeProfile='unknown';input.config.fxMode='unknown';
 assert.equal(evaluate(input).items[0].automaticScenarios.length,4);
 input.config.feesCHF=8;
 assert.equal(evaluate(input).items[0].automaticScenarios.length,0);
}
console.log('Missing venue permits labelled research tariff alternatives; quote, FX, KO, status and manual-input guards remain intact');

for(const direction of ['LONG','SHORT']){
 const input=fixture(direction,'EUR');input.config.feesCHF=null;input.config.feeProfile='unknown';input.config.fxMode='unknown';
 input.plans[direction].entrySuitable=false;
 const original=JSON.stringify(input),result=evaluate(input),row=result.items[0];
 assert(row.modelStop>0);assert.equal(row.entryApproved,false);assert.equal(row.entrySuitable,false);
 assert.match(row.entryWarning,/Kein Einstieg/);assert.equal(result.conditionalAvailable,1);
 for(const scenario of row.automaticScenarios){
  assert(scenario.available);assert.equal(scenario.entryApproved,false);assert.equal(scenario.copyAllowed,false);
  assert.equal(scenario.entrySuitable,false);assert.match(scenario.entryWarning,/Kein Einstieg/);
 }
 assert.equal(JSON.stringify(input),original);
 input.plans[direction].stop=direction==='LONG'?3901:4499;
 assert.equal(evaluate(input).conditionalAvailable,0);
}
console.log('Non-entry research comparisons retain real stops while preserving KO protection and all approval gates');

// Saved capital/risk must not be reported missing when only fee evidence is absent.
const feeOnly=fixture();feeOnly.config.feesCHF=null;
const feeOnlyBefore=JSON.stringify(feeOnly),feeOnlyRow=evaluate(feeOnly).items[0];
assert.equal(feeOnlyRow.available,false);
assert.equal(feeOnlyRow.reason,feeOnlyRow.feeAssessment.reason);
assert(feeOnlyRow.automaticScenarios.every(s=>s.available));
assert(!feeOnlyRow.reasons.some(r=>/Kapital|Verlustrisiko/.test(r)));
assert.equal(JSON.stringify(feeOnly),feeOnlyBefore);
const noBudget=fixture();noBudget.config.budgetCHF=null;
assert.match(evaluate(noBudget).items[0].reason,/Maximalen Einsatz/);
const noRisk=fixture();noRisk.config.riskCHF=null;
assert.match(evaluate(noRisk).items[0].reason,/Maximalen Verlust/);
const koBlocked=fixture();koBlocked.plans.LONG.stop=3901;
const koRow=evaluate(koBlocked).items[0];
assert.equal(koRow.available,false);assert.match(koRow.reason,/KO-Schutzbereich/);
assert.equal(koRow.modelStop,null);assert.equal(koRow.copyAllowed,false);
assert(koRow.automaticScenarios.every(s=>!s.available));
console.log('Exact model/fee/config blockers: saved CHF inputs retained, KO guard intact, conditional scenarios unchanged');

// A terminated product is not an instruction to keep retrying missing prices/FX.
{
 const input=fixture();input.report.items[0].state='terminated';
 input.report.items[0].handsetObservation={code:'NO_QUOTES',fields:{Geld:'0,001'}};
 input.config=null;input.spots={};input.plans={};
 const before=JSON.stringify(input),out=evaluate(input),row=out.items[0];
 assert.equal(row.available,false);assert.equal(out.available,0);
 assert.deepEqual(Array.from(row.reasons),['Produkt vom Emittenten als beendet gemeldet']);
 assert.equal(row.quantity,null);assert.equal(row.modelStop,null);
 assert.equal(row.entryApproved,false);assert.equal(row.copyAllowed,false);
 assert.equal(row.automaticScenarios.length,0);assert.equal(JSON.stringify(input),before);
}
console.log('Terminated issuer state remains explicit without misleading missing-plan retries');

{
 const input=fixture();delete input.quotes[isin].productModel;
 input.quotes[isin].handsetModelCheck={reason:'CHF-Mini-Future: Modellpfad fehlt',code:'CHF_MINI_MODEL_UNSUPPORTED'};
 const row=evaluate(input).items[0];
 assert.equal(row.available,false);
 assert(row.reasons.includes('CHF-Mini-Future: Modellpfad fehlt'));
 assert.equal(row.entryApproved,false);
}
