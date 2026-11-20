'use strict';
// Standby inventory is read-only and must not claim trade approval.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const src=fs.readFileSync(require('node:path').join(__dirname,'degiro_assistant.js'),'utf8');
const start=src.indexOf('function standbyProductCandidates(');
const end=src.indexOf('function renderContinuingAnalysis(',start);
assert(start>=0 && end>start,'standby ranking helpers present');

const now=Date.parse('2026-11-20T19:10:30Z');
const str=(x)=>String(x);
const context={
 n:x=>x===null||x===undefined||x===''?null:
    Number.isFinite(Number(x))?Number(x):null,
 validIsin:x=>typeof x==='string'&&/^DE[0-9A-Z]{10}$/.test(x),
 knockoutStatus:p=>p.knockedOut===true,
 isFutureProduct:p=>p.isFuture===true,
 productTermsStatus:p=>({complete:p.termsComplete===true}),
 esc:str,
 renderIsinCopy:()=>'<span data-copy-safe></span>',
 Date, Math, Number, Array, RegExp, String
};
const api=vm.runInNewContext(src.slice(start,end)+
 ';({standbyProductCandidates,renderStandbyProductRanking})',context);
const id='DE000FB0A490';
function product(){
 const time=new Date(now-12000).toISOString();
 const quote={isin:id,source:'SG · datierter Chartkurs',
  productVerified:true,metadata:{status:1,direction:'SHORT',issuerExchangeCode:'CBDE',
    underlyingType:'SPOT',underlying:'XAU/USD'},
  conditions:{ko:{value:3750,conditionVerified:true,dateText:'20.11.2026'}},
  secondaryQuote:{isin:id,source:'comdirect · SG LiveTrading',venue:'LT Societe Generale',
    currency:'EUR',priceKind:'market-observation',bid:49.1,ask:49.2,
    isExecutableQuote:false,degiroExecutable:false,
    bidAt:time,askAt:time,quoteAt:time}};
 return {isin:id,name:'Gold Turbo Short',productDirection:'SHORT',ko:3750,
  isinConfirmed:true,termsComplete:true,quote};
}
const base={direction:'NEUTRAL',spotFresh:true,spot:3510,atr:20,now};
const ready=api.standbyProductCandidates([product()],base);
assert.equal(ready.length,1,'verified SHORT stays prepared on NEUTRAL');
assert.equal(ready[0].isin,id);
assert.equal(ready[0].readyForEntry,false);
assert.match(api.renderStandbyProductRanking([product()],base),/ABWARTEN/);
assert.match(api.renderStandbyProductRanking([product()],base),/DE000FB0A490/);
assert.match(api.renderStandbyProductRanking([product()],base),/Kein virtueller oder echter Einstieg/);
function reject(name,fn){
 const p=product();fn(p);
 assert.equal(api.standbyProductCandidates([p],base).length,0,name);
}
reject('stale bid/ask',p=>{
 const old=new Date(now-91000).toISOString();
 p.quote.secondaryQuote.bidAt=old;
 p.quote.secondaryQuote.askAt=old;
 p.quote.secondaryQuote.quoteAt=old;
});
reject('undated quote',p=>{p.quote.secondaryQuote.quoteAt='heute';});
reject('one-sided only',p=>{p.quote.secondaryQuote.ask=null;});
reject('chart only',p=>{p.quote.secondaryQuote.priceKind='issuer-chart';});
reject('wrong issuer route',p=>{p.quote.secondaryQuote.venue='Swiss DOTS';});
reject('no issuer terms',p=>{p.termsComplete=false;});
reject('KO too close',p=>{p.ko=3515;p.quote.conditions.ko.value=3515;});
reject('past KO',p=>{p.ko=3450;p.quote.conditions.ko.value=3450;});
reject('wrong side',p=>{p.productDirection='LONG';});
reject('ended',p=>{p.quote.metadata.status=2;});
reject('factor',p=>{p.name='Gold Faktor Short';});
reject('future',p=>{p.isFuture=true;});
reject('knocked out',p=>{p.knockedOut=true;});
reject('forged broker quote',p=>{p.quote.secondaryQuote.isExecutableQuote=true;});
assert.equal(api.standbyProductCandidates([product()],{...base,spotFresh:false}).length,0);
assert.equal(api.standbyProductCandidates([product()],{...base,spot:null}).length,0);
const report=api.renderStandbyProductRanking([product()],{...base,spotFresh:false});
assert.match(report,/Kein aktuell vollständig nachgewiesener Produktkandidat/);
assert.equal(api.standbyProductCandidates([product(),product()],base).length,1);
console.log('standby product ranking: passed, no trade entry granted');
