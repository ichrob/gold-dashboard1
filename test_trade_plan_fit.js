const fs=require('fs'),vm=require('vm'),assert=require('assert');
const window={};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),{window});const b=window.BobExitEstimate;
const p={isin:'DE000FG4JXV7',currency:'CHF',direction:'SHORT',simpleSpotTurbo:true,referenceConfirmed:true,bid:20,goldReference:4200,fxReference:.9,fxScenario:.9,ratio:.1,strike:4460,ko:4460,entry:21,quantity:10,planGold:4200,targetGold:4150,stopGold:4230,source:'DEGIRO-Screenshot',referenceAt:'02/10/2026 15:04',lossBudget:40,minKoBuffer:100,minPlanRR:.9};
const original=JSON.stringify(p),x=b.assessPlan(p);
assert(x.available&&x.fits);assert(Math.abs(x.loss-37)<1e-9);assert.equal(x.gain,35);assert.equal(x.buffer,230);assert.equal(x.maxQuantity,10);assert.equal(x.currency,'CHF');assert(!x.tradeable&&!x.automaticOrder);
assert.equal(JSON.stringify(p),original);
for(const changes of [{lossBudget:36},{minKoBuffer:240},{minPlanRR:2}]){const r=b.assessPlan({...p,...changes});assert(r.available&&!r.fits);}
for(const changes of [{lossBudget:0},{lossBudget:-1},{minKoBuffer:-1},{minPlanRR:0},{entry:17},{quantity:1.5},{referenceConfirmed:false},{currency:'USD'},{stopGold:4460},{targetGold:4210}])assert(!b.assessPlan({...p,...changes}).available,JSON.stringify(changes));
const long=b.assessPlan({...p,direction:'LONG',strike:4000,ko:4000,targetGold:4250,stopGold:4170});assert(long.fits);assert.equal(long.buffer,170);assert(Math.abs(long.loss-x.loss)<1e-9);
const html=b.renderPlan(x);assert(html.includes('CHF'));assert(html.includes('keine garantierte Verlustgrenze'));assert(!html.includes('EUR'));
assert(!b.renderPlan({...x,source:'<script>attack</script>'}).includes('<script>'));
assert(fs.readFileSync('degiro_assistant.js','utf8').includes(fs.readFileSync('exit_estimate.js','utf8').trim()),'served bundle must contain the current planning module');
// Exercise the actual mount handlers: draft writes cannot alter purchase data or activate trades.
const elements=new Map(),handlers={},storage=new Map();let box;
function el(){return {value:'',textContent:'',innerHTML:'',events:{},addEventListener(k,fn){this.events[k]=fn;}};}
const doc={createElement(){box=el();box.querySelector=s=>{if(!elements.has(s))elements.set(s,el());return elements.get(s);};box.contains=t=>t===box;return box;}};
const panel={querySelector:s=>s==='h3'?{after(){}}:el(),addEventListener(k,f){handlers[k]=f;}};
const w={BobDegiro:{validIsin:()=>true}};
const context={window:w,document:undefined,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)}};
vm.createContext(context);vm.runInContext(fs.readFileSync('exit_estimate.js','utf8'),context);context.document=doc;
let main={...p};w.BobExitEstimate.mountPlan(panel,()=>({...main}));
const input=k=>elements.get('[data-plan="'+k+'"]');
elements.get('[data-plan-copy]').events.click();input('lossBudget').value='40';input('minPlanRR').value='.9';
elements.get('[data-plan-evaluate]').events.click();assert(elements.get('[data-plan-result]').innerHTML.includes('Passt rechnerisch'));
assert.equal(JSON.stringify(main),original);assert([...storage.keys()].every(k=>k.startsWith('bobTradePlanDraftV1:')));
main={...main,isin:'DE000FG8NHQ3'};handlers.change({target:{}});assert.equal(input('entry').value,'');assert.equal(input('lossBudget').value,'');
main={...p};handlers.change({target:{}});assert.equal(input('entry').value,21);assert.equal(input('lossBudget').value,'40');
console.log('Trade planning: CHF/EUR scenarios, KO/stop/budget/CRV checks, isolated drafts and identity switching passed');
