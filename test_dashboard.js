const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8'),script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map(),storage=new Map();
const noop=()=>{};const canvas=new Proxy({},{get:(_,key)=>key==='measureText'?text=>({width:text.length*6}):noop,set:()=>true});
const element=id=>{if(!elements.has(id))elements.set(id,{value:({tf:'15m',n:'200',account:'500',risk:'1',trailAtr:'1.5',minRR:'2',displayCcy:'USD'})[id]||'',textContent:'',innerHTML:'',className:'',parentElement:{className:''},style:{},dataset:{},classList:{add:noop,remove:noop,toggle:noop},addEventListener:noop,setAttribute:noop,appendChild:noop,append:noop,selectedOptions:[{textContent:"15 Minuten"}],getContext:()=>canvas,getBoundingClientRect:()=>({width:800,height:300}),width:800,height:220});return elements.get(id);};
const push={registered:false,serverRegistered:false,activeTrade:false,trade:false,general:false};
const env={console:{log:noop,warn:noop,info:noop,error:noop},document:{getElementById:element,querySelectorAll:()=>[],querySelector:()=>null,visibilityState:'hidden',addEventListener:noop,createTextNode:text=>({textContent:text}),createElement:()=>element('temp')},window:{addEventListener:noop},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},navigator:{},Notification:{permission:'denied'},BobPush:{state:()=>push,set:()=>push,setActiveTrade:()=>push,emit:async()=>false},BobDegiro:{riskModel:()=>({ok:false,reason:'fixture'})},fetch:async()=>{throw Error('offline fixture')},setTimeout:()=>0,clearTimeout:noop,setInterval:()=>0,AbortController,Date,Math,Number,JSON,URL,Blob,Promise};
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

// Signal changes count unique, consecutive, CLOSED 5m candles, never UI calls.
const confirmations=vm.runInContext(`(()=>{
 const run=dirs=>confirmClosedSignals(dirs.map((dir,i)=>({dir,at:300000*(i+1),valid:true})));
 const long=[{dir:'LONG',at:300000,valid:true},{dir:'LONG',at:600000,valid:true}];
 return {one:run(['LONG']),two:run(['LONG','LONG']),pending:run(['LONG','LONG','SHORT']),reverse:run(['LONG','LONG','SHORT','SHORT']),wait:run(['LONG','LONG','NEUTRAL','NEUTRAL']),noise:run(['LONG','LONG','SHORT','LONG','SHORT']),duplicate:confirmClosedSignals([long[0],long[0]]),gap:confirmClosedSignals([long[0],{...long[1],at:900000}]),invalid:confirmClosedSignals([...long,{at:900000,valid:false,dir:'LONG'}]),missing:fiveMinuteConfirmation({})};
})()`,env);
assert.equal(confirmations.one.dir,'NEUTRAL');assert.equal(confirmations.one.count,1);
assert.equal(confirmations.two.dir,'LONG');assert.equal(confirmations.pending.dir,'LONG');
assert.equal(confirmations.reverse.dir,'SHORT');assert.equal(confirmations.wait.dir,'NEUTRAL');
assert.equal(confirmations.noise.dir,'LONG');assert.equal(confirmations.noise.count,1);
for(const key of ['duplicate','gap','invalid','missing'])assert.equal(confirmations[key].dir,'NEUTRAL');
const replay=vm.runInContext(`(()=>{
 const now=Math.floor(Date.now()/14400000)*14400000,steps={'5m':300000,'15m':900000,'1h':3600000,'4h':14400000};
 const bars=Object.fromEntries(Object.entries(steps).map(([tf,step])=>[tf,Array.from({length:205},(_,i)=>{const p=4200+i*.1+Math.sin(i/8)*12;return {openTime:now-(205-i)*step,open:p,high:p+2,low:p-2,close:p,instrument:'XAU/USD',isOpen:false};})]));
 const bundle={history:{bars_by_tf:bars}},first=fiveMinuteConfirmation(bundle,now);
 bars['5m'].push({...bars['5m'].at(-1),openTime:now,isOpen:true,close:9999});
 const open=fiveMinuteConfirmation(bundle,now);
 bars['5m'].at(-1).isOpen=false;const unfinished=fiveMinuteConfirmation(bundle,now);
 return {first,open,unfinished,stale:fiveMinuteConfirmation(bundle,now+1500000)};
})()`,env);
assert.deepEqual(replay.first,replay.open);assert.deepEqual(replay.first,replay.unfinished);
assert.equal(replay.stale.dir,'NEUTRAL');
console.log('5m confirmation: two closes, reversal, neutral, interrupted sequence, duplicates, gaps, invalid/open/stale candles OK');

