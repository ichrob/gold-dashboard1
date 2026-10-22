'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const dg=fs.readFileSync('degiro_assistant.js','utf8');
const html=fs.readFileSync('Bob.html','utf8');
const st=dg.indexOf('function productSelectionExplanation(');
const en=dg.indexOf('function renderContinuingAnalysis(',st);
assert(st>0&&en>st,'selection reason classification must be present');
const fn=vm.runInNewContext(dg.slice(st,en)+'\nproductSelectionExplanation',
 {validIsin:isin=>isin==='DE000FG14AV8',
  productTermsStatus:p=>({complete:p.complete===true}),Date});
const withDirection=(dir='LONG',spotFresh=true)=>({direction:dir,spotFresh,now:Date.UTC(2026,9,22,20)});
const product={isin:'DE000FG14AV8',isinConfirmed:true,complete:true};
function classified(products,context,ranked=[],warnings=[]){
 return fn(products,context,ranked,warnings);
}
let r=classified([product],withDirection('ABWARTEN',false),[],[]);
assert.equal(r.state,'market-data','Missing/stale feed must beat apparent neutral state');
assert.match(r.text,/Marktdaten fehlen, sind veraltet/);
r=classified([product],withDirection('SHORT'),[],['Marktzeitstempel veraltet']);
assert.equal(r.state,'market-data','Warnings must override apparent directional signal');
assert.match(r.text,/Marktzeitstempel veraltet/);
r=classified([product],withDirection('ABWARTEN'));
assert.equal(r.state,'neutral');
assert.match(r.text,/keine bestätigte LONG- oder SHORT-Richtung/);
r=classified([],withDirection());
assert.equal(r.state,'no-products');
assert.match(r.text,/keine erfassten Gold-Hebelprodukte/);
r=classified([{...product,complete:false}],withDirection());
assert.equal(r.state,'product-data');
assert.match(r.text,/Pflichtdaten oder Produktnachweise/);
r=classified([product],withDirection());
assert.equal(r.state,'no-match');
assert.match(r.text,/keines sämtliche Auswahlkriterien/);
r=classified([product],withDirection(),[{p:product}]);
assert.equal(r.state,'ranked');
assert.match(r.text,/1 rechnerisch passenden LONG-Kandidaten/);
// A stale feed takes precedence even when a historical model ranking exists.
r=classified([product],withDirection('LONG',false),[{p:product}]);
assert.equal(r.state,'market-data');
assert.match(dg,/data-selection-reason/);
assert.match(html,/reasonState&&reasonState!=='ranked'&&reasonText/);
assert.match(html,/v=20261022-selection-reasons/);
const vStart=html.indexOf('  function longComparisonFromCurrentUi(out){');
const vEnd=html.indexOf('  function mountReadOnlyVoiceButton(',vStart);
assert(vStart>0&&vEnd>vStart);
const replies=vm.runInNewContext(html.slice(vStart,vEnd)+
 '\n({longComparisonFromCurrentUi,leverageComparisonFromCurrentUi})',{});
function section({direction='ABWARTEN',reason='market-data',text='Marktdaten fehlen oder sind veraltet.',risk=null}={}){
 return {querySelector:key=>{
  if(key===':scope > b > span')return {textContent:direction};
  if(key==='[data-selection-reason]')return {
    textContent:text,getAttribute:k=>k==='data-selection-reason'?reason:null};
  if(key==='[data-risk-leverage]')return risk;
  return null;
 },children:[]};
}
function out(sectionObj){return {querySelector:key=>key==='[data-indicative-recommendations]'?sectionObj:null};}
const late=out(section());
const lv=replies.leverageComparisonFromCurrentUi(late);
assert.match(lv,/Marktdaten fehlen oder sind veraltet/);
assert.match(lv,/nicht nennen/);
assert.doesNotMatch(lv,/Bobs vorhandene (LONG|SHORT)-Rangfolge/);
const long=replies.longComparisonFromCurrentUi(late);
assert.match(long.status,/Marktdaten fehlen oder sind veraltet/);
assert.equal(long.rows.length,0);
const verifiedNoMatch=out(section({direction:'LONG',reason:'no-match',
 text:'Keines der geprüften Produkte erfüllt sämtliche Auswahlkriterien.'}));
assert.match(replies.leverageComparisonFromCurrentUi(verifiedNoMatch),/Keines der geprüften Produkte/);
assert.match(replies.longComparisonFromCurrentUi(verifiedNoMatch).status,/sämtliche Auswahlkriterien/);
const questionNeutral=out(section({direction:'ABWARTEN',reason:'neutral',
 text:'Keine bestätigte LONG- oder SHORT-Richtung.'}));
assert.match(replies.leverageComparisonFromCurrentUi(questionNeutral),/Keine bestätigte/);
const ranked=out(section({direction:'SHORT',reason:'ranked',text:'Rechnerische Empfehlung',
 risk:{textContent:'Platz 1 · höchster Hebel: 12.53×',
 querySelector:()=>({textContent:'Platz 1 · höchster Hebel: 12.53×'}),
 getAttribute:k=>k==='data-risk-isins'?'DE000FG14AV8':null}}));
assert.match(replies.leverageComparisonFromCurrentUi(ranked),/12\.53× · ISIN: DE000FG14AV8/);
console.log('Selection reasons: no market-data false neutrality, evidence gap vs no-match, grounded voice responses.');
