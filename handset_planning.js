// Same browser product/stop/CHF functions, isolated from orders and ranking.
'use strict';
const fs=require('fs'),vm=require('vm');
const ModelReference=require('./model_product_reference.js');
function evaluate(input){
 const now=input.now;
 if(!Number.isFinite(now)||!Array.isArray(input.products)||input.products.length>12)
  throw Error('Ungültiger Planungseingang');
 const env={window:{},localStorage:{getItem:()=>null},input,now,ModelReference};
 vm.createContext(env);
 for(const file of ['degiro_assistant.js','bob_stop_assistant.js','degiro_android_bridge.js','manual_ranking_order.js'])
  vm.runInContext(fs.readFileSync(__dirname+'/'+file,'utf8'),env,{timeout:2000});
 return vm.runInContext(`(()=>{
  const api=window.BobDegiro,calc=window.BobManualTop3,cfg=input.config||{},
   accountEvidenceConditional=input.accountEvidenceConditional===true;
  const items=(input.report?.items||[]).filter(x=>x?.isin).slice(0,12).map(row=>{
   const isin=row.isin,original=input.products.find(p=>p.isin===isin),q=input.quotes?.[isin];
   const p=original&&q?.isin===isin?{...original,quote:q,
    ko:q.conditions?.ko?.value??q.ko??q.metadata?.ko??original.ko,
    productDirection:q.metadata?.direction||q.direction||original.productDirection}:original?{...original}:null;
   const direction=p?.productDirection;
   // The issuer/audit terminal state takes precedence over missing screen data.
   // A last bid is retained in the original report, never treated as an entry.
   if(row.state==='terminated'){
    const reason='Produkt vom Emittenten als beendet gemeldet';
    return {isin,available:false,reason,reasons:[reason],researchOnly:true,
     quantity:null,totalCHF:null,lossCHF:null,modelStop:null,modelTarget:null,
     modelReferenceAt:null,sourceAt:null,observedAt:row.handsetObservation?.observedAt||null,
     feeAssessment:{available:false,feesCHF:null,reason:'Bei beendetem Produkt keine Einstiegsberechnung'},
     automaticScenarios:[],entrySuitable:false,entryApproved:false,copyAllowed:false,
     rankingPenalty:false,brokerExecutionVerified:false,orderSubmitted:false};
   }
   // The normal identity validator still decides; saved client flags cannot
   // establish a new identity or turn a terminal product into a valid plan.
   if(p)p.isinConfirmed=api.automaticIdentity(p);
   const imported=calc.importHandsetReport(input.report,isin,now);
   const market={...(input.plans?.[direction]||{}),spots:input.spots};
   // Independent original-gold stop/target risk reference per displayed ISIN.
   // An unpriced product still shows its GOLD risk boundaries; never display
   // these USD/oz levels as a EUR/CHF issuer bid/ask or approved product stop.
   const goldSpot=input.spots||{},gp=input.plans?.[direction]||{},
    goldStamp=Date.parse(goldSpot.spot_price_as_of||''),
    goldGeometry=direction==='LONG'?gp.stop<gp.entry&&gp.entry<gp.target:
     direction==='SHORT'?gp.target<gp.entry&&gp.entry<gp.stop:false;
   const issuerActive=['analysis-evidence-complete','issuer-evidence-complete'].includes(row.state);
   const goldVerified=issuerActive&&goldSpot.is_genuine_xauusd_spot===true&&!goldSpot.spot_error&&
    Number.isFinite(goldSpot.xaus)&&goldSpot.xaus>0&&
    Number.isFinite(goldStamp)&&0<=now-goldStamp&&now-goldStamp<=60000&&
    gp.available===true&&gp.direction===direction&&goldGeometry&&
    [gp.entry,gp.stop,gp.target].every(x=>Number.isFinite(x)&&x>0)&&
    Math.abs(gp.entry-goldSpot.xaus)<=.10;
   const goldReference=goldVerified?{state:'available',direction,unit:'USD/oz',
    entry:gp.entry,stop:gp.stop,target:gp.target,sourceAt:goldSpot.spot_price_as_of,
    entrySuitable:gp.entrySuitable!==false,
    reason:gp.entrySuitable===false?'Zielhindernis: keine Handelsfreigabe':null,
    productPriceApproved:false,modelTradeApproved:false}:
    {state:'unavailable',reason:'Keine aktuell bestätigte Gold-Stop-/Zielreferenz',
     productPriceApproved:false,modelTradeApproved:false};
   const quote=p&&calc.selectQuoteByPriority(p,now)?.quote;
   // A technical reference requires original product/quote proof, not a
   // handset screenshot. Missing handset evidence still blocks comparison
   // admission and never makes the reference an executable plan.
   const stop=p&&quote?api.productRiskComparison(p,market,now,quote):null;
   // A recent calculated price can support a separate stop/target *display*,
   // never the real quote, entry quantity or product authorization.
   const estimate=stop?.available?null:ModelReference.calculate({
    quote:q,plan:input.plans?.[direction],spots:input.spots,now});
   if(stop?.reason==='Bestätigtes passendes EUR-/CHF-Spot-Turbo-Modell fehlt'&&q?.handsetModelCheck?.reason)
    stop.reason=q.handsetModelCheck.reason;
   const fx=calc.readChfFx(input.spots,now,quote?.currency);
   const feeAssessment=calc.resolveFees({config:cfg,report:input.report,isin,spots:input.spots,now});
   const rowConfig={...cfg,feesCHF:feeAssessment.available?feeAssessment.feesCHF:null};
   const candidate={isin,direction};
   const preliminary=calc.evaluate({candidate,product:p,quote,stopPlan:stop,fx,...rowConfig,now,direction});
   if(preliminary.reasonCode==='CHF_FEES_MISSING'&&!feeAssessment.available&&feeAssessment.reason)
    preliminary.reason=feeAssessment.reason;
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
   const reasons=[accountEvidenceConditional&&
     'Basic/AutoFX aus datierten Gerätesitzungen nur als Simulationsannahme; tatsächliche Brokergebühren und Kontogleichheit nicht bestätigt.',
    !imported.available&&imported.reason,
    !stop?.available&&(stop?.reason||'Unabhängiger Produkt-Modellplan fehlt'),
    !input.config&&'CHF-Vorgaben noch nicht dauerhaft gespeichert',
    !feeAssessment.available&&feeAssessment.reason,
    !preliminary.available&&preliminary.reason,!result.available&&result.reason].filter(Boolean);
   return {...result,isin,feeAssessment,automaticScenarios,contractModelCheck:q?.handsetModelCheck||null,
    goldReference,modelEvidenceCode:q?.handsetModelCheck?.code||null,
    modelEvidenceMissing:q?.handsetModelCheck?.unconfirmedTerms||[],
    planState:stop?.available?(stop.entrySuitable===false?'reference-target-obstacle':'reference-calculated'):
     estimate?.available?'model-only-reference':'reference-unavailable',
    modelMode:estimate?.available?estimate.mode:null,
    modelEntry:estimate?.available?estimate.modelEntry:null,
    modelWarning:estimate?.available?estimate.warning:null,
    modelEstimateReason:estimate?.available?null:
      q?.handsetModelCheck?.reason||estimate?.reason||stop?.reason||null,
    modelGoldEntry:estimate?.available?estimate.goldEntry:null,
    modelGoldStop:estimate?.available?estimate.goldStop:null,
    modelGoldTarget:estimate?.available?estimate.goldTarget:null,
    modelRatio:estimate?.available?estimate.ratio:null,
    modelStrike:estimate?.available?estimate.strike:null,
    modelKo:estimate?.available?estimate.ko:null,
    modelFxRate:estimate?.available?estimate.fxRate:null,
    modelInputAgeSeconds:estimate?.available?estimate.inputAgeSeconds:null,
    modelAnchorAgeSeconds:estimate?.available?estimate.anchorAgeSeconds:null,
    modelValidationReady:estimate?.available?estimate.validationReady:false,
    modelErrorBound:estimate?.available?estimate.errorBoundEur:null,
    modelOriginalGoldAt:estimate?.available?estimate.originalGoldAt:null,
    modelFxAt:estimate?.available?estimate.fxAt:null,
    simulationPlanningUsable:estimate?.available===true,
    simulationFillAllowed:false,
    entrySuitable:stop?.entrySuitable??null,entryWarning:stop?.entryWarning||null,entryApproved:false,
    modelStop:stop?.available?stop.stop:estimate?.available?estimate.modelStop:null,
    modelTarget:stop?.available?stop.target:estimate?.available?estimate.modelTarget:null,
    modelCurrency:stop?.available?stop.currency:estimate?.available?estimate.currency:null,
    modelReferenceAt:stop?.referenceAt||estimate?.referenceAt||null,
    fxBasis:fx.note||fx.reason,observedAt:imported.observedAt||null,
    reasons:[...new Set([...reasons,
      ...(estimate?.available?[estimate.reason,'Berechneter Modellkurs: ausdrücklich keine Handels- oder Stückzahlfreigabe']:
         !stop?.available&&estimate?.reason?[estimate.reason]:[])])],rankingPenalty:false};
  });
  return {calculatedAt:now,items,available:items.filter(x=>x.available).length,
   conditionalAvailable:items.filter(x=>x.automaticScenarios.some(s=>s.available)).length,
   configMissing:!input.config,
   accountEvidenceConditional,accountFeeConfirmed:false,
   brokerExecutionConfirmed:false,
   researchOnly:true,realOrders:false,rankingUpdated:false};
 })()`,env,{timeout:2000});
}
module.exports={evaluate};
if(require.main===module){try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(fs.readFileSync(0,'utf8')))));}
 catch(e){process.stderr.write(String(e.message));process.exitCode=1;}}
