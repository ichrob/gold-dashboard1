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
