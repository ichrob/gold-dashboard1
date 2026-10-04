const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8'),script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map(),storage=new Map();
const noop=()=>{};const canvas=new Proxy({},{get:()=>noop,set:()=>true});
const element=id=>{if(!elements.has(id))elements.set(id,{value:({tf:'15m',n:'200',account:'500',risk:'1',trailAtr:'1.5',minRR:'2',displayCcy:'USD'})[id]||'',textContent:'',innerHTML:'',className:'',parentElement:{className:''},style:{},dataset:{},classList:{add:noop,remove:noop,toggle:noop},addEventListener:noop,setAttribute:noop,appendChild:noop,getContext:()=>canvas,width:800,height:220});return elements.get(id);};
const push={registered:false,serverRegistered:false,activeTrade:false,trade:false,general:false};
const env={console:{log:noop,warn:noop,info:noop,error:noop},document:{getElementById:element,querySelectorAll:()=>[],querySelector:()=>null,visibilityState:'hidden',addEventListener:noop,createElement:()=>element('temp')},window:{addEventListener:noop},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},navigator:{},Notification:{permission:'denied'},BobPush:{state:()=>push,set:()=>push,setActiveTrade:()=>push,emit:async()=>false},BobDegiro:{riskModel:()=>({ok:false,reason:'fixture'})},fetch:async()=>{throw Error('offline fixture')},setTimeout:()=>0,clearTimeout:noop,setInterval:()=>0,AbortController,Date,Math,Number,JSON,URL,Blob,Promise};
vm.createContext(env);vm.runInContext(script,env);
const result=vm.runInContext(`(()=>{
 C=Array.from({length:240},(_,i)=>{const p=4200+i*.1+Math.sin(i/8)*12;return {openTime:Math.floor(Date.now()/900000)*900000-(240-i)*900000,open:p-1,high:p+3,low:p-3,close:p,isOpen:false,instrument:'XAU/USD'};});
 lastPrice=C.at(-1).close;MTF={longs:4,shorts:0,neutral:0,overall:'LONG',byTf:{},dirs:['LONG','LONG','LONG','LONG']};
 analyze();tradeMgmt={active:true,dir:'LONG',entry:lastPrice};const snapshot=captureFibonacciMonitor();
 const ready=A.ready;A.ready=false;renderAnalysisBlocks();return {snapshot,ready};
})()`,env);
assert(result.ready);assert(result.snapshot);assert.equal(result.snapshot.timeframe,'15m');assert.equal(result.snapshot.instrument,'XAU/USD');
for(const n of ['Trend','Momentum','Fibonacci','Mtf','Volatility','Structure'])assert.equal(element('block'+n).textContent,'NEUTRAL');
vm.runInContext('tradeMgmt.test=true;A.ready=true',env);assert.equal(vm.runInContext('captureFibonacciMonitor()',env),null);
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size);
env.window.BobSession={expired:()=>true};
const expired=vm.runInContext(`(()=>{const before=C.length;tradeMgmt.active=true;updateQuick();updateTradeSignal();renderAnalysisBlocks();return {direction:confirmedSignalDirection(),mtf:getMtfState().overall,bars:C.length,before,active:tradeMgmt.active,test:tradeMgmt.test};})()`,env);
assert.equal(expired.direction,'NEUTRAL');assert.equal(expired.mtf,'NEUTRAL');
assert.equal(expired.bars,expired.before);assert(expired.active&&expired.test);
assert(element('quickSignal').textContent.includes('Anmeldung erforderlich'));
assert(element('tradeSignal').textContent.includes('Anmeldung erforderlich'));
for(const n of ['Trend','Momentum','Fibonacci','Mtf','Volatility','Structure'])assert.equal(element('block'+n).textContent,'NEUTRAL');
console.log('Dashboard runtime: analysis, six blocks, frozen monitor snapshot and test exclusion OK');

const aggregation=vm.runInContext(`(()=>{
 const start=Date.UTC(2026,9,1,12),row=i=>({openTime:start+i*300000,open:100,high:102,low:99,close:101,instrument:'XAU/USD',isOpen:false});
 const rows=[row(0),row(1),row(2)];
 return {full:aggregateBrowserBars(rows,15),gap:aggregateBrowserBars([rows[0],rows[2]],15),duplicate:aggregateBrowserBars([...rows,rows[0]],15),mixed:aggregateBrowserBars([rows[0],{...rows[1],instrument:'GC=F'},rows[2]],15),open:aggregateBrowserBars([{...rows[0],isOpen:true},...rows.slice(1)],15)};
})()`,env);
assert.equal(aggregation.full.length,1);assert.equal(aggregation.gap.length,0);assert.equal(aggregation.duplicate.length,0);assert.equal(aggregation.mixed.length,0);assert(aggregation.open[0].isOpen);

