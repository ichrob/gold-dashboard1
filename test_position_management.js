const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('Bob.html','utf8'),env={};vm.createContext(env);
vm.runInContext(html.slice(html.indexOf('function positionManagementState('),html.indexOf('function trendFollowingSignal(')),env);
const state=env.positionManagementState;
for(const dir of ['LONG','SHORT']){
 const trade={active:true,dir,stop:dir==='LONG'?90:110},trend={available:true,intact:true,direction:dir,phase:'PULLBACK',reason:'Rücksetzer'};
 assert.equal(state(trade,trend,100,true).action,'HOLD');
 assert.equal(state({...trade,active:false},trend,100,true).action,'NONE');
 assert.equal(state(trade,trend,100,false).action,'UNAVAILABLE');
 assert.equal(state(trade,{available:false},100,true).action,'UNAVAILABLE');
 assert.equal(state(trade,{available:false},trade.stop,true).action,'EXIT');
 assert.equal(state(trade,{...trend,intact:false,structureBroken:true},100,true).action,'EXIT');
 assert.equal(state(trade,{...trend,intact:false},100,true).action,'PROTECT');
 assert.equal(state(trade,{...trend,direction:dir==='LONG'?'SHORT':'LONG'},100,true).action,'EXIT');
 assert.equal(trade.dir,dir);assert.equal(trade.stop,dir==='LONG'?90:110);
}
const els={activePositionSignal:{},activePositionReason:{}};
Object.assign(env,{$:id=>els[id],tradeMgmt:{active:true,dir:'SHORT',stop:110},liveBundleCache:{},lastPrice:100,currentSpotUsable:()=>true,sustainedTrendContext:()=>({available:true,intact:true,direction:'SHORT',reason:'Haupttrend intakt'})});
env.renderPositionStatus();assert(els.activePositionSignal.textContent.includes('SHORT · HALTEN'));
env.tradeMgmt.active=false;env.renderPositionStatus();assert(els.activePositionSignal.textContent.includes('KEIN AKTIVER TRADE'));
console.log('position management: passed');
