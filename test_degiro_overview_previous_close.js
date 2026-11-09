'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const window={};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const api=window.BobDegiro,isin='DE000FA9V5S0';
const original=[
 'Übersicht',
 'Zuletzt € 20,80 09/11/2026 09:52',
 'Geld € 20,80 Brief € 20,81',
 'Geld Vol. 25K Brief Vol. 25K',
 'Eröffnung € 21,94 Schluss € 18,47',
 'Hoch € 22,29',
 'Tief € 19,97',
 '+/- € +2,33 (+12,62%)',
 'Symbol | ISIN',
 isin,
 'Börse',
 'Societe Generale OTC',
 'Floating Aktien —'
].join('\n');
const now=Date.parse('2026-11-09T09:53:15+01:00');
const result=api.parseDegiroDisplayedQuote(original,isin);
assert(result,'DEGIRO overview must be recognized without Kursdaten tab');
assert.equal(result.bid,20.8);
assert.equal(result.ask,20.81);
assert.equal(result.lastPrice,20.8);
assert.equal(result.previousClose,18.47);
assert.equal(result.currency,'EUR');
assert.equal(result.venue,'Societe Generale OTC');
assert.equal(result.sourceTime,'09/11/2026 09:52');
assert(Math.abs(result.displayedDayChangePct-12.62)<0.01,result.displayedDayChangePct);
assert.equal(result.isExecutableQuote,false);
assert.equal(result.orderSubmitted,false);
assert.equal(result.executionGuaranteed,false);
assert.match(result.timeBasis,/keine eigene Geld-/);
assert.equal(api.degiroScreenQuoteState(result,isin,now).state,'display-recent');
let displayed=api.productDailyChangeView({isin,quote:{isin},snapshot:{degiroDisplayedQuote:result}},now);
assert.match(displayed,/\+12,62 %/,displayed);
assert.match(displayed,/DEGIRO-Bildstand/,displayed);
assert.match(displayed,/keine Live-Kurszeit/,displayed);
assert.match(displayed,/18,47/,displayed);
assert.doesNotMatch(displayed,/Aktueller Geldkurs gegenüber Vortagesschluss/);
displayed=api.productDailyChangeView({isin,quote:{isin},snapshot:{degiroDisplayedQuote:result}},
 Date.parse('2026-11-09T12:00:00+01:00'));
assert.match(displayed,/DEGIRO-Bildstand/,displayed);
displayed=api.productDailyChangeView({isin,quote:{isin},snapshot:{degiroDisplayedQuote:result}},
 Date.parse('2026-11-10T09:55:00+01:00'));
assert.match(displayed,/Tagesvergleich nicht verfügbar/,displayed);
assert.doesNotMatch(displayed,/\+12,62 %/,displayed);

const exact=api.parseDegiroDisplayedQuote(original.replace('Societe Generale OTC','Société Générale OTC'),isin);
assert(exact,'Accented trading venue must be preserved');
const never=[
 original.replace(isin,'DE000FB0QXR3'),
 original.replace('Börse\nSociete Generale OTC','Börse\n—'),
 original.replace('Geld € 20,80 Brief € 20,81','Geld € 20,82 Brief € 20,81'),
 original.replace('Schluss € 18,47','Schluss € 0,00'),
 original.replace('09/11/2026 09:52','09/11/2026 09:52 10/11/2026 09:52'),
 original.replace('09/11/2026 09:52','09/11/2026 09:52\nGeld € 99,99'),
 original.replace('€ 20,80 Brief','€ 20,80\nGeld € 20,80 Brief'),
 original.replace('Symbol | ISIN', 'Label'),
 original.replace('Übersicht','Abrechnung')
];
for(const bad of never)assert.equal(api.parseDegiroDisplayedQuote(bad,isin),null,bad);
assert.equal(api.parseDegiroDisplayedQuote(original+'\nDE000FB0QXR3',isin),null);
assert.equal(api.productDailyChangeView({isin,quote:{isin},snapshot:{degiroDisplayedQuote:{...result,isin:'DE000FB0QXR3'}}},now)
 .includes('DEGIRO-Bildstand'),false);
const authentic=api.productDailyChangeView({isin,quote:{isin,dailyChange:{
 isin,basis:'bid-vs-previous-close',bid:21.0,previousClose:18.47,
 percent:(21/18.47-1)*100,at:'2026-11-09T09:53:00+01:00',
 referenceAt:'2026-11-06T21:59:00+01:00',currency:'EUR',source:'Swissquote'}},
 snapshot:{degiroDisplayedQuote:result}},now);
assert.match(authentic,/Swissquote/,authentic);
assert.doesNotMatch(authentic,/DEGIRO-Bildstand/,authentic);
console.log('DEGIRO Übersicht display-only observed bid, ask, last, previous close, daily % and strict dated/ISIN/source tests passed.');
