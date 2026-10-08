// Reuse the browser's complete selection rules on the server. No submitted
// "approved" flag, ranking or notification text is trusted.
const fs=require('fs'),vm=require('vm');
function evaluate(input,now=Date.now()){
 if(!input||!Array.isArray(input.products)||input.products.length>12)throw Error('Produktliste ungültig');
 const captured=Number(input.capturedAt);
 if(!Number.isFinite(captured)||captured>now+1000||now-captured>15000)throw Error('Prüfanfrage veraltet');
 const sandbox={window:{},localStorage:{getItem:key=>key==='bobFixedScreenshotKoV1'?JSON.stringify(input.fixedBarriers||{}):null}};
 vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync(__dirname+'/degiro_assistant.js','utf8'),sandbox,{timeout:2000});
 sandbox.input=JSON.parse(JSON.stringify(input));
 const run=t=>{
  sandbox.now=t;
  return vm.runInContext(`(()=>{
   const bundle=input.bundle||{},spots=bundle.spots||{},age=Number(spots.xaus_age_seconds)+(now/1000-Number(bundle.fetched_at));
   const fresh=spots.xaus_age_seconds!=null&&bundle.fetched_at!=null&&age>=0&&age<=60&&!spots.spot_error&&Number(spots.xaus)>0;
   const context={...input.context,now,spot:Number(spots.xaus),spotFresh:fresh};
   if(!fresh||bundle.history?.data_state?.status!=='fresh')context.direction='NEUTRAL';
   return window.BobDegiro.selectionWorkflow(input.products,context,bundle,input.references||[]);
  })()`,sandbox,{timeout:2000});
 };
 const flow=run(now),candidates=flow.groups.flatMap(g=>g.candidates);
 const signature=items=>items.map(p=>[p.isin,p.direction,p.scope].join(':')).sort().join('|');
 let duration=30000;
 if(candidates.length){
  // Never queue a recommendation beyond the expiry of its underlying evidence.
  let lo=0,hi=30000;const key=signature(candidates);
  while(hi-lo>1000){const mid=Math.floor((lo+hi)/2);if(signature(run(now+mid).groups.flatMap(g=>g.candidates))===key)lo=mid;else hi=mid;}
  duration=lo;
 }
 const products=duration>=5000?candidates.map(p=>({isin:p.isin,name:p.name,direction:p.direction,scope:p.scope,estimated:!!p.estimated,quoteAt:p.at||p.rankingQuoteAt||p.quote?.quoteAt||null,reasons:p.reasons||[]})):[];
 return {products,gateReasons:flow.gateReasons,productIssues:flow.notApproved.map(p=>({isin:p.isin,reasons:p.reasons})),checkedAt:now,expiresAt:now+duration,reasons:duration<5000?['Pflichtnachweise laufen in wenigen Sekunden ab']:flow.gateReasons.length?flow.gateReasons:flow.notApproved.flatMap(p=>p.reasons).slice(0,3)};
}
module.exports={evaluate};
if(require.main===module){try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(fs.readFileSync(0,'utf8')))));}catch(e){process.stderr.write(String(e.message));process.exitCode=1;}}
