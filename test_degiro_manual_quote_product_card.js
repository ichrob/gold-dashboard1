'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('degiro_assistant.js','utf8');
function part(start,end) {
 const a=source.indexOf(start),b=source.indexOf(end,a);
 assert(a>=0&&b>a,'helper is part of production Gold UI');
 return source.slice(a,b);
}
const ctx={Date,Number,Math,
 validIsin:x=>x==='DE000PJ8APE4',
 selectionTimeWindow:x=>Number.isFinite(Date.parse(x))?{start:Date.parse(x)}:null,
 esc:x=>String(x).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))};
vm.createContext(ctx);
vm.runInContext(part('function degiroScreenQuoteState(','function degiroBrokerQuotePanelState(')+
 part('function degiroManualQuoteSummary(','function goldProductCompactView('),ctx);
const now=Date.parse('2026-10-23T17:19:45Z');
const q={isin:'DE000PJ8APE4',source:'DEGIRO-Produktdetail',brokerDisplayConfirmed:true,
 isExecutableQuote:false,orderWindowVerified:false,orderSubmitted:false,executionGuaranteed:false,
 venue:'BNP OTC',currency:'EUR',bid:12.34,ask:12.35,
 sourceTime:'2026-10-23T17:19:00Z',timeBasis:'Kursdaten-Anzeige, keine eigene Geld-/Briefzeit'};
const p={isin:'DE000PJ8APE4',snapshot:{degiroDisplayedQuote:q}};
assert.equal(ctx.degiroScreenQuoteState(q,p.isin,now).state,'display-recent');
let html=ctx.degiroManualQuoteSummary(p,now);
assert.match(html,/data-degiro-manual-quote="display-recent"/);
assert.match(html,/Geld 12\.34 \/ Brief 12\.35 EUR/);
assert.match(html,/keine ausführbare Preisgarantie/);
assert.doesNotMatch(html,/Ausführung bestätigt|Handelsfreigabe erteilt/);
html=ctx.degiroManualQuoteSummary(p,now+300000);
assert.match(html,/data-degiro-manual-quote="historical"/);
assert.match(html,/nicht aktuell/);
assert.match(ctx.degiroManualQuoteSummary({isin:'DE000PJ8APE4'},now),/data-degiro-manual-quote="missing"/);
assert.match(ctx.degiroManualQuoteSummary({isin:'DE000PJ8APE4',snapshot:{degiroDisplayedQuote:{...q,isin:'DE000FG8NHQ3'}}},now),/data-degiro-manual-quote="missing"/);
assert.match(ctx.degiroManualQuoteSummary({isin:'DE000PJ8APE4',snapshot:{degiroDisplayedQuote:{...q,executionGuaranteed:true}}},now),/data-degiro-manual-quote="missing"/);
assert.match(ctx.degiroManualQuoteSummary({isin:'DE000PJ8APE4',snapshot:{degiroDisplayedQuote:{...q,venue:'<script>bad</script>'}}},now),/&lt;script&gt;bad&lt;\/script&gt;/);
const compact=part('function goldProductCompactView(','function goldProductOverview(');
assert.match(compact,/degiroManualQuoteSummary\(p,now\)/);
console.log('Manual DEGIRO display-only quotes are visible, time-bounded, ISIN-bound and never execution-authorized.');
