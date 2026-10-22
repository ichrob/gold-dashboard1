'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('Bob.html','utf8');
const start=html.indexOf('  function longComparisonFromCurrentUi(out){');
const end=html.indexOf('  function renderRequestedLongComparison(){',start);
assert(start>0&&end>start);
assert(html.includes("['products-long','products-leverage'].includes(key)"), 'Both read-only product subviews must navigate into the existing products panel');
assert(html.includes("renderRequestedLongComparison()"));
const factory=vm.runInNewContext(html.slice(start,end)+'\nlongComparisonFromCurrentUi',Object.create(null));
const fake=(direction,descriptions)=>({
  querySelector:q=>q==='[data-indicative-recommendations]'?{
    querySelector:q=>q===':scope > b > span'?{textContent:direction}:null,
    children:descriptions.map(textContent=>({tagName:'DIV',textContent}))
  }:null
});
const noData=factory(null);
assert.match(noData.status,/noch geladen|nicht verfügbar/);
assert.equal(noData.rows.length,0);
const caution=factory(fake('SHORT',['1. DE000FG14AV8 · SHORT · KO-Abstand 3.15%']));
assert.match(caution.status,/keine LONG-Rangfolge/);
assert.equal(caution.direction,'SHORT');
const long=factory(fake('LONG',[
 'Risiko: Platz 1 · höchster Hebel: 20×',
 '1. DE000FG14AV8 · LONG · KO-Pufferwert 81/100 · KO-Abstand 5.15%',
 '2. BE000FG4JXV7 · LONG · KO-Pufferwert 76/100 · KO-Abstand 6.10%',
 '3. DE000FG14AV8 · LONG · KO-Pufferwert 74/100 · KO-Abstand 6.44%',
 '4. DE000FG14AV8 · LONG · KO-Abstand 5.00%'
]));
assert.equal(long.rows.length,3);
assert.match(long.status,/bestehender rechnerischer Rangfolge/);
assert.match(long.rows[0],/KO-Abstand 5.15%/);
assert(!long.rows.some(x=>x.includes('4. ')));
assert(!long.rows.some(x=>x.includes('höchster Hebel')));
assert(!html.includes("Neue LONG-Empfehlung bestätigt"));
console.log('Read-only product voice explanations use existing rendered LONG rows; SHORT and missing data are not mislabeled.');
