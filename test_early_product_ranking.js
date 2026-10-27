'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let src=fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={setEarlySnapshot:s=>earlyProductSnapshot=s,');
const env={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};vm.createContext(env);vm.runInContext(src,env);
env.window.BobProductEvidence=require('./product_evidence_contract');
const b=env.window.BobDegiro,now=Date.now();
for(const direction of ['LONG','SHORT']){
 const products=[{isin:'DE000FG14AV8',name:'Gold Turbo',isinConfirmed:true,productDirection:direction,price:7.5,leverage:8,ko:direction==='LONG'?3950:4350}];
 const context={spotFresh:true,spot:4140,atr:10,trend:direction,trend2:direction,mtf:direction,rsi:direction==='LONG'?64:36,hist:direction==='LONG'?2:-2,adx:28,momentum:direction==='LONG'?1:-1};
 b.setEarlySnapshot({at:now,products,context});
 const q={available:true,state:'active',direction};
 assert.match(b.earlyProductRankingText(q,now),/1\. DE000FG14AV8/);
 assert.match(b.earlyProductRankingText(q,now),/keine Handelsfreigabe/);
 assert.match(b.earlyProductRankingText({...q,state:'watch'},now),/1\. DE000FG14AV8/);
 assert.doesNotMatch(b.earlyProductRankingText(q,now+60001),/DE000/);
 for(const state of ['expired','withdrawn','paused','unavailable'])assert.equal(b.earlyProductRankingText({...q,state},now),'');
 assert.equal(b.earlyProductRankingText({...q,available:false},now),'');
 b.setEarlySnapshot({at:now,products,context:{...context,spotFresh:false}});
 assert.doesNotMatch(b.earlyProductRankingText(q,now),/1\. DE000/);
}
console.log('Early product ranking: LONG/SHORT, watch, expiry, stale data and no approval passed');
