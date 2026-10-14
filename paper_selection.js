// Same product gates/ranking as Bob; no submitted approval is trusted.
const fs=require('fs'),vm=require('vm');
function selectionQuote(q,now){
 if(q?.paperQuoteAccepted!==true)return q;
 const m=q.metadata||{},i=q.leverageCalculation?.inputs;
 const positive=x=>typeof x==='number'&&Number.isFinite(x)&&x>0;
 if(!q.productVerified||q.sourceDisabled||m.status!==1||m.tradingHalted||m.underlyingType!=='SPOT'
  ||m.underlying!=='XAU/USD'||m.issuerExchangeCode!=='CBDE'||q.currency!=='EUR'
  ||q.source!=='comdirect · SG LiveTrading'||q.venue!=='LT Societe Generale'
  ||q.priceKind!=='market-observation'||q.isExecutableQuote!==false||q.degiroExecutable!==false
  ||!positive(q.bid)||!positive(q.ask)||q.ask<q.bid||q.delayed
  ||!i||i.basisEstimated||i.basisDelayed||!positive(i.basisPriceUsd)||!positive(i.usdEur)
  ||!positive(i.ratio)||i.ratio!==m.ratio||q.conditions?.ratio?.value!==m.ratio
  ||q.conditions?.ratio?.conditionVerified!==true)return q;
 const fields=[q.quoteAt,q.bidAt,q.askAt,i.basisAt,i.fxDataAt,i.fxEffectiveAt];
 const clocks=fields.map(x=>typeof x==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(x)?Date.parse(x):NaN);
 if(clocks.some(t=>!Number.isFinite(t)||t>now||now-t>90000)||clocks[0]!==clocks[1]||clocks[0]!==clocks[2]||Math.max(...clocks)-Math.min(...clocks)>90000)return q;
 const leverage=i.basisPriceUsd*i.usdEur*i.ratio/q.ask;
 if(!Number.isFinite(leverage)||leverage<1)return q;
 // Private copy for the paper selector only. Provider/broker flags and original
 // clocks remain unchanged; the public product quote never becomes executable.
 return {...q,paperSelectionOnly:true,direction:m.direction,ko:q.conditions?.ko?.value,
  leverage,paperLeverage:{value:leverage,kind:'calculated-gearing',
   source:'Bob · berechneter Simulationshebel aus beobachtetem Briefkurs',
   inputs:{...i,askEur:q.ask,askAt:q.askAt,priceSource:q.source},
   oldestSourceAt:new Date(Math.min(...clocks)).toISOString()}};
}
function evaluate(input,now=Date.now()){
 const selectedInput={...input,quotes:Object.fromEntries(Object.entries(input.quotes||{}).map(([isin,q])=>[isin,selectionQuote(q,now)]))};
 const env={window:{},localStorage:{getItem:k=>k==='bobFixedScreenshotKoV1'?JSON.stringify(input.fixedBarriers||{}):null},input:selectedInput,now};
 vm.createContext(env);vm.runInContext(fs.readFileSync(__dirname+'/degiro_assistant.js','utf8'),env,{timeout:2000});
 return vm.runInContext(`(()=>{
  const api=window.BobDegiro,context={...input.market.context,direction:input.market.direction,spotFresh:input.market.priceFresh,spot:input.market.price,now};
  const products=(input.products||[]).map(p=>{
   const q=input.quotes?.[p.isin];if(!q||q.isin!==p.isin)return p;
   const m=q.metadata||{};
   return {...p,quote:q,price:q.price??p.price,leverage:q.leverage??p.leverage,ko:q.conditions?.ko?.value??q.ko??m.ko??p.ko,
    productDirection:q.direction||m.direction||p.productDirection,
    isinConfirmed:api.automaticIdentity({...p,quote:q,price:q.price??p.price,leverage:q.leverage??p.leverage,ko:q.conditions?.ko?.value??q.ko??m.ko??p.ko})||p.isinConfirmed===true};
  });
  const flow=api.selectionWorkflow(products,context,input.bundle,input.references||[]);
  const valid=p=>!/FAKTOR|FACTOR/i.test(p.name||'')&&!api.knockoutStatus(p);
  const papers=[];
  if(api.selectionMarketGate(context).ok)for(const p of products){
   if(!valid(p)||api.isFutureProduct(p)||!p.isinConfirmed||!p.quote?.paperSelectionOnly
    ||!api.productTermsStatus(p,now).complete)continue;
   const e=api.evaluateProduct({...p,...context});
   if(!e.ok||!e.fit||e.direction!==context.direction||e.setupScore<35||e.conflictCount>=3)continue;
   papers.push({isin:p.isin,name:p.name,direction:e.direction,scope:'XAU/USD',score:e.score,
    price:p.price,at:p.quote.quoteAt,source:p.quote.source,priceKind:'Simulationskurs · beobachteter comdirect-Geld/Brief',
    reasons:e.reasons,warnings:e.warnings});
  }
  const approved=[...flow.groups.flatMap(g=>g.candidates).filter(c=>!papers.some(p=>p.isin===c.isin)),...papers].sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin));
  const choices=approved.filter(c=>valid(products.find(p=>p.isin===c.isin)||{})).map(c=>({...c,approval:input.quotes[c.isin]?.paperSelectionOnly?'Simulationsfreigabe · beobachteter comdirect-Kurs, keine DEGIRO-Ausführung':'Bob-Pflichtprüfung bestanden',paperOnly:input.quotes[c.isin]?.paperSelectionOnly===true,koGuardRequired:true}));
  // The user's existing indicative mode remains a separate Gold-only model.
  if(!choices.length&&!flow.gateReasons.length)for(const x of api.indicativeRecommendations(products.filter(valid),context))
   choices.push({isin:x.p.isin,name:x.p.name,direction:context.direction,scope:api.isFutureProduct(x.p)?'FUTURE':'XAU/USD',score:x.evaluation.score,reasons:x.evaluation.reasons,approval:'Unverbindliche Berechnung mit vorhandenen Werten',indicative:true,warning:x.warning});
  const selected=new Set(choices.map(c=>c.isin));
  return {choices:choices.slice(0,3),reasons:flow.gateReasons.concat(flow.requests.filter(p=>!selected.has(p.isin)).flatMap(p=>p.reasons),flow.waiting.filter(p=>!selected.has(p.isin)).map(p=>p.reason)).slice(0,8)};
 })()`,env,{timeout:3000});
}
module.exports={evaluate,selectionQuote};
if(require.main===module){try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(fs.readFileSync(0,'utf8')))));}catch(e){process.stderr.write(e.name+': '+String(e.message).slice(0,200));process.exitCode=1;}}
