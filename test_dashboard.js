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
console.log('Dashboard runtime: analysis, six blocks, frozen monitor snapshot and test exclusion OK');
