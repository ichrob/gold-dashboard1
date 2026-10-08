const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8');
const structure=html.slice(html.indexOf('function structureLevels('),html.indexOf('function stopModel('));
const obstacle=html.slice(html.indexOf('function targetObstacle('),html.indexOf('function targetModel('));
const env={};vm.createContext(env);vm.runInContext(structure+obstacle,env);
const bars=Array.from({length:40},()=>({high:105,low:95}));bars[20]={high:112,low:88};
for(const [dir,target,expected] of [['LONG',120,112],['SHORT',80,88]]){
 const check=env.targetObstacle(dir,100,target,10,2,{available:true,bars});
 assert.equal(check.obstacle,expected);assert.equal(check.obstacleRR,1.2);assert.equal(check.entrySuitable,false);
 assert.equal(env.targetObstacle(dir,100,dir==='LONG'?110:90,10,2,{available:true,bars}).obstacle,null);
}
assert.equal(env.targetObstacle('LONG',100,120,10,2,{available:false}).available,false);
console.log('Confirmed LONG/SHORT obstacles, opportunity to first barrier and unavailable data passed.');

const risk=html.slice(html.indexOf('function intradayRiskData('),html.indexOf('function intradayEntryContext('));
const models=html.slice(html.indexOf('function stopModel('),html.indexOf('function displayStop('));
vm.runInContext(models+risk,env);
env.atr=()=>2;
const now=Date.parse('2026-10-08T10:00:00Z'),step=900000;
const oldBars=Array.from({length:50},(_,i)=>({openTime:now-(70-i)*step,isOpen:false,instrument:'XAU/USD',open:100,close:100,high:102,low:98}));
const bundle={history:{bars_by_tf:{'15m':oldBars}},spots:{xaus:100,spot_price_as_of:new Date(now-10*step).toISOString()}};
assert(!env.intradayRiskData(bundle,now).available);
for(const dir of ['LONG','SHORT']){
 const trade={active:true,tradeId:'old',dir,stop:dir==='LONG'?99:101,target:dir==='LONG'?120:80};
 const plan=env.continuedTradePlan(trade,bundle,now);
 assert(plan&&plan.target>0);assert.equal(plan.stop,trade.stop);
 assert.equal(plan.dataAt,now-10*step);assert.equal(plan.analysisBarAt,oldBars.at(-1).openTime);
 assert.equal(plan.computedAt,now);assert.equal(plan.tradeId,'old');
}
assert.equal(env.continuedTradePlan({active:true,dir:'LONG'}, {...bundle,spots:{xaus:100,spot_price_as_of:new Date(now+1).toISOString()}},now),null);
console.log('Stale LONG/SHORT plans keep original clocks, recompute with valid old bars, never loosen stops or accept future evidence');
