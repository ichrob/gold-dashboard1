const fs=require('fs'),vm=require('vm'),assert=require('assert');
let now=Date.parse('2026-10-16T17:20:00Z');
class Clock extends Date {constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
const window={};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={degiroVenueInferred,degiroVenueObserved,degiroTradingSession,expectedQuotePause,productProblemLabels,renderDegiroTradingSession,setTestList:a=>{listArchive=a;},'),{window,Date:Clock});
const b=window.BobDegiro,isin='DE000PJ9NB98',at='2026-10-16T17:19:50Z';
const archive={storedAt:'2026-10-16T06:00:00Z',items:[{isin}],files:[{name:'list.jpg'}]};b.setTestList(archive);
function sample(){return {isin,index:0,productDirection:'LONG',quote:{isin,productVerified:true,source:'BNP Paribas · Emittent OTC',sourceUrl:'https://derivate.bnpparibas.com/product-details/'+isin+'/',checkedAt:at,found:true,marketOpen:false,currency:'EUR',direction:'LONG',bid:12,ask:12.1,bidAt:at,askAt:at,leverage:20,leverageAt:at,metadata:{status:1,direction:'LONG',currency:'EUR',underlying:'XAU/USD',underlyingType:'SPOT'}}};}
const p=sample(),proof=b.degiroVenueInferred(p,archive,now);
assert.equal(proof.venue,'BNP Paribas OTC');assert.equal(proof.isExecutableQuote,false);
const card=b.compactProductCard(p);assert(card.includes('BNP Paribas OTC – aus Quellen abgeleitet'));assert(!card.includes('SG-Produktdaten'));
for(const mutate of [p=>p.quote.sourceUrl+='wrong',p=>p.quote.metadata.issuerExchangeCode='CBSW',p=>p.quote.metadata.currency='CHF',p=>p.quote.metadata.status=2,p=>p.quote.metadata.direction='SHORT',p=>p.quote.isin='DE000FG14AV8',p=>p.snapshot={degiroDisplayedQuote:{isin,currency:'EUR',venue:'Societe Generale OTC'}}]){const bad=sample();mutate(bad);assert.equal(b.degiroVenueInferred(bad,archive,now),null);assert.equal(b.degiroTradingSession(bad,now,archive),null);}
for(const [date,pause] of [['2026-10-19T05:59:59Z',true],['2026-10-19T06:00:00Z',false],['2026-10-16T19:59:59Z',false],['2026-10-16T20:00:00Z',true],['2026-10-17T10:00:00Z',true],['2026-10-18T10:00:00Z',true],['2026-10-19T06:00:00Z',false],['2026-10-26T06:59:59Z',true],['2026-10-26T07:00:00Z',false]]){
 const t=Date.parse(date),x=sample();x.quote.checkedAt=new Date(t-1000).toISOString();
 const a={...archive,storedAt:new Date(t-2000).toISOString()};
 const session=b.degiroTradingSession(x,t,a);assert.equal(session.scheduledPause,pause,date);assert.equal(session.marketOpenConfirmed,false);
}
now=Date.parse('2026-10-16T20:01:00Z');
assert(b.expectedQuotePause(p,now));assert(b.compactProductCard(p).includes('data-regular-trading-pause'));
assert(b.renderDegiroTradingSession(p).includes('Feiertage und Sonderunterbrechungen sind nicht bestätigt'));
assert.equal(b.currentQuote(p,now),false);assert.equal(b.finalProductStatus(p,now).complete,false);
const failure=sample();failure.quote.sourceFailure=true;assert(!b.expectedQuotePause(failure,now));
const missing=sample();delete missing.quote.askAt;assert(!b.expectedQuotePause(missing,now));
const unknown=sample();unknown.quote.productVerified=false;assert.equal(b.degiroTradingSession(unknown,now,archive),null);
// Suppress only an expected closure diagnostic; missing terms and failures stay.
const src=fs.readFileSync('degiro_assistant.js','utf8');
const c={knockoutStatus:()=>false,compactProductExclusion:()=>false,expectedQuotePause:()=>true,degiroVenueInferred:()=>proof,degiroVenueObserved:()=>false,finalProductStatus:()=>({complete:false,reasons:['BNP-Kursabruf: Markt geschlossen oder Produkt derzeit nicht handelbar','KO-Barriere fehlt','BNP-Kursabruf: Abruf fehlgeschlagen']}),productFieldStates:()=>({bid:{value:12},ask:{value:12.1},leverage:{value:20}}),n:Number};
vm.createContext(c);vm.runInContext(src.slice(src.indexOf('function productProblemLabels('),src.indexOf('function renderProductProblemSummary(')),c);
const labels=Array.from(c.productProblemLabels(p));assert(labels.includes('KO-Nachweis'));assert(labels.includes('Kursart / Ausführbarkeit'));assert(!labels.includes('DEGIRO-Handelsplatznachweis'));
console.log('BNP venue and Zurich trading sessions: boundaries, DST, conflicts and execution gates passed');
