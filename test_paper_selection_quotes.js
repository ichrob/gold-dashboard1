const assert=require('assert/strict'),{evaluate,selectionQuote}=require('./paper_selection');
const now=Date.parse('2026-10-14T14:50:30Z'),at=new Date(now-30000).toISOString(),isin='DE000FG7K275';
const conditions=Object.fromEntries(Object.entries({underlying:'XAU/USD',currency:'EUR',ratio:.1,type:'BEST Turbo-Optionsscheine (Open-End)',maturity:'Open End',ko:4400,strike:4400}).map(([k,value])=>[k,{value,source:'https://issuer.test/'+isin,at,reviewedAt:at,conditionVerified:true,dateText:'14.10.2026'}]));
const q={isin,productVerified:true,paperQuoteAccepted:true,found:true,eligible:false,marketOpen:true,
 source:'comdirect · SG LiveTrading',venue:'LT Societe Generale',currency:'EUR',priceKind:'market-observation',
 isExecutableQuote:false,degiroExecutable:false,bid:9.99,ask:10,price:10,bidAt:at,askAt:at,quoteAt:at,checkedAt:at,
 leverage:35,leverageCalculation:{available:true,inputsFresh:true,inputs:{basisPriceUsd:4000,basisAt:at,usdEur:.9,ratio:.1,askEur:10,fxDataAt:at,fxEffectiveAt:at}},
 metadata:{status:1,direction:'SHORT',underlyingType:'SPOT',underlying:'XAU/USD',issuerExchangeCode:'CBDE',currency:'EUR',ratio:.1,ko:4400,strike:4400,termsDated:true,termsDate:'14.10.2026'},conditions};
const input={products:[{isin,name:'SG Gold BEST SHORT',productDirection:'SHORT',isinConfirmed:false}],quotes:{[isin]:q},market:{direction:'SHORT',price:4000,priceFresh:true,context:{policy:'intraday-trend-follow-v7',signalScore:0,trend:'SHORT',trend2:'NEUTRAL',mtf:'SHORT',hist:-1,momentum:-1,rsi:40,atr:10}},bundle:{}};
const before=JSON.stringify(input),projected=selectionQuote(q,now);
assert.equal(projected.leverage,36);assert.equal(projected.eligible,false);
assert.equal(projected.isExecutableQuote,false);assert.equal(projected.degiroExecutable,false);
const r=evaluate(input,now);assert.equal(r.choices.length,1,JSON.stringify(r));
assert.equal(r.choices[0].paperOnly,true);assert.equal(r.choices[0].koGuardRequired,true);
assert.equal(JSON.stringify(input),before,'provider payload must remain unchanged');
for(const change of [{bidAt:new Date(now-90001).toISOString()},{isin:'wrong'},{currency:'CHF'},
 {source:'SG chart'},{venue:'other'},{priceKind:'issuer-chart'},{paperQuoteAccepted:false},
 {leverageCalculation:{inputs:{}}},{metadata:{...q.metadata,status:2}},
 {conditions:{...conditions,ratio:{...conditions.ratio,conditionVerified:false}}}]){
 const changed={...q,...change};
 if(change.isin)continue; // Exact identity is checked in the full selector.
 assert.notEqual(selectionQuote(changed,now).paperSelectionOnly,true,JSON.stringify(change));
}
assert.equal(evaluate({...input,quotes:{[isin]:{...q,isin:'wrong'}}},now).choices.filter(c=>!c.indicative).length,0);
assert.equal(evaluate({...input,market:{...input.market,direction:'NEUTRAL'}},now).choices.length,0);
console.log('Paper selection: observed bid/ask reaches approved candidate; identity, dates, terms, market and broker isolation pass');

// Counterfactual research retains eligible alternatives beyond the displayed Top 3.
function testIsin(i){const prefix='DE000TEST0'+i;for(let check=0;check<10;check++){const value=prefix+check,digits=Array.from(value,c=>/[A-Z]/.test(c)?String(c.charCodeAt(0)-55):c).join('');let sum=0;for(let n=digits.length-1,d=false;n>=0;n--,d=!d){let x=Number(digits[n])*(d?2:1);sum+=x>9?x-9:x;}if(sum%10===0)return value;}}
const all=Array.from({length:5},(_,i)=>({...input.products[0],isin:testIsin(i)}));
const quotes=Object.fromEntries(all.map(p=>[p.isin,JSON.parse(JSON.stringify(q).replaceAll(isin,p.isin))]));
const expanded=evaluate({...input,products:all,quotes},now);
assert.equal(expanded.choices.length,3,JSON.stringify(expanded));assert.equal(expanded.researchCandidates.length,5);
assert(expanded.researchCandidates.every(c=>c.paperOnly));
const fs=require('fs'),vm=require('vm'),w={};
vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window:w});
const expectedBasis=w.BobDegiro.selectedPriceSnapshot({...input.products[0],quote:projected,price:projected.price,leverage:projected.leverage},now);
assert(expectedBasis);
assert.equal(r.choices[0].priceBasis.selectionKey,expectedBasis.selectionKey);
assert.equal(r.choices[0].priceBasis.degiroExecutable,false);
// Risiko study reuses the exact signal and monitor, without changing old selectors.
const minute=Math.floor(now/60000)*60000;
const rb=Array.from({length:21},(_,i)=>({openTime:minute-(21-i)*60000,instrument:'XAU/USD',isOpen:false,open:4000,high:4001,low:3999,close:4000}));
for(const b of rb.slice(-2)){b.close=3997;b.low=3997;}
const riskBundle={spots:{is_genuine_xauusd_spot:true,xaus:3996.8,spot_price_as_of:new Date(now).toISOString()},history:{bars_by_tf:{'1m':rb}}};
const riskInput={...input,riskOnly:true,bundle:riskBundle,positions:{'0':{id:'paper-0',direction:'SHORT',goldEntry:4000,goldStop:4020,watch:{}}}};
const riskResult=evaluate(riskInput,now);
assert.equal(riskResult.signal.stage,'BESTÄTIGT');
assert.equal(riskResult.signal.direction,'SHORT');
assert.equal(riskResult.choices.length,1,JSON.stringify(riskResult));
assert.equal(riskResult.watches['0'].id,'paper-0');
assert.equal(evaluate({...riskInput,quotes:{[isin]:{...q,productVerified:false}}},now).choices.length,0);
console.log('Risk paper selector: shared confirmed signal, qualified product and isolated monitor passed');
