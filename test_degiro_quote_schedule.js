/* No network, account access or simulated trades: morning quote schedule only. */
'use strict';
const assert=require('node:assert/strict');
const m=require('./degiro_all_products');
function at(timestamp){return Date.parse(timestamp);}
const cases=[
 ['2026-10-20T03:15:00Z','night'],       // Zurich 05:15 CEST
 ['2026-10-20T05:29:59Z','night'],       // Zurich 07:29
 ['2026-10-20T05:30:00Z','preparation'], // Zurich 07:30
 ['2026-10-20T05:59:59Z','preparation'],
 ['2026-10-20T06:00:00Z','trading'],     // Zurich 08:00
 ['2026-10-20T19:59:59Z','trading'],     // Zurich 21:59
 ['2026-10-20T20:00:00Z','night'],       // Zurich 22:00
 ['2026-10-25T04:00:00Z','weekend'],     // October DST change weekend
 ['2026-10-26T06:30:00Z','preparation'], // After DST, 07:30 CET
 ['2026-10-26T07:00:00Z','trading']
];
for(const [date,phase] of cases)assert.equal(m.zurichQuotePhase(at(date)),phase,date);
assert(m.quotePhaseMessage('night','stale').includes('07:30'));
assert(m.quotePhaseMessage('preparation','stale').includes('07:30'));
assert(m.quotePhaseMessage('trading','stale').includes('überfällig')||
       m.quotePhaseMessage('trading','stale').includes('aktueller Produktprüfbericht fehlt'));
assert(!m.quotePhaseMessage('night','stale').includes('Kurs aktuell'));
assert(m.quotePhaseMessage('weekend','stale').includes('Wochenende'));
const oldAudit={status:'stale',lastCheckedAt:'2026-10-19T19:59:48+00:00',
 items:[{isin:'DE000FG7K366',direction:'LONG',sourceObservations:[{
  bid:6.09,ask:6.10,source:'SG Chart',currency:'EUR',
  bidAt:'2026-10-19T19:58:44+00:00',askAt:'2026-10-19T19:58:44+00:00',
  researchOnly:true,degiroExecutable:false}]}]};
const out=m.combine(null,[],oldAudit,[],at('2026-10-20T03:15:00Z'));
assert.equal(out.length,1);
assert.equal(out[0].quote.fresh,false,'HTTP report read must not renew original price time');
assert.equal(out[0].quote.degiroExecutable,false);
assert.equal(out[0].tradeApproved,false);
assert.equal(m.summary(out,oldAudit).currentObserved,0);
console.log('Issuer quote 07:30 preparation, 08:00 trading, DST, and source-time safety passed');
