'use strict';
const assert=require('node:assert/strict'),{evaluate}=require('./handset_planning');
const now=Date.now(),at=new Date(now-10000).toISOString(),isin='DE000FG14AV8';
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
