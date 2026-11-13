// Same browser product/stop/CHF functions, isolated from orders and ranking.
'use strict';
const fs=require('fs'),vm=require('vm');
function evaluate(input){
 const now=input.now;
 if(!Number.isFinite(now)||!Array.isArray(input.products)||input.products.length>12)
  throw Error('Ungültiger Planungseingang');
 const env={window:{},localStorage:{getItem:()=>null},input,now};
 vm.createContext(env);
 for(const file of ['degiro_assistant.js','bob_stop_assistant.js','degiro_android_bridge.js','manual_ranking_order.js'])
  vm.runInContext(fs.readFileSync(__dirname+'/'+file,'utf8'),env,{timeout:2000});
 return vm.runInContext(`(()=>{
  const api=window.BobDegiro,calc=window.BobManualTop3,cfg=input.config||{};
  const items=(input.report?.items||[]).filter(x=>x.handsetObservation).slice(0,12).map(row=>{
   const isin=row.isin,original=input.products.find(p=>p.isin===isin),q=input.quotes?.[isin];
   const p=original&&q?.isin===isin?{...original,quote:q,
    ko:q.conditions?.ko?.value??q.ko??q.metadata?.ko??original.ko,
    productDirection:q.metadata?.direction||q.direction||original.productDirection}:original?{...original}:null;
   const direction=p?.productDirection;
   // The normal identity validator still decides; saved client flags cannot
   // establish a new identity or turn a terminal product into a valid plan.
   if(p)p.isinConfirmed=api.automaticIdentity(p);
   const imported=calc.importHandsetReport(input.report,isin,now);
   const market={...(input.plans?.[direction]||{}),spots:input.spots};
   const quote=p&&calc.selectQuoteByPriority(p,now)?.quote;
   const stop=imported.available&&p&&quote?api.productRiskComparison(p,market,now,quote):null;
   const fx=calc.readChfFx(input.spots,now,quote?.currency);
   const feeAssessment=calc.resolveFees({config:cfg,report:input.report,isin,spots:input.spots,now});
   const rowConfig={...cfg,feesCHF:feeAssessment.available?feeAssessment.feesCHF:null};
   const candidate={isin,direction};
   const preliminary=calc.evaluate({candidate,product:p,quote,stopPlan:stop,fx,...rowConfig,now,direction});
   const result=calc.compareHandsetModel({report:input.report,candidate,product:p,
    preliminary,fx,...rowConfig,now,direction});
   const automaticScenarios=input.config?calc.automaticFeeScenarios({config:cfg,
    report:input.report,isin,spots:input.spots,now}).map(fee=>{
     const scenarioConfig={...cfg,feesCHF:fee.available?fee.feesCHF:null};
     const plan=calc.evaluate({candidate,product:p,quote,stopPlan:stop,fx,...scenarioConfig,now,direction});
     const compared=calc.compareHandsetModel({report:input.report,candidate,product:p,
      preliminary:plan,fx,...scenarioConfig,now,direction});
     return {...compared,reason:!fee.available?fee.reason:!stop?.available?
      (stop?.reason||'Unabhängiger Produkt-Modellplan fehlt'):compared.reason,
      feeAssessment:fee,assumptions:fee.assumptions,conditional:true,settingsConfirmed:false,
      entrySuitable:stop?.entrySuitable??null,entryWarning:stop?.entryWarning||null,
      entryApproved:false,copyAllowed:false,rankingPenalty:false,orderSubmitted:false};
    }):[];
   const reasons=[!imported.available&&imported.reason,
    !stop?.available&&(stop?.reason||'Unabhängiger Produkt-Modellplan fehlt'),
    !input.config&&'CHF-Vorgaben noch nicht dauerhaft gespeichert',
    !feeAssessment.available&&feeAssessment.reason,
    !preliminary.available&&preliminary.reason,!result.available&&result.reason].filter(Boolean);
   return {...result,isin,feeAssessment,automaticScenarios,
    entrySuitable:stop?.entrySuitable??null,entryWarning:stop?.entryWarning||null,entryApproved:false,
    modelStop:stop?.available?stop.stop:null,
    modelTarget:stop?.available?stop.target:null,modelReferenceAt:stop?.referenceAt||null,
    fxBasis:fx.note||fx.reason,observedAt:imported.observedAt||null,
    reasons:[...new Set(reasons)],rankingPenalty:false};
  });
  return {calculatedAt:now,items,available:items.filter(x=>x.available).length,
   conditionalAvailable:items.filter(x=>x.automaticScenarios.some(s=>s.available)).length,
   configMissing:!input.config,researchOnly:true,realOrders:false,rankingUpdated:false};
 })()`,env,{timeout:2000});
}
module.exports={evaluate};
if(require.main===module){try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(fs.readFileSync(0,'utf8')))));}
 catch(e){process.stderr.write(String(e.message));process.exitCode=1;}}
