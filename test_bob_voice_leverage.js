'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('  function leverageComparisonFromCurrentUi(out){');
const end=html.indexOf('  function mountReadOnlyVoiceButton(note){',start);
assert(start>0&&end>start,'Voice leverage explanation must be present');
const calculate=vm.runInNewContext(html.slice(start,end)+'\nleverageComparisonFromCurrentUi',Object.create(null));
const fixture=(direction,riskText,isinText='',reasonState='ranked')=>({
 querySelector:key=>key==='[data-indicative-recommendations]'?{
  querySelector:key=>key===':scope > b > span'?{textContent:direction}:
   key==='[data-selection-reason]'?{
    textContent:reasonState==='neutral'?'Marktdaten aktuell, aber keine bestätigte LONG- oder SHORT-Richtung.':'Bob hat Kandidaten geprüft.',
    getAttribute:k=>k==='data-selection-reason'?reasonState:null
   }:
   key==='[data-risk-leverage]'?(riskText?{
    textContent:riskText,
    querySelector:k=>k===':scope > strong'?{textContent:riskText.split('Erklärung zum Hebelrisiko')[0]}:null,
    getAttribute:k=>k==='data-risk-isins'?isinText:null
   }:null):null
 }:null
});
const missing=calculate(null);
assert.match(missing,/lädt die Produktauswertung noch/i);
const neutral=calculate(fixture('ABWARTEN','Risiko: höchster Hebel: 50×','', 'neutral'));
assert.match(neutral,/keine bestätigte LONG- oder SHORT-Richtung/i);
assert.doesNotMatch(neutral,/50×/);
const notReady=calculate({
 querySelector:key=>key==='[data-indicative-recommendations]'?{
  querySelector:key=>key===':scope > b > span'?{textContent:'ABWARTEN'}:null
 }:null
});
assert.match(notReady,/Produktprüfung läuft noch/i);
assert.doesNotMatch(notReady,/kein bester Hebel belegt/i);
const stale=calculate(fixture('ABWARTEN','Risiko: höchster Hebel: 50×','', 'market-data')
).replace('Bob hat Kandidaten geprüft.','Marktdaten sind veraltet.');
assert.doesNotMatch(stale,/50×/);
const valid=calculate(fixture('LONG','Risiko: Platz 2 · höchster Hebel: 12.5×'));
assert.match(valid,/12\.5×/);
assert.match(valid,/Gewinne UND Verluste/);
assert.match(valid,/keine Handelsfreigabe/i);
const noRisk=calculate(fixture('SHORT',''));
assert.match(noRisk,/keinen belegten höchsten Hebel/i);
assert.doesNotMatch(noRisk,/SHORT.+\d+×/);
const fromSamsung=factoryWithScreenshotFixture();
function factoryWithScreenshotFixture(){
 return calculate(fixture('SHORT',
  'Risiko: Platz 1 · höchster Hebel: 12.53×Erklärung zum HebelrisikoUnter den angezeigten Empfehlungen',
  'DE000FG14AV8'));
}
assert.match(fromSamsung,/SHORT-Rangfolge: Platz 1/);
assert.match(fromSamsung,/12\.53× · ISIN: DE000FG14AV8/);
assert.doesNotMatch(fromSamsung,/Erklärung zum HebelrisikoUnter/);
assert.doesNotMatch(fromSamsung,/Unter den angezeigten Empfehlungen/);
assert.match(fromSamsung,/höchste unter den angezeigten rechnerischen Empfehlungen/);
const rankedCode=fs.readFileSync('degiro_assistant.js','utf8');
assert.match(rankedCode,/data-risk-isins/);
assert.match(rankedCode,/leverageIsins=ranked\.flatMap/);

console.log('Voice leverage: no invented values, only observed UI risk and no neutral recommendations');
