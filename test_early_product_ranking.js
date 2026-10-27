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
// Reproduce the reported case: early LONG while main technical context is SHORT/NEUTRAL.
const p={isin:'DE000FG14AV8',name:'Gold Turbo Long',isinConfirmed:true,productDirection:'LONG',price:7.5,leverage:8,ko:3950};
const ctx={now,spotFresh:true,spot:4140,atr:10,direction:'LONG',trend:'SHORT',trend2:'SHORT',mtf:'SHORT',rsi:20,hist:-2,adx:28,momentum:-1};
assert.equal(b.unapprovedComparisonRanking([p],ctx).length,0,'main setup still required for regular shortlist');
assert.equal(b.earlyWarningRanking([p],ctx).length,1,'early watchlist can precede main confirmation');
for(const bad of [{...p,ko:4130},{...p,isinConfirmed:false},{...p,price:null},{...p,productDirection:'SHORT'},{...p,name:'FACTOR Gold'}])assert.equal(b.earlyWarningRanking([bad],ctx).length,0,'product safety gates remain');
const before=JSON.stringify(ctx);b.earlyWarningRanking([p],ctx);assert.equal(JSON.stringify(ctx),before);
b.setEarlySnapshot({at:now,products:[p],context:ctx});
const panel={hidden:true,textContent:''};env.document={getElementById:id=>id==='dgEarlyProductRanking'?panel:null};
b.renderEarlyProductPanel({available:true,state:'active',direction:'LONG',expiresAt:now+60000});
assert.equal(panel.hidden,false);assert.match(panel.textContent,/1\. DE000FG14AV8/);assert.match(panel.textContent,/technische Bestätigung fehlt/);
b.renderEarlyProductPanel({available:true,state:'expired',direction:'NEUTRAL'});assert.equal(panel.hidden,true);assert.equal(panel.textContent,'');
b.setEarlySnapshot({at:now,products:[{...p,ko:4130}],context:ctx});
assert.match(b.earlyProductRankingText({available:true,state:'active',direction:'LONG'},now),/KO-Gefahr/);
const html=fs.readFileSync('Bob.html','utf8');assert(html.includes('renderEarlyProductPanel(q)'));
assert(src.includes('id="dgEarlyProductRanking"'));assert(src.indexOf('id="dgEarlyProductRanking"')<src.indexOf('id="dgTop3Out"'));
console.log('Early warning with neutral/opposite main context: Products panel visible, main gates unchanged, KO exclusions explained, expiry clears panel');
