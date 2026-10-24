'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const now=Date.parse('2026-10-19T15:06:45Z');
class Clock extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
const context={window:{},Date:Clock,Intl};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),context);
const b=context.window.BobDegiro,isin='DE000FG14AV8';
const sample={
 isin,source:'DEGIRO-Produktdetail',venue:'Societe Generale OTC',currency:'CHF',
 bid:6.87,ask:6.88,sourceTime:'19/10/2026 17:06',
 timeBasis:'Kursdaten-Anzeige; keine eigene Geld-/Briefzeit',
 brokerDisplayConfirmed:true,orderWindowVerified:false,orderSubmitted:false,
 executionGuaranteed:false,isExecutableQuote:false
};
let s=b.degiroScreenQuoteState(sample,isin,now);
assert.equal(s.state,'display-recent');
assert.equal(s.bid,6.87);assert.equal(s.ask,6.88);
for(const key of ['displayOnly','brokerConnected','executionConfirmed','isExecutableQuote','tradeApproved']){
 assert.equal(s[key],key==='displayOnly',key+' must fail closed');
}
s=b.degiroScreenQuoteState(sample,isin,now+600000);
assert.equal(s.state,'historical','a screenshot cannot be refreshed by UI polling');
assert.equal(s.sourceTime,sample.sourceTime);
assert.equal(b.degiroScreenQuoteState(sample,isin,now-600000).state,'invalid-time');
const provider={...sample,source:'comdirect · SG LiveTrading'};
for(const [label,bad] of [
 ['different ISIN',{...sample,isin:'DE000FG8NHQ3'}],
 ['issuer observation',provider],
 ['not reviewed',{...sample,brokerDisplayConfirmed:false}],
 ['execution spoof',{...sample,isExecutableQuote:true}],
 ['filled-order spoof',{...sample,orderSubmitted:true}],
 ['offer verified spoof',{...sample,orderWindowVerified:true}],
 ['executable guarantee spoof',{...sample,executionGuaranteed:true}],
 ['wrong currency',{...sample,currency:'USD'}],
 ['crossed bid ask',{...sample,bid:7.50}],
 ['missing time',{...sample,sourceTime:''}],
 ['invalid venue',{...sample,venue:''}]
])assert(!['display-recent','historical'].includes(b.degiroScreenQuoteState(bad,isin,now).state),label);
const input=[
 {isin,direction:'LONG',slot:1,snapshot:{isin,degiroDisplayedQuote:sample},listingConfirmed:true},
 {isin,direction:'LONG',slot:2,snapshot:null,listingConfirmed:true},
 {isin:'DE000FG8NHQ3',direction:'SHORT',slot:3,snapshot:null,listingConfirmed:true}
];
const report=b.degiroBrokerQuotePanelState(input,now);
assert.equal(report.total,2);assert.equal(report.quotes,1);assert.equal(report.recent,1);
assert.equal(report.items[0].status.state,'display-recent');
assert.equal(report.items[1].status.state,'missing');
const source=fs.readFileSync('degiro_assistant.js','utf8');
assert(source.includes('id="dgBrokerQuotePanel"'));
assert(source.includes('data-dg-broker-quote-upload'));
assert(source.includes("document.getElementById('dgDetailShot'+index)"));
assert(source.includes('Keine bestätigte Ausführung und keine Handelsfreigabe.'));
assert(!source.includes('snaptrade.com/accounts/{accountId}/quotes'));
console.log('DEGIRO read-only screen observation: exact ISIN, time, quote classification, no broker API, no trading and correct upload shortcut.');
