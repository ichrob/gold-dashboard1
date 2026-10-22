'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('  function leverageComparisonFromCurrentUi(out){');
const end=html.indexOf('  function mountReadOnlyVoiceButton(note){',start);
assert(start>0&&end>start,'Voice leverage explanation must be present');
const calculate=vm.runInNewContext(html.slice(start,end)+'\nleverageComparisonFromCurrentUi',Object.create(null));
const fixture=(direction,riskText)=>({
 querySelector:key=>key==='[data-indicative-recommendations]'?{
  querySelector:key=>key===':scope > b > span'?{textContent:direction}:
   key==='[data-risk-leverage]'?(riskText?{textContent:riskText}:null):null
 }:null
});
const missing=calculate(null);
assert.match(missing,/kein bester Hebel belegt/i);
const neutral=calculate(fixture('ABWARTEN','Risiko: höchster Hebel: 50×'));
assert.match(neutral,/kein bester Hebel belegt/i);
assert.doesNotMatch(neutral,/50×/);
const valid=calculate(fixture('LONG','Risiko: Platz 2 · höchster Hebel: 12.5×'));
assert.match(valid,/12\.5×/);
assert.match(valid,/Gewinne UND Verluste/);
assert.match(valid,/keine Handelsfreigabe/i);
const noRisk=calculate(fixture('SHORT',''));
assert.match(noRisk,/keinen belegten höchsten Hebel/i);
assert.doesNotMatch(noRisk,/SHORT.+\d+×/);
console.log('Voice leverage: no invented values, only observed UI risk and no neutral recommendations');
