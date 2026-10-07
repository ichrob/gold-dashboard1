// Same product gates/ranking as Bob; no submitted approval is trusted.
const fs=require('fs'),vm=require('vm');
function evaluate(input,now=Date.now()){
 const env={window:{},localStorage:{getItem:k=>k==='bobFixedScreenshotKoV1'?JSON.stringify(input.fixedBarriers||{}):null},input,now};
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
  const approved=flow.groups.flatMap(g=>g.candidates).sort((a,b)=>b.score-a.score||a.isin.localeCompare(b.isin));
  const valid=p=>!/FAKTOR|FACTOR/i.test(p.name||'')&&!api.knockoutStatus(p);
  const choices=approved.filter(c=>valid(products.find(p=>p.isin===c.isin)||{})).map(c=>({...c,approval:'Bob-Pflichtprüfung bestanden'}));
  // The user's existing indicative mode remains a separate Gold-only model.
  if(!choices.length&&!flow.gateReasons.length)for(const x of api.indicativeRecommendations(products.filter(valid),context))
   choices.push({isin:x.p.isin,name:x.p.name,direction:context.direction,scope:api.isFutureProduct(x.p)?'FUTURE':'XAU/USD',score:x.evaluation.score,reasons:x.evaluation.reasons,approval:'Unverbindliche Berechnung mit vorhandenen Werten',indicative:true,warning:x.warning});
  return {choices:choices.slice(0,3),reasons:flow.gateReasons.concat(flow.requests.flatMap(p=>p.reasons),flow.waiting.map(p=>p.reason)).slice(0,8)};
 })()`,env,{timeout:3000});
}
module.exports={evaluate};
if(require.main===module){try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(fs.readFileSync(0,'utf8')))));}catch(e){process.stderr.write(e.name+': '+String(e.message).slice(0,200));process.exitCode=1;}}
