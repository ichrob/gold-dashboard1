'use strict';
// Unapproved products may be compared, never promoted into the approved Top 3.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('degiro_assistant.js','utf8');
const context={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};
vm.createContext(context);vm.runInContext(src,context,{timeout:4000});
const b=context.window.BobDegiro;
const now=Date.parse('2026-10-26T13:51:00Z');
const market={now,direction:'LONG',spotFresh:true,spot:4140,atr:10,
 trend:'LONG',trend2:'LONG',mtf:'LONG',rsi:64,hist:2,adx:28,momentum:1};
const p={isin:'DE000FG14AV8',name:'Gold Turbo Long',isinConfirmed:true,
 productDirection:'LONG',price:7.5,leverage:8,ko:3950};
const q={...p,isin:'DE000FG4JXV7',ko:4000};
assert.equal(b.finalProductStatus(p,now).complete,false);
const preliminary=b.unapprovedComparisonRanking([q,p,p],market);
assert.deepEqual(Array.from(preliminary,x=>x.p.isin),[p.isin,q.isin],
 'Partial research candidates sort by KO buffer and dedupe by ISIN');
assert(preliminary.every(x=>x.proofComplete===false&&x.missing.length>0));
assert.equal(b.selectionWorkflow([p],market,{}).approvedCount,0,
 'Preview never changes formal approval');
assert.equal(b.selectionWorkflow([p],market,{}).groups.length,0);
const markup=b.renderContinuingAnalysis([p,{...p,isin:'DE000FG309G0',price:null}],market);
assert.match(markup,/data-unified-product-ranking/);
assert.match(markup,/data-indicative-recommendations/);
assert.match(markup,/data-selection-reason=/);
assert.match(markup,/data-unified-ranking-isin/);
assert.match(markup,/NICHT FREIGEGEBEN/);
assert.match(markup,/Ohne Rang/);
assert.doesNotMatch(markup,/data-unapproved-comparison/);
assert.doesNotMatch(markup,/data-product-trade=/);
for(const [why,bad] of [
 ['missing price',{...p,price:null}],['missing leverage',{...p,leverage:null}],
 ['missing KO',{...p,ko:null}],['unconfirmed identity',{...p,isinConfirmed:false}],
 ['opposite direction',{...p,productDirection:'SHORT'}],
 ['KO crossed',{...p,ko:4200}],['factor product',{...p,name:'Faktor Gold Long'}],
 ['known gold future',{...p,isin:'DE000FG309G0'}],
 ['mismatched quote',{...p,quote:{isin:'DE000FG4JXV7'}}],
 ['mismatched snapshot',{...p,snapshot:{isin:'DE000FG4JXV7'}}],
 ['terminated issuer',{...p,quote:{isin:p.isin,productVerified:true,metadata:{status:0}}}]
])assert.equal(b.unapprovedComparisonRanking([bad],market).length,0,why);
assert.equal(b.unapprovedComparisonRanking([p],{...market,spotFresh:false}).length,0);
assert.equal(b.unapprovedComparisonRanking([p],{...market,direction:'NEUTRAL'}).length,0);
assert.equal(b.unapprovedComparisonRanking([p],{...market,atr:null}).length,0);
const opposite=b.renderContinuingAnalysis([p,{...q,productDirection:'SHORT'}],market);
assert.match(opposite,/Platz 1 · DE000FG14AV8/);
assert.match(opposite,/Ohne Rang · DE000FG4JXV7/,
 'Products against the current market direction stay visible but do not receive a rank');
const stale=b.renderContinuingAnalysis([p],{...market,spotFresh:false});
assert.doesNotMatch(stale,/Platz 1/);
assert.match(stale,/data-selection-reason="market-data"/,
 'Stale market data keeps all products visible but suppresses a current rank');
console.log('Unified research ranking keeps incomplete products visible and approval independent');
