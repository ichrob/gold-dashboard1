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
// venueMissing verified by original cropped-footer fixture. The screenshot is
// a local display observation only; it cannot fill the issuer quote or venue.
const sampleTime=Date.parse('2026-11-13T09:02:35Z');
const chfId='DE000FE6B3E4',eurId='DE000FA9UFD4';
const chfText=[
 'Übersicht','Kursdaten','Zuletzt CHF 104,57 13/11/2026 10:02',
 'Geld CHF 104,57 Brief CHF 104,58','Geld Vol. 25K Brief Vol. 25K',
 'Schluss CHF 102,51','Symbol | ISIN','156825575 | '+chfId
].join('\n');
const eurText=[
 'Übersicht','Kursdaten','Zuletzt € 5,90 13/11/2026 10:02',
 'Geld € 5,90 Brief € 5,91','Schluss € 3,74',
 'Symbol | ISIN',eurId
].join('\n');
for(const [label,text,expected,currency,bid,ask] of [
 ['CHF cropped venue',chfText,chfId,'CHF',104.57,104.58],
 ['EUR cropped venue',eurText,eurId,'EUR',5.90,5.91]
]){
 const parsed=b.parseDegiroDisplayedQuote(text,expected);
 assert(parsed,label+' must parse a visible pair without inventing venue');
 assert.equal(parsed.isin,expected);
 assert.equal(parsed.currency,currency);
 assert.equal(parsed.bid,bid);
 assert.equal(parsed.ask,ask);
 assert.equal(parsed.sourceTime,'13/11/2026 10:02');
 assert.equal(parsed.venue,null);
 assert.equal(parsed.venueMissing,true);
 assert.equal(parsed.brokerDisplayConfirmed,false);
 assert.equal(parsed.displayOnly,true);
 assert.equal(parsed.isExecutableQuote,false);
 const full=b.detailScreenshotData(text,expected);
 assert.equal(full.ok,true,label+' import');
 assert.equal(full.degiroDisplayedQuote?.venueMissing,true);
 assert.equal(full.degiroDisplayedQuote?.bid,bid);
 assert.equal(full.degiroDisplayedQuote?.ask,ask);
 for(const key of ['bid','ask'])assert.equal(full[key],null);
 assert.equal(full.price,'');
 assert.equal(full.combinedDraft?.hasQuote,false);
 for(const key of ['bid','ask','quoteAt'])assert.equal(full.combinedDraft?.fields?.[key],undefined);
 assert.equal(b.parseDegiroDisplayedQuote(text,expected,true),null,'venue-only proof must fail closed');
 const state=b.degiroScreenQuoteState(parsed,expected,sampleTime);
 assert.equal(state.state,'display-recent',label);
 assert.equal(state.venue,null);
 assert.equal(state.venueMissing,true);
 assert.equal(state.tradeApproved,false);
 assert.equal(state.executionConfirmed,false);
 assert.equal(state.brokerConnected,false);
 assert.equal(state.isExecutableQuote,false);
 assert.equal(b.degiroScreenQuoteState(parsed,expected,sampleTime+120000).state,'historical');
 assert.equal(b.degiroScreenQuoteState(parsed,expected,sampleTime-120000).state,'invalid-time');
 assert.equal(b.degiroScreenQuoteState({...parsed,brokerDisplayConfirmed:true},expected,sampleTime).state,'missing','no fake broker status');
 assert.equal(b.degiroScreenQuoteState({...parsed,isExecutableQuote:true},expected,sampleTime).state,'missing','no spoofed quote');
 assert.equal(b.degiroScreenQuoteState({...parsed,venue:'Societe Generale OTC'},expected,sampleTime).state,'missing','cannot fabricate venue');
}
assert.equal(b.parseDegiroDisplayedQuote(chfText,chfId==='DE000FA9UFD4'?chfId:eurId),null,'wrong ISIN rejected');
assert.equal(b.parseDegiroDisplayedQuote(chfText+'\n'+eurId,chfId),null,'conflicting ISIN rejected');
assert.equal(b.parseDegiroDisplayedQuote(chfText.replace('Brief CHF 104,58','Brief CHF 104,55'),chfId),null,'crossed pair rejected');
assert.equal(b.parseDegiroDisplayedQuote(chfText.replace('13/11/2026 10:02',''),chfId),null,'missing original display clock rejected');
const croppedReport=b.degiroBrokerQuotePanelState([
 {isin:chfId,direction:'LONG',slot:1,snapshot:{isin:chfId,degiroDisplayedQuote:b.parseDegiroDisplayedQuote(chfText,chfId)},listingConfirmed:true}
],sampleTime);
assert.equal(croppedReport.quotes,1);
assert.equal(croppedReport.items[0].status.venueMissing,true);

const source=fs.readFileSync('degiro_assistant.js','utf8');
assert(source.includes("const displayWithoutVenue=degiroDisplayedQuote?.venueMissing===true"));
assert(source.includes("const bid=displayWithoutVenue?null:"));
assert(source.includes("if(degiroDisplayedQuote&&!displayWithoutVenue&&!draft.paired)"));
assert(source.includes('id="dgBrokerQuotePanel"'));
assert(source.includes('data-dg-broker-quote-upload'));
assert(source.includes("document.getElementById('dgDetailShot'+index)"));
assert(source.includes('Keine bestätigte Ausführung und keine Handelsfreigabe.'));
assert(!source.includes('snaptrade.com/accounts/{accountId}/quotes'));
console.log('DEGIRO read-only screen observation: exact ISIN, time, quote classification, no broker API, no trading and correct upload shortcut.');
