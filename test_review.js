const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8'),script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map(),storage=new Map();
const noop=()=>{};const canvas=new Proxy({},{get:()=>noop,set:()=>true});
const element=id=>{if(!elements.has(id))elements.set(id,{value:({tf:'15m',n:'200',account:'500',risk:'1',trailAtr:'1.5',minRR:'2',displayCcy:'USD'})[id]||'',textContent:'',innerHTML:'',className:'',parentElement:{className:''},style:{},dataset:{},classList:{add:noop,remove:noop,toggle:noop},addEventListener:noop,setAttribute:noop,appendChild:noop,append:noop,selectedOptions:[{textContent:"15 Minuten"}],getContext:()=>canvas,getBoundingClientRect:()=>({width:800,height:300}),width:800,height:220});return elements.get(id);};
const push={registered:false,serverRegistered:false,activeTrade:false,trade:false,general:false};
const env={console:{log:noop,warn:noop,info:noop,error:noop},document:{getElementById:element,querySelectorAll:()=>[],querySelector:()=>null,visibilityState:'hidden',addEventListener:noop,createTextNode:text=>({textContent:text}),createElement:()=>element('temp')},window:{addEventListener:noop},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},navigator:{},Notification:{permission:'denied'},BobPush:{state:()=>push,set:()=>push,setActiveTrade:()=>push,emit:async()=>false},BobDegiro:{riskModel:()=>({ok:false,reason:'fixture'})},fetch:async()=>{throw Error('offline fixture')},setTimeout:()=>0,clearTimeout:noop,setInterval:()=>0,AbortController,Date,Math,Number,JSON,URL,Blob,Promise};
vm.createContext(env);vm.runInContext(script,env);

(async()=>{
 await new Promise(setImmediate);
 let notices=0;env.notice=()=>notices++;
 vm.runInContext(`
  notifyTrade=async()=>{notice();return true;};
  C=[{openTime:Date.now()-900000}];MTF.byTf={};A={ready:true,at:5,score:80};
  lastPrice=120;liveBundleCache={spots:{xaus:120,is_genuine_xauusd_spot:true,spot_price_as_of:new Date(Date.now()-61000).toISOString()}};
  tradeMgmt={active:true,dir:'LONG',entry:100,stop:90,target:200,initialRisk:10};
  pushState={registered:true,activeTrade:true,trade:true,backgroundEnabled:false};
 `,env);
 await vm.runInContext('manageProfitProtection();suggestStopUpdate()',env);
 assert.equal(vm.runInContext('tradeMgmt.stop',env),90);assert.equal(notices,0);
 vm.runInContext("liveBundleCache.spots.spot_price_as_of=new Date().toISOString();stopModel=()=>({stop:NaN});",env);
 await vm.runInContext('suggestStopUpdate()',env);assert.equal(vm.runInContext('tradeMgmt.stop',env),90);
 vm.runInContext('stopModel=()=>({stop:110})',env);await vm.runInContext('suggestStopUpdate()',env);
 assert.equal(vm.runInContext('tradeMgmt.stop',env),110);assert.equal(notices,1);
 vm.runInContext("liveBundleCache.spots.spot_price_as_of='2026-10-02T10:00:00Z';liveBundleCache.spots.xaus_age_seconds=5;liveBundleCache.fetched_at=Date.now()/1000;C=[];draw()",env);
 // A spot timestamp must never be presented as a missing chart candle's close.
 assert(element('chartLatest').textContent.includes('Schlusszeit: nicht verfügbar'));
 assert(!element('chartLatest').textContent.includes(new Date('2026-10-02T10:00:00Z').toLocaleString('de-CH',{timeZone:'Europe/Zurich'})));
 // A late server reply must not overwrite a newer analysis, and the new request must not be lost.
 const diagnostics=[],pending=[];
 env.fetch=async(url,options)=>{
  if(url.startsWith('/api/diag')){diagnostics.push(JSON.parse(options.body));return {ok:true};}
  assert(url.startsWith('/api/mtf'));
  return new Promise((resolve,reject)=>{pending.push(resolve);options.signal.addEventListener('abort',()=>reject(Error('aborted')));});
 };
 vm.runInContext('timeframeScore=(bars)=>bars[0];renderAnalysisBlocks=()=>{};updateTradeSignal=()=>{};updateResearchPanel=()=>{};loadGeneration=10;',env);
 const fixture=(dir,at,fresh=true)=>({history:{bars_by_tf:Object.fromEntries(['5m','15m','1h','4h'].map(tf=>[tf,[{dir,available:true,fresh,openTime:at}]]))}});
 env.first=fixture('LONG',100);env.second=fixture('SHORT',200);
 const one=vm.runInContext('loadMTF(false,10,first)',env);
 vm.runInContext('loadGeneration=11',env);
 vm.runInContext('lastMtfVerifyAt=0',env);
 const two=vm.runInContext('loadMTF(false,11,second)',env);
 pending.shift()({ok:true,json:async()=>({overall:'LONG',results:{}})});
 await one;await new Promise(setImmediate);assert.equal(pending.length,1);
 pending.shift()({ok:true,json:async()=>({overall:'SHORT',results:Object.fromEntries(Object.entries(env.second.history.bars_by_tf).map(([tf,v])=>[tf,v[0]]))})});
 await two;assert.equal(vm.runInContext('MTF.overall',env),'SHORT');
 const beforeCooldown=pending.length;
 await vm.runInContext('loadMTF(false,11,second)',env);
 assert.equal(pending.length,beforeCooldown);
 assert(diagnostics.some(d=>d.event==='mtf:verification-skipped'&&d.details.reason.includes('zwei Minuten')));
 env.stale=fixture('LONG',100,false);
 vm.runInContext('lastMtfVerifyAt=0',env);
 const stale=vm.runInContext('loadMTF(false,11,stale)',env);
 pending.shift()({ok:true,status:200});await stale;
 assert(!diagnostics.some(d=>d.event==='mtf:server-error'&&d.details.error==='HTTP 200'));
 // An aborted verification releases the single-flight lock.
 let timeout;env.setTimeout=(fn,ms)=>{if(ms===8000)timeout=fn;return 1;};
 vm.runInContext('lastMtfVerifyAt=0',env);
 const slow=vm.runInContext('loadMTF(false,11,second)',env);timeout();await slow;
 assert.equal(vm.runInContext('mtfInFlight',env),null);
 assert(!diagnostics.some(d=>d.event==='mtf:server-error'&&/abort/i.test(d.details.error||'')));
 console.log('Review regressions: stale/invalid stop protection, original chart time, MTF late responses and timeout recovery passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
