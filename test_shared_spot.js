const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('Bob.html','utf8'),script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements=new Map(),storage=new Map();
const noop=()=>{};const canvas=new Proxy({},{get:()=>noop,set:()=>true});
const element=id=>{if(!elements.has(id))elements.set(id,{value:({tf:'15m',n:'200',account:'500',risk:'1',trailAtr:'1.5',minRR:'2',displayCcy:'USD'})[id]||'',textContent:'',innerHTML:'',className:'',parentElement:{className:''},style:{},dataset:{},classList:{add:noop,remove:noop,toggle:noop},addEventListener:noop,setAttribute:noop,appendChild:noop,getContext:()=>canvas,width:800,height:220});return elements.get(id);};
const push={registered:false,serverRegistered:false,activeTrade:false,trade:false,general:false};
const env={console:{log:noop,warn:noop,info:noop,error:noop},document:{getElementById:element,querySelectorAll:()=>[],querySelector:()=>null,visibilityState:'hidden',addEventListener:noop,createElement:()=>element('temp')},window:{addEventListener:noop},localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},navigator:{},Notification:{permission:'denied'},BobPush:{state:()=>push,set:()=>push,setActiveTrade:()=>push,emit:async()=>false},BobDegiro:{riskModel:()=>({ok:false,reason:'fixture'})},fetch:async()=>{throw Error('offline fixture')},setTimeout:()=>0,clearTimeout:noop,setInterval:()=>0,AbortController,Date,Math,Number,JSON,URL,Blob,Promise};
vm.createContext(env);vm.runInContext(script,env);

(async()=>{
 await new Promise(setImmediate);
 let calls=0,resolve;
 const at=new Date().toISOString();
 const bundle={spots:{xaus:4141.8,spot_price_as_of:at,is_genuine_xauusd_spot:true,xaus_is_spot:true},history:{bars_by_tf:{'5m':[{}],'1h':[{}]}}};
 env.fetch=async url=>{assert.equal(url,'/api/live');calls++;return new Promise(r=>resolve=()=>r({ok:true,json:async()=>bundle}));};
 const one=vm.runInContext('fetchLiveBundle(true)',env),two=vm.runInContext('fetchLiveBundle(true)',env);
 assert.equal(calls,1);resolve();const [a,b]=await Promise.all([one,two]);assert.strictEqual(a,b);
 assert.equal(a.spots.spot_price_as_of,at);
 // The card, overview and analysis read the exact same snapshot, even without history.
 let painted;
 env.window.BobGoldCards={spot:b=>painted=b.spots};
 bundle.history.bars_by_tf={};
 await vm.runInContext('loadData()',env);
 assert.equal(painted.xaus,vm.runInContext('lastPrice',env));
 assert.equal(painted.spot_price_as_of,at);
 assert.equal(element('quickPrice').textContent,'4141.80 USD');
 env.fetch=async()=>{throw Error('offline');};
 const failed=await vm.runInContext('fetchLiveBundle(true)',env);
 assert.equal(failed.spots.xaus,4141.8);assert.equal(failed.spots.spot_price_as_of,at);
 assert(failed.spots.spot_error);
 assert(vm.runInContext('analysisAgeWarnings().some(x=>x.startsWith("Goldpreis:"))',env));
 env.fetch=async()=>({ok:true,json:async()=>({...bundle,spots:{...bundle.spots,xaus:9999}})});
 const conflict=await vm.runInContext('fetchLiveBundle(true)',env);
 assert.equal(conflict.spots.xaus,4141.8);assert(conflict.spots.spot_error);
 console.log('Shared spot: concurrent fetch, analysis/display identity, outage and conflict rejection passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