// Display and approval share the exact closed-bar evidence, including genuine zero.
assert(Number.isFinite(replay.first.score));
assert.equal(replay.first.components.length,5);
assert(Number.isFinite(replay.first.scoreAt));
assert.equal(replay.stale.score,undefined);
const displayCheck=vm.runInContext(`(()=>{
 const original=confirmedSignalDirection;
 A.ready=true;window.BobSession={expired:()=>false};
 confirmedSignalDirection=()=>{signalState={dir:'NEUTRAL',score:0,scoreAt:Date.now(),components:[{label:'RSI',direction:'SHORT'}],reason:'5m-Bestätigung fehlt'};return 'NEUTRAL'};
 renderAnalysisBlocks();const zero=$('analysisQuality').textContent;
 confirmedSignalDirection=()=>{signalState={dir:'NEUTRAL',reason:'Daten fehlen'};return 'NEUTRAL'};
 renderAnalysisBlocks();const missing=$('analysisQuality').textContent;
 confirmedSignalDirection=original;return {zero,missing};
})()`,env);
assert(displayCheck.zero.includes('0/100'));
assert(displayCheck.zero.includes('RSI: SHORT'));
assert(displayCheck.zero.includes('ABWARTEN'));
assert(displayCheck.missing.includes('nicht verfügbar'));
assert(!displayCheck.missing.includes('0/100'));
console.log('Signal evidence: shared closed-bar score, timestamp, components, real zero and missing value OK');

const intradayTests=vm.runInContext(`(()=>{
 const now=Math.floor(Date.now()/900000)*900000;
 const make=(step,reverse=false)=>Array.from({length:240},(_,i)=>{const p=4200+(reverse?-1:1)*i*.2;return {instrument:'XAU/USD',openTime:now-(240-i)*step,open:p-.05,high:p+.1,low:p-.1,close:p,isOpen:false};});
 const bundle={spots:{xaus:4247.8,is_genuine_xauusd_spot:true,spot_price_as_of:new Date(now).toISOString()},history:{bars_by_tf:{'5m':make(300000),'15m':make(900000),'1h':make(3600000,true)}}};
 const good=intradayState(bundle,null,now),hit=intradayState(bundle,{active:true,dir:'LONG',stop:4248},now);
 const duplicate=JSON.parse(JSON.stringify(bundle));duplicate.history.bars_by_tf['5m'].at(-1).openTime-=300000;
 const irregular=JSON.parse(JSON.stringify(bundle));irregular.history.bars_by_tf['5m'].at(-1).openTime+=60000;
 const difference=JSON.parse(JSON.stringify(bundle));difference.spots.xaus=4132;
 const stale=JSON.parse(JSON.stringify(bundle));stale.spots.spot_price_as_of=new Date(now-61000).toISOString();
 const flat=JSON.parse(JSON.stringify(bundle));for(const row of flat.history.bars_by_tf['15m'])Object.assign(row,{open:4247.8,high:4248,low:4247.6,close:4247.8});
 return {good,hit,duplicate:intradayState(duplicate,null,now),irregular:intradayState(irregular,null,now+60000),difference:intradayState(difference,null,now),stale:intradayState(stale,null,now),flat:intradayState(flat,null,now)};
})()`,env);
assert.equal(intradayTests.good.direction,'LONG');assert(intradayTests.good.countertrend);
assert.equal(intradayTests.good.mode,'shadow');assert.equal(intradayTests.hit.tradeAction,'AUSSTIEG PRÜFEN');
for(const key of ['duplicate','irregular','difference','stale']){assert.equal(intradayTests[key].available,false,key);assert.equal(intradayTests[key].direction,'NEUTRAL',key);}
assert.equal(intradayTests.flat.direction,'NEUTRAL');
console.log('Intraday shadow: 15m/5m entry, 1h countertrend, no 4h veto, immediate stop, sideways and invalid data gates passed');

// Neutral trading signals must not suppress chart-only confirmed swings.
const chartChecks=vm.runInContext(`(()=>{
 const bars=Array.from({length:120},(_,i)=>{const p=4200+Math.sin(i/5)*20;return {openTime:Date.UTC(2026,9,2)+i*300000,open:p,close:p,high:p+1,low:p-1};});
 const models=['5m','15m','1h','4h'].map(tf=>{chartHistory[tf]=bars;$('chartTf').value=tf;$('chartType').value='line';draw();return {valid:!!chartFibonacci(bars,3)?.valid,text:$('chartFib').textContent};});
 const flat=chartFibonacci(bars.map(b=>({...b,open:4200,close:4200,high:4200,low:4200})),0);
 const friday=Date.UTC(2026,9,2,20),monday=Date.UTC(2026,9,5,0);
 const axis=chartTradingAxis([{openTime:friday},{openTime:friday+300000},{openTime:monday},{openTime:monday+300000}],300000);
 return {models,flat,positions:[friday,friday+300000,monday,monday+300000].map(axis.position),breaks:[0,1,2,3].map(axis.startsSegment)};
})()`,env);
for(const m of chartChecks.models){assert(m.valid);assert(m.text.includes('38,2 %'));assert(m.text.includes('161,8 %'));}
assert.equal(chartChecks.flat,null);
assert.deepEqual(Array.from(chartChecks.positions),[0,1/3,2/3,1]);
assert.deepEqual(Array.from(chartChecks.breaks),[true,false,true,false]);
console.log('Chart: confirmed Fibonacci in all four timeframes, no fabricated flat-market levels, compressed and disconnected weekend gaps OK');

