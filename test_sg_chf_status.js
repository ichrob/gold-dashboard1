const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const bob=window.BobDegiro,now=Date.now();
const isin='DE000FG8NHQ3';
const at=new Date(now-35000).toISOString().replace('Z','+00:00');
function sample(){
 return {isin,index:0,productDirection:'SHORT',isinConfirmed:true,
  quote:{isin,productVerified:true,found:false,eligible:false,fresh:false,
   source:'Société Générale · Direktimport',importActive:true,checkedAt:new Date(now).toISOString(),
   metadata:{status:1,direction:'SHORT',underlying:'XAU/USD',underlyingType:'SPOT',
     currency:'CHF',issuerExchangeCode:'CBSW'},
   nativeChartEvidence:{bid:18.46,ask:18.48,currency:'CHF',pointAt:at},
   issuerLeverageReference:{value:16.0508,source:'SG · AllProperties.Gearing',
     dated:false,eligible:false,sourceAt:null,sharedContextAt:at},
   sharedTimeContext:{kind:'issuer-collection',isin,at,fields:['Geld','Brief','Referenzhebel']},
   sharedValueObservations:{'Referenzhebel':{isin,contextAt:at,value:16.0508}}}};
}
const card=bob.compactProductCard(sample());
assert(card.includes('data-sg-chf-analysis-only'),card);
assert(card.includes('Kurs/Hebel · nur Analyse'),card);
assert(card.includes('DEGIRO-Handelsplatznachweis offen'),card);
assert(card.includes('18.46')&&card.includes('18.48'),card);
assert(card.includes('data-selection-blocked'),card);
assert(!card.includes('data-selection-approved'),card);
assert.strictEqual(bob.finalProductStatus(sample(),now).complete,false);
assert.strictEqual(bob.currentQuote(sample(),now),false);
assert.strictEqual(bob.productDataStatus(sample(),now).complete,false);
const invalid=[
 {name:'quote unavailable',change:p=>{p.quote.sourceFailure=true;}},
 {name:'issuer clock lost',change:p=>{p.quote.sharedTimeContext.at=new Date(now-45000).toISOString();}},
 {name:'other ISIN',change:p=>{p.quote.sharedValueObservations.Referenzhebel.isin='DE000FG14AV8';}},
 {name:'wrong currency',change:p=>{p.quote.metadata.currency='EUR';}},
 {name:'non SG CHF venue',change:p=>{p.quote.metadata.issuerExchangeCode='CBDE';}},
 {name:'knocked-out',change:p=>{p.quote.metadata.status=2;}},
 {name:'direction mismatch',change:p=>{p.quote.metadata.direction='LONG';}},
 {name:'bad ask',change:p=>{p.quote.nativeChartEvidence.ask=17;}},
 {name:'unverified quote',change:p=>{p.quote.productVerified=false;}},
 {name:'no leverage',change:p=>{p.quote.issuerLeverageReference.value=null;}},
 {name:'future underlying',change:p=>{p.quote.metadata.underlyingType='FUTURE';}},
 {name:'stale source',change:p=>{p.quote.nativeChartEvidence.pointAt=new Date(now-360000).toISOString();}},
];
for(const item of invalid){
 const p=sample();item.change(p);
 const html=bob.compactProductCard(p);
 assert(!html.includes('data-sg-chf-analysis-only'),item.name);
 assert.equal(bob.currentQuote(p,now),false,item.name);
}
console.log('SG Swiss DOTS CHF display-only timestamp and broker gate regression passed');

// Broker proof cannot be recovered by a quote retry alone.
const venueCard=bob.compactProductCard(sample(),['BNP-Kursabruf: Quellenantwort veraltet']);
assert(venueCard.includes('Konkret offen: Welcher DEGIRO-Handelsplatz gehört zu dieser ISIN und Handelswährung?'));
assert(!venueCard.includes('derzeit keine neuen Bilder erforderlich'));
assert(!venueCard.includes('Du musst jetzt nichts tun.'));
const observed=sample();
observed.snapshot={isin,degiroDisplayedQuote:{isin,brokerDisplayConfirmed:true,isExecutableQuote:false,
 currency:'CHF',venue:'Societe Generale OTC',sourceTime:'16/10/2026 18:51',bid:16.95,ask:16.97}};
const observedCard=bob.compactProductCard(observed);
assert(observedCard.includes('DEGIRO-Handelsplatz belegt'));
assert(!observedCard.includes('DEGIRO-Handelsplatznachweis offen'));
assert(!observedCard.includes('data-swiss-dots-warning'));
assert.equal(bob.currentQuote(observed,now),false);
observed.snapshot.degiroDisplayedQuote.isin='DE000FG34XV8';
assert(bob.compactProductCard(observed).includes('DEGIRO-Handelsplatznachweis offen'));
