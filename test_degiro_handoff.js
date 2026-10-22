const assert=require('node:assert/strict');
const a=require('./degiro_handoff.js');
const input={budget:'100',currency:'EUR',isin:'US0378331005',side:'Kauf',qty:'2',price:'20,50',fees:'1'};
let s=a.reserve(null,input,'2026-10-17');assert.equal(s.orders[0].cost,4200);
s=a.reserve(s,input,'2026-10-17');assert.equal(s.orders.length,2);
assert.throws(()=>a.reserve(s,input,'2026-10-17'),/überschreiten/);
assert.throws(()=>a.reserve(s,{...input,currency:'CHF'},'2026-10-17'),/Währung/);
assert.throws(()=>a.reserve(s,{...input,budget:'10',side:'Verkauf'},'2026-10-17'),/überschreiten/);
const sold=a.reserve(s,{...input,side:'Verkauf'},'2026-10-17');assert.throws(()=>a.reserve(sold,input,'2026-10-17'),/überschreiten/);
assert.equal(a.reserve(s,input,'2026-10-18').orders.length,1);
for(const bad of ['-1','Infinity','1e3','1.001',''])assert.throws(()=>a.cents(bad));
assert.throws(()=>a.isin('US0378331006'));
assert.throws(()=>a.reserve(null,{...input,qty:'1.5'}));
assert.equal(a.day(new Date('2026-10-17T22:30:00Z')),'2026-10-18');
assert.match(a.summary(s.orders[0],'EUR'),/nicht übermittelt/);
const fs=require('node:fs');assert.match(fs.readFileSync('Bob.html','utf8'),/degiro2:'DEGIRO-Handy-Assistent'/);
console.log('DEGIRO 2: budget, rollover, validation and manual handoff checks passed');

assert.equal(a.maxQuantity(s,input,'2026-10-17'),0);
assert.equal(a.maxQuantity(null,input,'2026-10-17'),4);
assert.equal(a.maxQuantity(s,input,'2026-10-18'),4);

const risk=a.reserve(null,{...input,stop:'19',target:'25'},'2026-10-22').orders[0];
assert.equal(risk.stop,1900);assert.equal(risk.target,2500);
assert.match(a.summary(risk,'EUR'),/Rechnerischer Verlust bis Stopp/);
assert.throws(()=>a.reserve(null,{...input,stop:'22'},'2026-10-22'),/Stopp/);
assert.throws(()=>a.reserve(null,{...input,target:'20'},'2026-10-22'),/Ziel/);
assert.throws(()=>a.reserve(null,{...input,side:'Verkauf',stop:'19'},'2026-10-22'),/Verkaufsentwurf/);
const sale=a.reserve(null,{...input,side:'Verkauf'},'2026-10-22').orders[0];
assert.match(a.summary(sale,'EUR'),/Geschätzter Nettoerlös nach Gebühren: 40,00 EUR/);
assert.throws(()=>a.reserve(null,{...input,side:'Verkauf',price:'0,01',fees:'1'},'2026-10-22'),/Verkaufsgebühren/);

const now=Date.parse('2026-10-22T07:00:00Z');
const position={isin:'DE000FG14AV8',providerIsin:'DE000FG14AV8',currency:'CHF',units:'9',name:'Gold LONG',cashEquivalent:false};
const account={positions:[position],freshnessMode:'realtime',positionsSourceAt:'2026-10-22T06:55:00Z'};
const broker={code:'READ_OK',readOnly:true,fresh:true,snapshot:{accounts:[account]}};
let candidates=a.snapPositions(broker,now);
assert.equal(candidates.length,1);assert.equal(candidates[0].quantity,9);
assert.equal(candidates[0].current,true);assert.equal(candidates[0].currency,'CHF');
assert.equal(a.snapPositions({...broker,readOnly:false},now).length,0);
assert.equal(a.snapPositions({...broker,code:'PROVIDER_UNAVAILABLE'},now).length,0);
assert.equal(a.snapPositions({...broker,fresh:false},now)[0].current,false);
assert.equal(a.snapPositions({...broker,snapshot:{accounts:[{...account,positionsSourceAt:'2026-10-21T06:55:00Z'}]}},now)[0].current,false);
assert.equal(a.snapPositions({...broker,snapshot:{accounts:[{...account,freshnessMode:'delayed-or-unknown'}]}},now)[0].current,false);
assert.equal(a.snapPositions({...broker,snapshot:{accounts:[{...account,positions:[{...position,providerIsin:null}]}]}},now)[0].current,false);
assert.equal(a.snapPositions({...broker,snapshot:{accounts:[{...account,positions:[{...position,csvLinkConflict:true}]}]}},now).length,0);
assert.equal(a.snapPositions({...broker,snapshot:{accounts:[{...account,positions:[{...position,units:'9.5'}]}]}},now).length,0);
assert.equal(a.snapPositions({...broker,snapshot:{accounts:[{...account,positions:[{...position,isin:'DE000FG14AV9'}]}]}},now).length,0);
console.log('Read-only SnapTrade sale drafts, aged holdings, safe quantity, buy plan levels and fees passed');



