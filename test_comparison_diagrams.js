const assert=require('assert/strict'),fs=require('fs'),vm=require('vm'),api=require('./comparison_diagrams');
const at=1800000000000;
const result={complete:true,chosenIsin:'a',chosenPct:-2,alternativeIsin:'b',returns:{b:{grossPct:1}}};
const study={comparisons:[{at:at+7200000,currency:'EUR',outcome:{complete:false,chosenPct:99}},{at,currency:'EUR',outcome:result},{at,currency:'CHF',outcome:{...result,chosenPct:3}}],lifecycle:{comparisons:[{slot:at,currency:'CHF',...result}]},states:{EUR:{phase:'validation',progress:{second:{samples:12,days:3,coverage:1,scenarios:{stress:{mean:{baseline:-.2,candidate:.1},improvementPct:.3}}}}}},policy:{variants:{EUR:'baseline'}}};
const before=JSON.stringify(study),rows=api.series(study,'EUR','horizon');
assert.equal(rows.length,2);assert.equal(rows[0].chosen,-2);assert.equal(rows[1].chosen,null);assert.equal(rows[1].alternative,null);
assert.equal(api.series(study,'CHF','horizon')[0].chosen,3);assert.equal(api.series(study,'CHF','exit')[0].chosen,-2);
assert.equal(api.series(study,'EUR','exit').length,0);
assert(api.bounds(rows).low<-2);assert(api.bounds(rows).high>1);
assert.equal(api.segments([rows[0],rows[1],{...rows[0],at:at+14400000}],'chosen',x=>x,x=>x).length,2);
assert.equal(api.segments([rows[0],{...rows[0],at:at+14400000}],'chosen',x=>x,x=>x).length,2,'An absent scheduled group must not be bridged');
assert.equal(api.proofs(study,'EUR')[0].active,false);assert.equal(api.proofs(study,'EUR')[0].phase,'validation');assert.equal(JSON.stringify(study),before);
// Exercise actual SVG/DOM rendering, empty state, later data, stale state and controls.
class El{constructor(tag){this.tag=tag;this.children=[];this.style={};this.events={};this.attrs={};this.textContent='';}append(...els){this.children.push(...els);}replaceChildren(...els){this.children=els;}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,f){this.events[k]=f;}}
const doc={createElement:t=>new El(t),createElementNS:(_,t)=>new El(t),dispatchEvent:()=>{}};
const window={document:doc};vm.runInNewContext(fs.readFileSync('comparison_diagrams.js','utf8'),{window,setInterval:()=>{},Event:class{},Date,console});
const panel=new El('section');window.BobDiagrams.mount(panel);
const all=()=>{const out=[];function walk(e){out.push(e);e.children.forEach(walk);}walk(panel);return out;};
assert(all().some(e=>e.textContent.includes('Noch keine vollständigen')));
window.BobDiagrams.unavailable();assert(all().some(e=>e.textContent.includes('derzeit nicht verfügbar')));
window.BobDiagrams.update(study);assert.equal(all().filter(e=>e.tag==='svg').length,3);
assert(all().some(e=>e.textContent.includes('nicht übernommen')));
const circle=all().find(e=>e.tag==='circle');circle.events.click();assert(all().some(e=>e.textContent.includes('Damals bevorzugt: a')));
window.BobDiagrams.unavailable();assert(all().some(e=>e.textContent.includes('Datenstand veraltet')));
const selectors=all().filter(e=>e.tag==='select');selectors[0].value='CHF';selectors[0].events.change();selectors[1].value='exit';selectors[1].events.change();assert.equal(all().filter(e=>e.tag==='svg').length,1);
console.log('Comparison diagrams: currency/horizon isolation, no missing-value winners, gaps, frozen evidence, actual SVG rendering and stale/empty states pass');

// Independent transforms: missing prices never become zero P/L or hits.
const cr=api.capitalRows({control:{initialCapital:100},daily:[
 {day:'2026-10-14',valuationKnown:true,capital:110,initialCapital:100,observedMaxDrawdownPct:2},
 {day:'2026-10-15',valuationKnown:false,capital:null,initialCapital:100},
 {day:'2026-10-16',valuationKnown:true,capital:99,initialCapital:100}]});
assert.equal(cr[0].profit,10);assert.equal(cr[1].profit,null);assert(Math.abs(cr[2].drawdown+10)<1e-8);
assert.equal(api.signalRows({'15':{evaluated:4,favorable:3,directionalSumPct:-2}})[0].mean,-.5);
assert.equal(api.signalRows({})[0].hit,null);
const stop={currency:'EUR',slot:at,chosenIsin:'a',stopComparison:{complete:true,bobReturns:{a:{grossPct:-1,peakPct:3}},fixedReturns:{a:{grossPct:2}}}};
assert.equal(api.stopRows({lifecycle:{comparisons:[stop]}},'EUR')[0].giveback,3);
assert.equal(api.stopRows({lifecycle:{comparisons:[{...stop,stopComparison:{...stop.stopComparison,complete:false}}]}},'EUR')[0].bob,null);
window.BobDiagrams.portfolios({realOrders:false,accounts:[{profile:'balanced',title:'Test',control:{initialCapital:100},daily:[{day:'2026-10-14',valuationKnown:true,capital:110,initialCapital:100}]}]});
assert(all().some(e=>e.textContent.includes('Rendite seit Kontostart')));
window.BobDiagrams.portfoliosUnavailable();assert(all().some(e=>e.textContent.includes('Kontodaten veraltet')));
window.BobDiagrams.update({...study,lifecycle:{comparisons:[stop]}},{precisionLearning:{states:[{currency:'CHF',isin:'x',source:'issuer',chartHistory:[{at,raw:10,original:11,corrected:10.2}]}]},metrics:{'15':{evaluated:4,favorable:3,directionalSumPct:-2}}});
assert(all().some(e=>e.textContent.includes('Originalkurs')));assert(all().some(e=>e.textContent.includes('Trefferquote')));
