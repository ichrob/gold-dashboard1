const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const window={};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const ui=window.BobDegiro;
const isin='DE000FG7K283';
const at='2026-11-09T09:05:00+01:00', prior='2026-11-06T21:59:00+01:00';
const now=Date.parse('2026-11-09T09:05:20+01:00');
const daily={isin,basis:'bid-vs-last-observed-prior-day',percent:10,bid:11,
  previousClose:10,at,referenceAt:prior,currency:'EUR',source:'SG · datierte Geldkursbeobachtung'};
const display=row=>ui.productDailyChangeView({isin,quote:{dailyChange:row}},now);
const valid=display(daily);
assert(valid.includes('10'),valid);
assert(valid.includes('kein offizieller Schlusskurs'),valid);
assert(valid.includes('SG'),valid);
assert(valid.includes('Vortag')===false,valid);
const official=display({...daily,basis:'bid-vs-previous-close',source:'Swissquote'});
assert(official.includes('Vortagesschluss'),official);
assert(!official.includes('kein offizieller Schlusskurs'),official);
const missing=display(null);
assert(missing.includes('Tagesvergleich nicht verfügbar'),missing);
assert(!missing.includes('10,00 %'),missing);
for(const row of [
  {...daily,isin:'DE000FB0KKS1'},
  {...daily,basis:'unknown'},
  {...daily,percent:9},
  {...daily,referenceAt:'2026-11-05T21:59:00+01:00'},
  {...daily,referenceAt:'2026-11-09T08:00:00+01:00'},
  {...daily,referenceAt:'2026-11-10T21:59:00+01:00'},
  {...daily,at:'2026-11-06T21:59:00+01:00'},
  {...daily,bid:0},
  {...daily,previousClose:0},
  {...daily,currency:'USD'},
]) {
  const text=display(row);
  assert(text.includes('Tagesvergleich nicht verfügbar'),text);
}
assert(display({...daily,percent:-5,bid:9.5}).includes('5'), 'Negative movement must render');
const portalUrl='https://www.comdirect.de/inf/zertifikate/'+isin;
const portal={isin,quote:{isin,metadata:{status:1},comdirectFieldsBackup:{
 isin,source:portalUrl,state:'active',inactive:false,checkedAt:'2026-11-09T09:04:00+01:00',
 observations:{leverage:{value:17.52,source:portalUrl},ko:{value:3860.4758,source:portalUrl},
 strike:{value:3860.4758,source:portalUrl}}}}};
const reference=ui.productPortalReferenceView(portal,now);
assert(reference.includes('17'),reference);
assert(reference.includes('3860'),reference);
assert(reference.includes('unbestätigt'),reference);
assert(reference.includes('kein eigener Kurs-/Hebelzeitpunkt'),reference);
for(const bad of [
 {...portal,isin:'DE000FA9V5S0'},
 {...portal,quote:{...portal.quote,metadata:{status:2}}},
 {...portal,quote:{...portal.quote,comdirectFieldsBackup:{...portal.quote.comdirectFieldsBackup,source:'https://example.test/quote'}}},
 {...portal,quote:{...portal.quote,comdirectFieldsBackup:{...portal.quote.comdirectFieldsBackup,checkedAt:'2026-10-01T09:04:00+02:00'}}},
])assert.equal(ui.productPortalReferenceView(bad,now),'');
console.log('Product previous-session percentage: source/ISIN/date/maths and stale reference safeguards passed');
