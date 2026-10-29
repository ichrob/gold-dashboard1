'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const risk=require('./risk_workspace');
const env={window:{},localStorage:{getItem:()=>null}};
vm.createContext(env);
vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),env);
const api=env.window.BobDegiro,now=Date.parse('2026-10-29T10:00:00Z');
for(const direction of ['LONG','SHORT']){
 const p={isin:'DE000SQ02JQ6',name:'Gold Turbo',isinConfirmed:true,
  productDirection:direction,price:10,leverage:8,ko:direction==='LONG'?3800:4200};
 const signal={ready:true,direction,stage:'VORWARNUNG',spot:4000,atr:2,at:now};
 // riskOnly passes an empty market context; use the actual production selector.
 assert.equal(risk.ranking([p],signal,{},api,now).length,1);
 assert.equal(risk.ranking([p],signal,{atr:99999},api,now).length,1,
  'unrelated main-timeframe ATR must not override the risk signal');
 assert.equal(risk.ranking([p],{...signal,atr:0},{},api,now).length,0);
 assert.equal(risk.ranking([{...p,isinConfirmed:false}],signal,{},api,now).length,0);
 assert.equal(risk.ranking([{...p,name:'Faktor Gold'}],signal,{},api,now).length,0);
 assert.equal(risk.ranking([{...p,ko:4000}],signal,{},api,now).length,0);
 assert.equal(risk.ranking([p],{...signal,direction:'ABWARTEN'},{},api,now).length,0);
}
console.log('Risk ranking: signal ATR reaches actual LONG/SHORT selector; safety exclusions retained.');