// Intraday live policy: 4h context never vetoes, 1h/15m/5m must all confirm.
const intradayPolicy=vm.runInContext(`(()=>{
 const f=dir=>({dir,available:true,fresh:true});
 const base={'1h':f('LONG'),'15m':f('LONG'),'5m':f('LONG'),'4h':f('SHORT')};
 return {aligned:buildMtfHierarchy(base),no4h:buildMtfHierarchy({...base,'4h':undefined}),neutral:buildMtfHierarchy({...base,'15m':f('NEUTRAL')}),opposed:buildMtfHierarchy({...base,'1h':f('SHORT')}),stale:buildMtfHierarchy({...base,'5m':{...f('LONG'),fresh:false}}),
 before:intradaySession(Date.parse('2026-10-05T19:29:00Z')),cutoff:intradaySession(Date.parse('2026-10-05T19:30:00Z')),end:intradaySession(Date.parse('2026-10-05T19:45:00Z')),winter:intradaySession(Date.parse('2026-11-02T20:45:00Z')),weekend:intradaySession(Date.parse('2026-10-04T10:00:00Z'))};
})()`,env);
assert.equal(intradayPolicy.aligned.overall,'LONG');assert.equal(intradayPolicy.no4h.overall,'LONG');
for(const key of ['neutral','opposed','stale'])assert.equal(intradayPolicy[key].overall,'NEUTRAL',key);
assert(intradayPolicy.before.entryAllowed);assert(!intradayPolicy.cutoff.entryAllowed);
assert(!intradayPolicy.weekend.entryAllowed);assert(intradayPolicy.end.closeReminder);assert(intradayPolicy.winter.closeReminder);
console.log('Live intraday: mandatory 1h/15m/5m, optional 4h, stale veto, Zurich daily cutoff and DST OK');

// Historical confirmation must use its own bar clock, independent of wall time.
const clockChecks=vm.runInContext(`(()=>{
 const now=Date.UTC(2026,8,15,12),steps={'5m':300000,'15m':900000,'1h':3600000};
 const bars=Object.fromEntries(Object.entries(steps).map(([tf,step])=>[tf,Array.from({length:240},(_,i)=>{const p=4200+i*.1+Math.sin(i/8)*12;return {openTime:now-(240-i)*step,open:p,high:p+2,low:p-2,close:p,instrument:'XAU/USD',isOpen:false};})]));
 const score=timeframeScore(bars['5m'],'5m',now);
 const original=timeframeScore,observed=[];
 timeframeScore=(rows,tf,asOf)=>{observed.push({asOf,last:rows.at(-1).openTime,tf});return original(rows,tf,asOf);};
 fiveMinuteConfirmation({history:{bars_by_tf:bars}},now);
 timeframeScore=original;
 return {score,observed,flat:rsiS(Array(240).fill(4200)),up:rsiS(Array.from({length:240},(_,i)=>4200+i)),down:rsiS(Array.from({length:240},(_,i)=>4200-i))};
})()`,env);
assert(clockChecks.score.fresh,'Historical bars should be fresh at their own decision time');
assert(clockChecks.observed.length>0);
assert(clockChecks.observed.every(x=>Number.isFinite(x.asOf)&&x.asOf>=x.last),'Each replay frame must have an explicit historical clock');
assert.equal(clockChecks.flat,50);assert.equal(clockChecks.up,100);assert.equal(clockChecks.down,0);
console.log('Historical replay clock and neutral flat RSI OK');

// The narrative must withdraw technical commentary when data or login is unavailable.
vm.runInContext("A.ready=true;window.BobSession={expired:()=>false}",env);
element('quickReason').textContent='5m-Daten veraltet';
element('quickSignal').textContent='ABWARTEN';
vm.runInContext('renderMarketNarrative()',env);
assert(element('bobMarketNarrative').textContent.includes('nicht verlässlich beurteilbar'));
assert(!element('bobMarketNarrative').textContent.includes('Intraday-Tendenz:'));
element('quickReason').textContent='Außerhalb des Einstiegsfensters';
vm.runInContext('renderMarketNarrative()',env);
assert(element('bobMarketNarrative').textContent.includes('Intraday-Tendenz:'));
assert(element('bobMarketNarrative').textContent.includes('Außerhalb des Einstiegsfensters'));
assert(/<details id="bobMarketAnalysis"[^>]*>/.test(html));
assert(!/<details id="bobMarketAnalysis"[^>]*\bopen\b/.test(html));
console.log('Market narrative: collapsed initially, shares current reason, stale data suppresses tendency');