const spotChecks=vm.runInContext(`(()=>{
 const now=Date.now(),base={spot_usd_oz:4100,price_as_of:new Date(now-1000).toISOString(),stale:false,data_state:{status:'fresh'},xau:{currency:'USD',unit:'troy_oz'}};
 let rejected=0;
 for(const changes of [{price_as_of:null,updated_at:new Date(now).toISOString()},{price_as_of:new Date(now+1000).toISOString()},{price_as_of:new Date(now-181000).toISOString()},{stale:true},{spot_usd_oz:true},{price_as_of:'2026-10-03T08:00:00'}]){
  try{parseDirectSpot({...base,...changes},now);}catch(_){rejected++;}
 }
 return {rejected,valid:parseDirectSpot(base,now)};
})()`,env);
assert.equal(spotChecks.rejected,1);assert.equal(spotChecks.valid.age,1000);

// Legacy panels must lose their previous setup after a data/analysis failure.
vm.runInContext(`A.ready=true;A.at=20;A.score=90;invalidateTechnicalSignal('Historie zu alt');`,env);
assert.equal(env.A.ready,false);
for(const id of ['signal','tradeSignal']){assert(element(id).textContent.includes('ABWARTEN'));assert.equal(element(id).className,'signal neutral');}
assert(element('dgOut').textContent.includes('Abwarten'));
assert(element('dgProductOut').textContent.includes('Keine aktuelle Produktfreigabe'));
vm.runInContext('updateTradeSignal()',env);
assert(element('tradeSignal').textContent.includes('ABWARTEN'));
// Actual manual-input wiring: prices, identity and name must reach the assessment.
let entered;
env.BobDegiro={...env.BobDegiro,manualProductMissing:()=>[],selectionUiSignals:()=>({mtf:'LONG',momentum:1}),escapeHtml:s=>s,evaluateProduct:p=>{entered=p;return {ok:false,reasons:['fixture']};}};
Object.assign(element('dgIsin'),{value:'DE000FC1CHB7'});element('dgName').value='Gold Faktor Long';element('dgPrice').value='7.25';element('dgLev').value='12';element('dgKo').value='3500';
vm.runInContext('lastPrice=4000;A.at=20;checkDgProduct()',env);
assert.equal(entered.price,'7.25');assert.equal(entered.isin,'DE000FC1CHB7');assert.equal(entered.name,'Gold Faktor Long');assert.equal(entered.atr,20);
// The calculator respects the shared market veto, even with a directional score.
env.BobDegiro.selectionMarketGate=()=>({ok:false,reasons:['MTF widerspricht LONG']});
vm.runInContext('A.ready=true;A.score=90;A.at=20;calcDgTrade()',env);
assert(element('dgOut').innerHTML.includes('Kein Trade-Vorschlag'));
assert(element('dgOut').innerHTML.includes('MTF widerspricht LONG'));
console.log('Legacy panels: stale signal revoked, manual data forwarded, scenario veto preserved');

// Age is a warning for calculations, but cannot establish a current approval.
env.window.BobSession={expired:()=>false};
const ageChecks=vm.runInContext(`(()=>{
 const saved=C.map(b=>({...b}));
 C=C.map(b=>({...b,openTime:b.openTime-86400000}));
 liveBundleCache={spots:{xaus:4200,spot_price_as_of:'2020-01-01T00:00:00Z'}};
 const staleScore=timeframeScore(C,'15m');analyze();renderAnalysisAge();
 const stale={available:staleScore.available,fresh:staleScore.fresh,ready:A.ready,approval:confirmedSignalDirection(),count:C.length};
 C=C.map(b=>({...b,openTime:undefined}));
 const missing=timeframeScore(C,'15m');
 C=saved;MTF.byTf={};liveBundleCache={spots:{xaus:4200,spot_price_as_of:new Date().toISOString()}};renderAnalysisAge();
 return {stale,missing:{available:missing.available,fresh:missing.fresh},freshWarnings:analysisAgeWarnings(),noTime:dataAge(null)};
})()`,env);
assert(ageChecks.stale.available&&ageChecks.stale.ready);assert.equal(ageChecks.stale.fresh,false);assert.equal(ageChecks.stale.approval,'NEUTRAL');assert(ageChecks.stale.count>=200);
assert(ageChecks.missing.available);assert.equal(ageChecks.missing.fresh,false);assert.equal(ageChecks.freshWarnings.length,0);assert.equal(ageChecks.noTime.fresh,false);
assert.equal(element('price').style.fontStyle,'');assert.equal(element('analysisAge').hidden,true);
console.log('Age warnings: old/missing times calculate, no current approval, fresh data clears warnings');