// Automatic proposals: only dated, matched issuer observations + Bob's existing
// KO-aware spot-turbo scenario. Nothing is sent to a broker.
const quoteAt='2026-10-22T07:00:00Z',quoteTime=Date.parse(quoteAt)+20000;
const quote={
 isin:'DE000FG14AV8',found:true,productVerified:true,
 metadata:{currency:'CHF',direction:'LONG',status:1,underlyingType:'SPOT'},
 currency:'CHF',bid:9.85,ask:10.005,bidAt:quoteAt,askAt:quoteAt,
 source:'Zeitgleicher Emittent',priceKind:'market-observation',
 productModel:{isin:'DE000FG14AV8',verifiedSimpleTurbo:true,underlying:'XAU/USD'}
};
const identity={
 isin:'DE000FG14AV8',direction:'LONG',quote,
 reference:{isin:'DE000FG14AV8',currency:'CHF',source:'Emittent',bid:9.85,
 referenceAt:quoteAt,goldReference:4300,fxReference:.92,fxScenario:.92,
 strike:4200,ko:4000,ratio:.1}
};
const purchase={isin:identity.isin,side:'Kauf',budget:'1000',fees:'1',currency:'CHF',maxLoss:'50',minRR:'2'};
const gold={
 available:true,at:quoteAt,source:'XAU/USD Spot',gold:4300,atr:20,
 stopModel:()=>({stop:4270}),targetModel:()=>({target:4400}),
 exitModel:()=>({available:true,reasons:[],rows:[
   {label:'Am Stop',available:true,price:9},
   {label:'Am Ziel',available:true,price:13}
 ]})
};
let proposed=a.calculateProposal(identity,purchase,gold,null,quoteTime);
assert.equal(proposed.ok,true);
assert.equal(proposed.price,'10,01'); // round buying quote conservatively up
assert.equal(proposed.qty,48);
assert.equal(proposed.stop,'9,00');assert.equal(proposed.target,'13,00');
assert.equal(proposed.loss,'49,48'); // below stated loss budget after rounding
assert.equal(proposed.tradeable,false);assert.equal(proposed.automaticOrder,false);
assert.equal(a.calculateProposal(identity,{...purchase,side:'Verkauf'},null,null,quoteTime).price,'9,85');
assert.equal(a.calculateProposal(identity,{...purchase,side:'Verkauf'},null,null,quoteTime).qty,null);
assert.equal(a.calculateProposal(identity,purchase,{...gold,available:false},null,quoteTime).ok,false);
assert.equal(a.calculateProposal(identity,purchase,{...gold,available:false},null,quoteTime).price,'10,01');
for(const q of [
 {...quote,estimated:true},{...quote,paperSelectionOnly:true},{...quote,priceKind:'calculated'},{...quote,priceKind:'issuer-chart'},
 {...quote,found:false},{...quote,productVerified:false},{...quote,marketOpen:false},
 {...quote,metadata:{...quote.metadata,status:2}},
 {...quote,metadata:{...quote.metadata,underlyingType:'FUTURE'}},
 {...quote,currency:'EUR'}, {...quote,ask:9}, {...quote,bidAt:null},
 {...quote,askAt:'2026-10-22T06:57:00Z'}
 ]){
 assert.equal(a.calculateProposal({...identity,quote:q},purchase,gold,null,quoteTime).ok,false);
}
assert.equal(a.calculateProposal(identity,purchase,gold,null,quoteTime+91000).ok,false);
assert.equal(a.calculateProposal(identity,purchase,{...gold,at:'2026-10-22T06:00:00Z'},null,quoteTime).ok,false);
assert.equal(a.calculateProposal({...identity,reference:{...identity.reference,referenceAt:'2026-10-22T06:30:00Z'}},purchase,gold,null,quoteTime).ok,false);
assert.equal(a.calculateProposal({...identity,quote:{...quote,productModel:{...quote.productModel,verifiedSimpleTurbo:false}}},purchase,gold,null,quoteTime).ok,false);
assert.equal(a.calculateProposal(identity,{...purchase,minRR:'5'},gold,null,quoteTime).ok,false);
assert.equal(a.calculateProposal(identity,{...purchase,maxLoss:'1'},gold,null,quoteTime).ok,false);
assert.equal(a.calculateProposal(identity,purchase,{...gold,exitModel:()=>({available:true,reasons:[],rows:[
 {label:'Am Stop',available:false},{label:'Am Ziel',available:true,price:13}]})},null,quoteTime).ok,false);
const planned={day:'2026-10-22',currency:'CHF',budget:100000,orders:[{side:'Kauf',cost:95000}]};
assert.equal(a.calculateProposal(identity,purchase,gold,planned,quoteTime).qty,4);
const saved=a.reserve(null,{...purchase,price:proposed.price,qty:String(proposed.qty),stop:proposed.stop,target:proposed.target},'2026-10-22');
assert.equal(saved.orders.length,1);
const app=fs.readFileSync('degiro_handoff.js','utf8');
assert.match(app,/dg2-propose/);assert.match(app,/BobExitEstimate\?\.planInput/);
assert.match(app,/GET|fetch\('\/api\/snaptrade\/status'/);
assert.ok(!/\/api\/snaptrade\/orders|\/api\/degiro\/order|accessibilityService\.click/i.test(app));
console.log('Automatic proposals: original-time validity, CHF, bid/ask, active issuer, KO model, budget, fees and no brokerage write tested');
