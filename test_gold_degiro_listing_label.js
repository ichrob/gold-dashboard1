'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('degiro_assistant.js','utf8');
const start=src.indexOf('function goldProductBrokerListStatus(');
const end=src.indexOf('function goldProductCompactView(',start);
assert(start>0&&end>start);
const now=Date.parse('2026-10-23T17:21:00Z');
const record={
 isin:'DE000PJ8APE4',venue:'BNP OTC',currency:'EUR',uploadedAt:'2026-10-23T17:19:01.239Z',currentDay:true};
const vars={listArchive:{items:[]},Date,Intl,observedDegiroListRow:()=>record,sharedVenueStatus:()=>null};
const status=vm.runInNewContext(src.slice(start,end)+'\ngoldProductBrokerListStatus',vars);
let result=status({isin:record.isin},now);
assert.equal(result.state,'confirmed');
assert(result.message.includes('In DEGIRO-Liste bestätigt'));
assert(result.message.includes('BNP OTC'));
assert(result.message.includes('EUR'));
assert(!/Ausführung bestätigt|Handelsfreigabe erteilt/.test(result.message));
vars.observedDegiroListRow=()=>({...record,currentDay:false});
result=status({isin:record.isin},Date.parse('2026-10-24T17:00:00Z'));
assert.equal(result.state,'historical','old list never becomes current execution evidence');
vars.observedDegiroListRow=()=>null;
vars.sharedVenueStatus=()=>({current:true,evidence:{
 isin:record.isin,venue:record.venue,currency:record.currency,
 listingConfirmed:true,executionConfirmed:false}});
result=status({isin:record.isin},now);
assert.equal(result.state,'confirmed','current server verified list may corroborate screenshot');
vars.sharedVenueStatus=()=>({current:true,evidence:{
 isin:record.isin,venue:record.venue,currency:record.currency,
 listingConfirmed:true,executionConfirmed:true}});
assert.equal(status({isin:record.isin},now).state,'unconfirmed','do not treat execution flag as a list-only record');
vars.sharedVenueStatus=()=>null;
assert.equal(status({isin:record.isin},now).state,'unconfirmed');
const compact=src.slice(src.indexOf('function goldProductCompactView('),src.indexOf('function compactProductCard('));
assert(compact.includes('data-degiro-list-proof'));
assert(compact.includes('Ausführbarer DEGIRO-Orderkurs und tatsächliche Ausführung nicht bestätigt'));
assert(compact.includes('data-degiro-list-count'));
const x=src.slice(src.indexOf('function goldProductOverview('),src.indexOf('function compactProductCard('));
assert(x.includes('Heute in DEGIRO-Liste bestätigt'));
assert(x.includes('Listung ist kein ausführbarer DEGIRO-Orderkurs'));
console.log('DEGIRO list proof: current/historical/server confirmation displayed, never equated with executable broker order.');
