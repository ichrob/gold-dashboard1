/* Broker listing proof survives unavailable issuer data; never execution. */
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const now=Date.parse('2026-10-20T17:00:00+02:00');
class Clock extends Date{constructor(...a){super(...(a.length?a:[now]));}static now(){return now;}}
const generation='2026-10-20T06:13:00Z',isin='US0378331005';
const window={};
let source=fs.readFileSync('degiro_assistant.js','utf8');
// Test the actual card renderer with a restored active screenshot generation.
source=source.replace('let listArchive=null,',`let listArchive={storedAt:'${generation}'},`);
vm.runInNewContext(source,{window,Date:Clock});
const b=window.BobDegiro;
const p={isin,name:'Test Gold',productDirection:'LONG',currency:'EUR',quote:null};
const e={isin,broker:'DEGIRO',venue:'BNP OTC',currency:'EUR',
 kind:'owner-reviewed-screenshot',listingConfirmed:true,executionConfirmed:false,
 timezone:'Europe/Zurich',timePrecision:'minute',imageReference:'Reviewed original list',
 listUploadedAt:generation,observedMinute:'2026-10-20T08:12',validUntil:'2026-10-20T22:00:00+02:00'};
const report={status:'ok',lastCheckedAt:new Date(now-30000).toISOString(),listUploadedAt:generation,items:[{isin,brokerVenueEvidence:e}]};
window.BobProductAuditReport=report;
assert.equal(b.serverVenueEvidence(p).venue,'BNP OTC');
assert(b.degiroVenueObserved(p));
const card=b.compactProductCard(p);
assert(card.includes('data-server-listing-proof'));
assert(card.includes('DEGIRO-Handelsplatz belegt'));
assert(card.includes('Aktueller Brokerkurs separat zu prüfen'));
assert(!card.includes('Kursart / DEGIRO-Handelsplatznachweis'));
assert(card.includes('data-selection-blocked'));
assert(!b.finalProductStatus(p,now).complete);
assert(!b.currentQuote(p,now));
for(const change of [{isin:'US5949181045'},{currency:'CHF'},{listingConfirmed:false},
 {executionConfirmed:true},{kind:'issuer-inference'},{venue:'unknown'},
 {listUploadedAt:'old'},{observedMinute:'2026-10-19T08:12'},
 {observedMinute:'2026-10-20T18:00'},{validUntil:'2026-10-21T22:00:00+02:00'}]){
 const bad={...report,items:[{isin,brokerVenueEvidence:{...e,...change}}]};
 assert.equal(b.serverVenueEvidence(p,bad,generation,now),null,JSON.stringify(change));
}
assert.equal(b.serverVenueEvidence(p,{...report,status:'stale'},generation,now),null);
assert.equal(b.serverVenueEvidence(p,report,'replacement',now),null);
assert.equal(b.serverVenueEvidence(p,report,generation,now+180001),null);
assert.equal(b.serverVenueEvidence(p,report,generation,Date.parse(e.validUntil)),null);
for(const [venue,currency] of [['Societe Generale OTC','EUR'],['Societe Generale OTC','CHF'],['BNP OTC','EUR'],['BNP Paribas OTC','EUR']]){
 const row={isin,snapshot:{degiroVenueEvidence:{isin,currency,venue,brokerDisplayConfirmed:true,isExecutableQuote:false,sourceTime:'20/10/2026 08:12'}}};
 window.BobProductAuditReport=null;
 assert(b.degiroVenueObserved(row),venue+' '+currency);
}
console.log('Original list proof shown independently of issuer quotes; wrong/stale generation and execution claims rejected');
