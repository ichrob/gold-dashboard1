'use strict';
// Unapproved products may be compared, never promoted into the approved Top 3.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('degiro_assistant.js','utf8');
const context={window:{},localStorage:{getItem:()=>null,setItem:()=>{}}};
vm.createContext(context);vm.runInContext(src,context,{timeout:4000});
context.window.BobProductEvidence=require('./product_evidence_contract');
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
assert.doesNotMatch(opposite,/DE000FG4JXV7/,
 'Opposite-direction products must not appear in the active market ranking');
const stale=b.renderContinuingAnalysis([p],{...market,spotFresh:false});
assert.doesNotMatch(stale,/Platz 1/);
assert.match(stale,/ABWARTEN/,
 'Stale market data suppresses the entire ranking');
console.log('Unified research ranking keeps incomplete products visible and approval independent');

// Regression: neutral market must not expose ranking entries.
assert.doesNotMatch(b.renderContinuingAnalysis([p],{...market,direction:'NEUTRAL'}),/data-unified-ranking-isin/);
assert.match(b.renderContinuingAnalysis([p],{...market,direction:'NEUTRAL'}),/ABWARTEN/);
assert.doesNotMatch(b.renderContinuingAnalysis([p],{...market,spotFresh:false}),/data-unified-ranking-isin/);
assert.doesNotMatch(b.renderContinuingAnalysis([p],{...market,direction:'SHORT'}),/data-unified-ranking-isin="DE000FG14AV8"/);

const calcProduct={...p,priceCalculated:true,calculationEvidence:{price:{method:'issuer formula',source:'issuer',at:new Date(now-10000).toISOString()}}};
const calcMarkup=b.renderContinuingAnalysis([calcProduct],market);
assert.doesNotMatch(calcMarkup,/RECHNERISCH FREIGEGEBEN/,'Free-form calculation labels cannot replace actual product evidence');
assert.match(calcMarkup,/NICHT FREIGEGEBEN/);
const noProofMarkup=b.renderContinuingAnalysis([{...calcProduct,calculationEvidence:{}}],market);
assert.doesNotMatch(noProofMarkup,/RECHNERISCH FREIGEGEBEN/);

for(const bad of [
 {...calcProduct,isin:'DE000FG309G0'},
 {...calcProduct,isinConfirmed:false},
 {...calcProduct,quote:{isin:p.isin,productVerified:true,metadata:{status:0}}},
 {...calcProduct,underlyingType:'FUTURE'},
 {...calcProduct,price:Infinity},
 {...calcProduct,ko:4139}
])assert.doesNotMatch(b.renderContinuingAnalysis([bad],market),/RECHNERISCH FREIGEGEBEN/);
context.window.BobAnalysisAge=()=>['Quelle veraltet'];
assert.doesNotMatch(b.renderContinuingAnalysis([calcProduct],market),/RECHNERISCH FREIGEGEBEN/);
