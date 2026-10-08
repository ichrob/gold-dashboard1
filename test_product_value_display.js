const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});
const b=window.BobDegiro,isin='DE000SQ02JQ6',now=Date.now(),at=new Date(now-1000).toISOString();
const p={isin,index:0,price:100,quote:{isin,productVerified:true,found:false,analysisQuote:{currency:'EUR',bid:180.2,ask:180.21,bidAt:at,askAt:at,source:'SG',priceKind:'issuer-chart'},leverage:2.0447,leverageAt:at}};
let f=b.productFieldStates(p,now);
assert.equal(f.ask.value,180.21);assert.equal(f.bid.value,180.2);assert.equal(f.leverage.value,2.0447);
assert(b.compactProductCard(p).includes('Geld, Brief und Hebel vorhanden'));
const shot={isin,index:1,snapshot:{isin,currency:'EUR',bid:10,ask:10.01,sourceTime:at,evidence:{Hebel:{value:5,at,source:'image'}}}};
f=b.productFieldStates(shot,now);assert.equal(f.ask.value,10.01);assert.equal(f.leverage.value,5);
assert(b.compactProductCard({isin,index:2}).includes('Fehlende Kurswerte: Geld, Brief, Hebel'));
assert.equal(b.productFieldStates({...shot,snapshot:{...shot.snapshot,isin:'DE000FG5GUN3'}},now).ask.state,'fehlt');
assert.equal(b.productFieldStates({...shot,snapshot:{...shot.snapshot,currency:'CHF'}},now).ask.state,'fehlt');
const stale=JSON.parse(JSON.stringify(p));stale.quote.analysisQuote.bidAt=stale.quote.analysisQuote.askAt=new Date(now-3600000).toISOString();
assert.equal(b.productFieldStates(stale,now).ask.state,'veraltet');
console.log('Product value display: OK');

const auto=b.compactProductCard(p,['BNP-Kursabruf: Quellenantwort veraltet']);assert(auto.includes('derzeit keine neuen Bilder erforderlich'));
const actualMissing=b.compactProductCard(p,['Bezugsverhältnis fehlt']);assert(!actualMissing.includes('derzeit keine neuen Bilder erforderlich'));
