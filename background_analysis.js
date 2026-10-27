// Run Bob's actual dashboard analysis on the server; never duplicate its score formula.
const fs=require('fs'),vm=require('vm');
const LateEntry=require('./late_entry_guard.js');
function evaluate(input, {render=false}={}){
 const noop=()=>{},elements=new Map(),canvas=new Proxy({},{get:()=>noop,set:()=>true});
 const element=id=>{if(!elements.has(id))elements.set(id,{value:({tf:input.timeframe||'15m',n:'200',account:'500',risk:'1',trailAtr:String(input.trailAtr||1.5),minRR:'2',displayCcy:'USD'})[id]||'',textContent:'',innerHTML:'',className:'',parentElement:{className:''},style:{},dataset:{},classList:{add:noop,remove:noop,toggle:noop},addEventListener:noop,setAttribute:noop,appendChild:noop,append:noop,selectedOptions:[{textContent:"15 Minuten"}],getContext:()=>canvas,getBoundingClientRect:()=>({width:800,height:300}),width:800,height:220});return elements.get(id);};
 const push={registered:false,general:false,trade:false,activeTrade:false};
 const env={input,render,console:{log:noop,warn:noop,info:noop,error:noop},document:{getElementById:element,querySelectorAll:()=>[],querySelector:()=>null,visibilityState:'hidden',addEventListener:noop,createTextNode:text=>({textContent:text}),createElement:()=>element('temp')},window:{addEventListener:noop},localStorage:{getItem:()=>null,setItem:noop},navigator:{},Notification:{permission:'denied'},BobPush:{state:()=>push,set:()=>push,setActiveTrade:()=>push,emit:async()=>false},BobDegiro:{riskModel:()=>({ok:false})},fetch:async()=>{throw Error('Headless analysis has no network access')},setTimeout:()=>0,clearTimeout:noop,setInterval:()=>0,AbortController,Date,Math,Number,JSON,URL,Blob,Promise};
 env.LateEntry=LateEntry;
 vm.createContext(env);
 const html=fs.readFileSync(__dirname+'/Bob.html','utf8');
 const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].find(m=>m[1].includes('function confirmedSignalDirection()'))[1];
 vm.runInContext(script,env,{timeout:3000});
 return vm.runInContext(`(()=>{
  // UI rendering repeatedly replays signal history and formats dates. None is
  // needed by the worker: retain the shared math and evaluate direction once.
  if(!render){draw=()=>{};renderCompactAnalysis=()=>{};renderExtraDirections=()=>{};updateQuick=()=>{};updateResearchPanel=()=>{};renderIntraday=()=>{};renderDecisionExplanation=()=>{};}
  const bundle=input.bundle||{},bars=bundle.history?.bars_by_tf||{},tf=input.timeframe||'15m';
  liveBundleCache=bundle;
  window.BobLearningPolicy=input.learningPolicy||bundle.learningPolicy||null;
  C=(bars[tf]||[]).filter(b=>!b.isOpen&&b.instrument==='XAU/USD').slice(-240);
  const spot=bundle.spots||{},price=Number(spot.xaus),at=Date.parse(spot.spot_price_as_of);
  const priceFresh=spot.is_genuine_xauusd_spot===true&&Number.isFinite(price)&&price>0&&Number.isFinite(at)&&Date.now()>=at&&Date.now()-at<=60000&&!spot.spot_error;
  const earlyWarning=earlyWarningContext(bundle);
  if(C.length<100)return {earlyWarning,earlyImpulse:earlyImpulseContext(bundle),session:intradaySession(),ready:false,decisionReason:'Zu wenige abgeschlossene '+tf+'-Goldkerzen: '+C.length+'/100',price,priceFresh,dataAt:Number.isFinite(at)?at:null,direction:'NEUTRAL',mtf:'NEUTRAL'};
  const byTf=Object.fromEntries(['5m','15m','1h','4h'].map(t=>[t,timeframeScore((bars[t]||[]).filter(b=>b.instrument==='XAU/USD'),t)]));
  const hierarchy=buildMtfHierarchy(byTf,['5m','15m'].every(tf=>byTf[tf].available&&byTf[tf].fresh));
  MTF={...hierarchy,byTf,dirs:Object.values(byTf).map(x=>x.dir)};lastPrice=price>0?price:C.at(-1).close;
  analyze();
  const baseline=fiveMinuteConfirmation(bundle),trendContext=sustainedTrendContext(bundle);
  const direction=confirmedSignalDirection(),ready=A.ready&&analysisAgeWarnings().length===0;
  const confirmationAt=signalState.confirmationAt || (Number.isFinite(signalState.confirmedAt)?signalState.confirmedAt+300000:null);
  const entryTimingGate=LateEntry.check(bundle,direction,Date.now(),confirmationAt);
  const riskData=intradayRiskData(bundle);
  const context={spotFresh:priceFresh,spot:price,confirmationAt,...intradayTechnicalContext(bundle,signalState)};
  let suggestedStop=null,suggestedTarget=null,suggestedTargetPlan=null;
  if(ready&&priceFresh&&input.trade?.active){const stop=stopModel(input.trade.dir,price,A.at,input.trailAtr||1.5).stop;if(Number.isFinite(stop)&&stop>0){suggestedStop=stop;suggestedTargetPlan=targetModel(input.trade.dir,price,stop,2);suggestedTarget=suggestedTargetPlan.target;}}
  // Additional paper-only setup from the same checked evidence; never substitutes
  // the confirmed market signal, existing plan, active trade, or product gate.
  const earlyImpulse=earlyImpulseContext(bundle);
  let earlyPaperPlan=null,earlyPaperPlanReason=null;
  if(ready&&priceFresh&&earlyImpulse.available&&['LONG','SHORT'].includes(earlyImpulse.direction)
     &&!earlyImpulse.extensionRisk&&Number.isFinite(earlyImpulse.barAt)){
   const side=earlyImpulse.direction;
   const stop=stopModel(side,price,A.at,input.trailAtr||1.5).stop;
   const targetPlan=Number.isFinite(stop)&&stop>0?targetModel(side,price,stop,2):{};
   earlyPaperPlanReason=targetPlan.entrySuitable===false?targetPlan.warning:
    !Number.isFinite(targetPlan.target)||targetPlan.target<=0?(targetPlan.reason||riskData.reason||'Kein gültiger Gold-Stop/Ziel-Plan berechenbar'):null;
   if(Number.isFinite(targetPlan.target)&&targetPlan.target>0&&targetPlan.entrySuitable!==false){
    earlyPaperPlan={kind:'candidate',direction:side,entry:price,stop,target:targetPlan.target,
      unit:'USD/oz',at:Date.now(),experimental:true,source:'early-impulse-paper-v1'};
   }
  }
  let warningPaperPlan=null,warningPaperPlanReason=null;
  if(ready&&priceFresh&&earlyWarning.available&&['LONG','SHORT'].includes(earlyWarning.direction)
     &&!earlyWarning.extensionRisk&&Number.isFinite(earlyWarning.signalBarAt)){
   const side=earlyWarning.direction;
   const stop=stopModel(side,price,A.at,input.trailAtr||1.5).stop;
   const targetPlan=Number.isFinite(stop)&&stop>0?targetModel(side,price,stop,2):{};
   warningPaperPlanReason=targetPlan.entrySuitable===false?targetPlan.warning:
    !Number.isFinite(targetPlan.target)||targetPlan.target<=0?(targetPlan.reason||riskData.reason||'Kein gültiger Gold-Stop/Ziel-Plan berechenbar'):null;
   if(Number.isFinite(targetPlan.target)&&targetPlan.target>0&&targetPlan.entrySuitable!==false){
    warningPaperPlan={kind:'candidate',direction:side,entry:price,stop,target:targetPlan.target,
      unit:'USD/oz',at:Date.now(),experimental:true,source:'early-warning-paper-v2'};
   }
  }
  let monitorPlan=null;
  if(ready&&priceFresh&&['LONG','SHORT'].includes(input.monitorDirection)){
   const side=input.monitorDirection,stop=stopModel(side,price,A.at,input.trailAtr||1.5).stop;
   const target=Number.isFinite(stop)&&stop>0?targetModel(side,price,stop,2).target:null;
   if(Number.isFinite(target)&&target>0)monitorPlan={direction:side,entry:price,stop,target,kind:'existing-purchase-monitor'};
  }
  let plan=null;
  if(ready&&priceFresh&&direction!=='NEUTRAL'&&entryTimingGate.allowed){
   const stop=stopModel(direction,price,A.at,input.trailAtr||1.5).stop;
   const targetPlan=Number.isFinite(stop)&&stop>0?targetModel(direction,price,stop,2):{};
   const target=targetPlan.target;
   if(Number.isFinite(target)&&target>0)plan={targetCheck:targetPlan,entrySuitable:targetPlan.entrySuitable,kind:'candidate',direction,entry:price,stop,target,unit:'USD/oz',at:Date.now()};
  }
  if(input.trade?.active&&['entry','stop','target'].every(k=>Number.isFinite(input.trade[k])&&input.trade[k]>0))plan={kind:'active-monitor',direction:input.trade.dir,entry:input.trade.entry,stop:input.trade.stop,target:input.trade.target,unit:'USD/oz',at:Date.now(),isin:input.trade.product?.isin||null};
  return {monitorPlan,entryTimingGate,entryTiming:signalState.entryTiming||'five-minute-confirmation',confirmationAt:signalState.confirmationAt||null,baseDirection:signalState.baseDirection||direction,learningPolicy:signalState.learningPolicy,dmi:dmiContext(bundle),continuedPlan:continuedTradePlan(input.trade,bundle),fx:bundle.spots?.usd_eur_meta||null,fxByCurrency:{EUR:bundle.spots?.usd_eur_meta||null,CHF:bundle.spots?.usd_chf_meta||null},marketReview:bundle.marketReview||null,plan,trendContext,earlyImpulse,earlyWarning,warningPaperPlan,warningPaperPlanReason,earlyPaperPlan,earlyPaperPlanReason,comparisonBaseline:{ruleVersion:'intraday-responsive-v6',direction:intradaySession().entryAllowed?baseline.dir:'NEUTRAL',shadowDirection:intradaySession().entryAllowed?baseline.shadowDirection:'NEUTRAL',decisionReason:baseline.reason},analysisSnapshot:{timeframe:tf,...A,mtf:MTF},minuteEntry:minuteEntryContext(bundle,signalState),entryQuality:intradayEntryContext(bundle,signalState),ruleVersion:'intraday-trend-follow-v7',session:intradaySession(),intraday:intradayState(bundle,input.trade),analysisWarnings:analysisAgeWarnings(),ready,price,priceFresh,dataAt:Number.isFinite(at)?at:null,direction,mtf:MTF.overall,score:A.score,atr:riskData.available?riskData.atr:null,macd:A.macd,signal:A.sig,suggestedStop,suggestedTarget,suggestedTargetPlan,analysisBarAt:signalState.lastAt??C.at(-1)?.openTime,shadowDirection:signalState.shadowDirection,decisionReason:signalState.reason,context};
 })()`,env,{timeout:8000});
}
module.exports={evaluate};
if(require.main===module){try{process.stdout.write(JSON.stringify(evaluate(JSON.parse(fs.readFileSync(0,'utf8')))));}catch(e){process.stderr.write(JSON.stringify({name:e.name,message:String(e.message).slice(0,200),frames:String(e.stack).split('\n').filter(x=>/^\s+at /.test(x)).slice(0,3)}));process.exitCode=1;}}



