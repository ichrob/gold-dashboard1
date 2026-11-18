'use strict';
// Product selection ONLY for the independently confirmed 2x5m PAPER hypothesis.
// The main selectionMarketGate (EMA/MACD/full MTF) remains unchanged. The
// alternative uses the *same* primary issuer identity and strict paper quote
// clocks, but never infers an order or a missing original KO/barrier source.
const VERSION='two-5m-product-selection-v1';
const positive=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
const ms=x=>typeof x==='string'&&/(?:Z|[+-]\d\d:\d\d)$/i.test(x)?Date.parse(x):NaN;
function zurichDate(now){
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Zurich',
  year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(now));
 const part=t=>parts.find(p=>p.type===t)?.value;
 return part('day')+'.'+part('month')+'.'+part('year');
}
function select({market,products,now,termsValid,exclusion}={}){
 const out={version:VERSION,paperOnly:true,realOrders:false,choices:[],
  reasons:['Zwei-5m-Test: unabhängige Signal- oder Produktnachweise fehlen']};
 if(!Number.isFinite(now)||!market||market.paperEntrySource!=='two-candle-5m-paper-v1'||
   !['LONG','SHORT'].includes(market.direction)||market.ready!==true||
   market.priceFresh!==true||!positive(market.price)||
   market.plan?.source!=='two-candle-5m-paper-v1'||
   market.plan?.paperOnly!==true||market.plan?.experimental!==true||
   market.plan?.direction!==market.direction||market.plan?.unit!=='USD/oz'||
   market.entryTimingGate?.paperOnly!==true||market.entryTimingGate?.allowed!==true||
   typeof termsValid!=='function'||typeof exclusion!=='function'||
   !Array.isArray(products))return out;
 const side=market.direction,sign=side==='LONG'?1:-1,day=zurichDate(now);
 const options=[];
 for(const p of products.slice(0,25)){
  const q=p?.quote,meta=q?.metadata||{},cond=q?.conditions?.ko;
  if(!p||typeof p.isin!=='string'||p.isin!==q?.isin||
     p.isinConfirmed!==true||p.productDirection!==side||
     exclusion(p)||!termsValid(p))continue;
  if(meta.direction!==side||meta.underlyingType!=='SPOT'||
     meta.underlying!=='XAU/USD'||meta.status!==1||meta.tradingHalted===true||
     q.productVerified!==true||q.sourceDisabled||q.delayed||
     q.currency!=='EUR'||!['market-observation','issuer-bid-ask'].includes(q.priceKind)||
     !positive(q.bid)||!positive(q.ask)||q.ask<q.bid||
     !positive(q.leverage)||q.leverage<1)continue;
  // Either the signed public issuer's current pair, or Bob's explicit
  // issuer/fx-verified PAPER-only projection (never an executable broker pair).
  const currentPaper=q.paperSelectionOnly===true&&q.paperQuoteAccepted===true&&
    q.isExecutableQuote===false&&q.degiroExecutable===false;
  const issuerPair=q.found===true&&q.isExecutableQuote!==false&&
    q.paperSelectionOnly!==true;
  if(!currentPaper&&!issuerPair)continue;
  const t1=ms(q.bidAt),t2=ms(q.askAt),gold=market.dataAt;
  if(![t1,t2,gold].every(t=>Number.isFinite(t)&&t<=now&&now-t<=90000)||
     Math.max(t1,t2,gold)-Math.min(t1,t2,gold)>90000)continue;
  if(!positive(cond?.value)||cond?.conditionVerified!==true||
     cond?.validityUnconfirmed===true||typeof cond?.source!=='string'||
     !cond.source||cond.dateText!==day)continue;
  const distance=sign*(market.price-cond.value)/market.price;
  if(!(distance>0))continue;
  options.push({isin:p.isin,direction:side,scope:'XAU/USD',
   score:Math.round(distance*10000)/100,
   koGuardRequired:true,indicative:false,estimated:false,paperOnly:true,
   approval:'Nur virtueller 2x5m-Test; KO- und Euro-Originalquote im Konto erneut prüfen'});
 }
 options.sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin));
 if(options.length)out.reasons=[];
 return {...out,choices:options.slice(0,3)};
}
module.exports={VERSION,select};
