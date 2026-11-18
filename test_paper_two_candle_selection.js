'use strict';
const assert=require('node:assert/strict');
const Selection=require('./paper_two_candle_selection.js');
const now=Date.parse('2026-11-18T11:10:30Z');
const ID='DE000FG14AV8';
const clone=x=>structuredClone(x);
function fixture(side='LONG'){
 const sign=side==='LONG'?1:-1;
 const market={paperEntrySource:'two-candle-5m-paper-v1',
   direction:side,ready:true,priceFresh:true,price:4000.1,dataAt:now-10000,
   entryTimingGate:{allowed:true,paperOnly:true},
   plan:{source:'two-candle-5m-paper-v1',paperOnly:true,experimental:true,
     direction:side,unit:'USD/oz'}};
 const t=new Date(now-12000).toISOString();
 const quote={isin:ID,paperSelectionOnly:true,paperQuoteAccepted:true,
   isExecutableQuote:false,degiroExecutable:false,found:true,productVerified:true,
   source:'comdirect · SG LiveTrading',priceKind:'market-observation',
   bid:10,ask:10.1,bidAt:t,askAt:t,quoteAt:t,currency:'EUR',leverage:12,
   metadata:{direction:side,underlying:'XAU/USD',underlyingType:'SPOT',status:1},
   conditions:{ko:{value:4000.1-sign*100,conditionVerified:true,
       validityUnconfirmed:false,source:'Emittent',dateText:'18.11.2026'}}};
 const products=[{isin:ID,name:'Gold Turbo',isinConfirmed:true,
   productDirection:side,quote}];
 return {market,products,now,termsValid:()=>true,exclusion:()=>false};
}
for(const side of ['LONG','SHORT']){
 const x=fixture(side),r=Selection.select(x);
 assert.equal(r.choices.length,1,JSON.stringify(r));
 assert.deepEqual(r.reasons,[]);
 assert.equal(r.choices[0].isin,ID);
 assert.equal(r.choices[0].direction,side);
 assert.equal(r.choices[0].koGuardRequired,true);
 assert.equal(r.choices[0].paperOnly,true);
 assert.equal(r.choices[0].indicative,false);
 assert.equal(r.choices[0].estimated,false);
 assert.equal(r.realOrders,false);
 const reject=(label,mod)=>{const y=fixture(side);mod(y);
  const out=Selection.select(y);assert.equal(out.choices.length,0,label);
  assert.equal(out.realOrders,false,label);
 };
 reject('main-signal-only',y=>y.market.paperEntrySource=null);
 reject('unverified 2x5m',y=>y.market.entryTimingGate.allowed=false);
 reject('forged executable',y=>y.products[0].quote.degiroExecutable=true);
 reject('non-paper projection',y=>y.products[0].quote.paperQuoteAccepted=false);
 reject('issuer-only chart',y=>y.products[0].quote.priceKind='issuer-chart');
 reject('missing issuer identity',y=>y.products[0].quote.productVerified=false);
 reject('wrong direction',y=>y.products[0].productDirection=side==='LONG'?'SHORT':'LONG');
 reject('terminated',y=>y.products[0].quote.metadata.status=2);
 reject('wrong instrument',y=>y.products[0].quote.metadata.underlyingType='FUTURE');
 reject('not EUR',y=>y.products[0].quote.currency='CHF');
 reject('bad two-sided pair',y=>y.products[0].quote.ask=9);
 reject('stale original bid',y=>y.products[0].quote.bidAt=new Date(now-91000).toISOString());
 reject('missing ask clock',y=>y.products[0].quote.askAt=null);
 reject('wrong issuer date',y=>y.products[0].quote.conditions.ko.dateText='17.11.2026');
 reject('undated KO',y=>y.products[0].quote.conditions.ko.conditionVerified=false);
 reject('KO source missing',y=>y.products[0].quote.conditions.ko.source='');
 reject('KO already crossed',y=>y.products[0].quote.conditions.ko.value=4000.1+100*(side==='LONG'?1:-1));
 reject('incomplete terms',y=>y.termsValid=()=>false);
 reject('factor/knockout',y=>y.exclusion=()=>true);
}
console.log('Independent 2x5m paper issuer selection: original price/KO clocks, direction, safe currency, no broker approval');
