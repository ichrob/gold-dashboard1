const fs=require('fs'),vm=require('vm'),assert=require('assert');
const now=Date.parse('2026-10-16T17:20:00Z'),isin='DE000FG14AV8';
class Clock extends Date {constructor(...args){super(...(args.length?args:[now]));} static now(){return now;}}
const window={};
const source=fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={degiroVenueInferred,setTestList:a=>{listArchive=a;},');
vm.runInNewContext(source,{window,Date:Clock});
const bob=window.BobDegiro;
const archive={storedAt:'2026-10-16T06:04:57Z',files:[{name:'list.jpg'}],items:[{isin}]};
const at='2026-10-16T17:19:50Z';
function sample(){return {isin,index:0,productDirection:'LONG',isinConfirmed:true,quote:{
 isin,productVerified:true,found:false,eligible:false,fresh:false,importActive:true,
 source:'Société Générale · Direktimport',checkedAt:at,
 metadata:{status:1,direction:'LONG',underlying:'XAU/USD',underlyingType:'SPOT',currency:'CHF',issuerExchangeCode:'CBSW'},
 nativeChartEvidence:{bid:8.17,ask:8.18,currency:'CHF',pointAt:at},
 issuerLeverageReference:{value:40.9424,source:'SG · AllProperties.Gearing',dated:false,eligible:false,sourceAt:null,sharedContextAt:at},
 sharedTimeContext:{kind:'issuer-collection',isin,at,fields:['Geld','Brief','Referenzhebel']},
 sharedValueObservations:{Referenzhebel:{isin,contextAt:at,value:40.9424}}
}};}
const p=sample(),proof=bob.degiroVenueInferred(p,archive,now);
assert.equal(proof.venue,'Société Générale OTC');
assert.equal(proof.brokerDisplayConfirmed,false);assert.equal(proof.isExecutableQuote,false);
bob.setTestList(archive);
const before=JSON.stringify(p),html=bob.compactProductCard(p);
assert(html.includes('data-degiro-venue-inferred'));
assert(html.includes('Société Générale OTC – aus Quellen abgeleitet'));
assert(html.includes('https://www.degiro.ch/fr/produits-and-places-boursieres'));
assert(!html.includes('DEGIRO-Handelsplatznachweis offen'));
assert(!html.includes('data-swiss-dots-warning'));
assert(!html.includes('Welcher DEGIRO-Handelsplatz'));
assert(!html.includes('DEGIRO-Handelsplatz belegt'));
assert(!html.includes('data-selection-approved'));
assert.equal(bob.currentQuote(p,now),false);assert.equal(bob.finalProductStatus(p,now).complete,false);
assert.equal(JSON.stringify(p),before,'inference must not mutate evidence');
for(const change of [
 p=>p.quote.isin='DE000FG8NHQ3',p=>p.quote.productVerified=false,
 p=>p.quote.source='BNP',p=>p.quote.metadata.currency='EUR',
 p=>p.quote.metadata.issuerExchangeCode='CBDE',p=>p.quote.metadata.direction='SHORT',
 p=>p.quote.metadata.status=2,p=>p.quote.metadata.tradingHalted=true,
 p=>p.quote.sourceFailure=true,p=>p.quote.checkedAt='2026-10-14T17:00:00Z',
 p=>p.snapshot={degiroDisplayedQuote:{isin,currency:'CHF',venue:'Other exchange'}},
 p=>p.snapshot={degiroDisplayedQuote:{isin:'DE000FG8NHQ3',currency:'CHF',venue:'Societe Generale OTC'}}
]){const bad=sample();change(bad);assert.equal(bob.degiroVenueInferred(bad,archive,now),null);}
for(const a of [{...archive,items:[]},{...archive,files:[]},{...archive,storedAt:'2026-10-15T06:00:00Z'},{...archive,storedAt:'2026-10-17T06:00:00Z'}])assert.equal(bob.degiroVenueInferred(p,a,now),null);
assert.equal(bob.degiroVenueInferred(p,archive,Date.parse('2026-10-16T20:00:00Z')),null,'Zurich 22h list cutoff');
const later=Date.parse('2026-11-17T12:00:00Z'),future=sample();future.quote.checkedAt=new Date(later).toISOString();
assert.equal(bob.degiroVenueInferred(future,{...archive,storedAt:new Date(later).toISOString()},later),null,'policy review expires');
const direct=sample();direct.snapshot={degiroDisplayedQuote:{isin,currency:'CHF',venue:'Societe Generale OTC',brokerDisplayConfirmed:true,isExecutableQuote:false,sourceTime:'16/10/2026 19:15',bid:8.17,ask:8.18}};
assert.equal(bob.degiroVenueInferred(direct,archive,now),null);
assert(bob.compactProductCard(direct).includes('DEGIRO-Handelsplatz belegt'));
console.log('DEGIRO source inference: provenance, conflicts, expiry, UI and execution gates passed');