const grouped=vm.runInContext(`(()=>{
 const a=collectiveSignal([1,1,1,1,1]),b=collectiveSignal([1]),mixed=collectiveSignal([1,1,1,-1]);
 return {a,b,mixed,short:collectiveSignal([-1]),weights:A.weights};
})()`,env);
assert.equal(grouped.a,grouped.b);assert.equal(grouped.mixed,0);assert.equal(grouped.short,-grouped.a);
assert.equal(grouped.weights.priceCollective,100);assert.equal(grouped.weights.mtf,0);assert.equal(grouped.weights.atr,0);assert.equal(grouped.weights.cr,0);

(async()=>{
 await new Promise(resolve=>setImmediate(resolve));
 push.serverRegistered=true;push.registered=true;push.general=true;push.trade=false;
 vm.runInContext('tradeMgmt={active:false}',env);
 env.navigator.serviceWorker={ready:Promise.resolve({pushManager:{getSubscription:async()=>({endpoint:'fixture'})}})};
 const paths=[];env.fetch=async path=>{paths.push(path);return {ok:false,status:502};};
 await vm.runInContext('testBackgroundPush()',env);
 assert.deepEqual(paths,['/api/push/preferences']);
 assert(element('fibMonitorStatus').textContent.includes('HTTP 502'));
 assert(!element('fibMonitorStatus').textContent.includes('Anmeldung prüfen'));
 paths.length=0;env.fetch=async path=>{paths.push(path);return {ok:true,status:200,json:async()=>({backgroundEnabled:true})};};
 await vm.runInContext('testBackgroundPush()',env);
 assert.deepEqual(paths,['/api/push/preferences','/api/push/test-background']);
 assert(element('fibMonitorStatus').textContent.startsWith('Test gespeichert.'));
 vm.runInContext('renderPush()',env);
 assert(!element('pushStatus').textContent.includes('Push-Service erreichbar'));
 env.window.BobTradeProduct=require('./trade_product.js');
 env.window.BobExitEstimate={planInput:()=>({available:true,gold:105})};
 env.BobDegiro.validIsin=()=>true;
 env.window.BobSession={expired:()=>false};push.trade=true;push.activeTrade=true;
 vm.runInContext('analysisAgeWarnings=()=>[];tradeMgmt={active:true,tradeId:"product-test",dir:"LONG",entry:100,stop:90,target:120,initialRisk:10,fibonacciMonitor:{instrument:"XAU/USD"}};lastPrice=105',env);
 env.productInput={isin:'DE000FG4JXV7',direction:'LONG',simpleSpotTurbo:true,referenceConfirmed:true,bid:20,goldReference:100,fxReference:.9,fxScenario:.9,ratio:.1,strike:50,ko:50,entry:20,quantity:10,source:'fixture',referenceAt:'02/10/2026 15:04'};
 let sent;
 env.fetch=async(path,opts)=>{sent=JSON.parse(opts.body);return {ok:true,json:async()=>({backgroundEnabled:true,backgroundTrade:{tradeId:'product-test',stop:95,target:140}})};};
 await vm.runInContext('activateProductTrade(productInput)',env);
 assert.equal(sent.background.trade.product.isin,env.productInput.isin);
 assert.equal(vm.runInContext('tradeMgmt.target',env),140);
 assert(element('stopPanel').textContent.includes('EUR/Stück (berechnet)'));
 assert(element('stopPanel').textContent.includes('23.6000'));
 assert(element('stopPanel').textContent.includes('DE000FG4JXV7'));
 assert.equal(vm.runInContext('tradeMgmt.stop',env),95);
 console.log('Background test: failed sync blocks scheduling; success confirms server scheduling');
})().catch(e=>{console.error(e);process.exitCode=1;});
