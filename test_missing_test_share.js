const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
const api=require('./comparison_diagrams');
const at=1800000000000;
const study={comparisons:[
 {at,slot:at,currency:'EUR',missing:['DETEST'],candidates:[{isin:'DETEST',quote:{source:'issuer\ntext',at,askAt:at,bid:999},secret:'never-export'}],outcome:{complete:false,status:'incomplete',missing:['DETEST']}},
 {at:at+1,currency:'EUR',missing:[],outcome:null},
 {at:at+2,currency:'EUR',missing:['old-error'],outcome:{complete:true}},
],lifecycle:{comparisons:[{slot:at,currency:'CHF',complete:false,status:'incomplete',missing:['CHTEST'],details:{CHTEST:{events:[{kind:'comparison-unavailable',reason:'Quellenzeit fehlt'}]}},stopComparison:{complete:false,missing:['CHTEST'],pending:[]}}]}};
const audit={metrics:{'15':{missing:5,missingReasons:{pending:2,missingFollowup:2,invalidStart:1}},'60':{missing:3,missingReasons:{pending:3}}},account:'never-export'};
const rows=api.missingTests(study,audit);assert.equal(rows.length,5);assert.equal(rows.reduce((n,r)=>n+r.count,0),6);
assert(!rows.some(r=>r.at===at+1));assert(!rows.some(r=>r.reasons.includes('old-error')));
assert.equal(api.escalatedTests({available:true,items:[{status:'trying',attempts:0}]}).length,0);
assert.equal(api.escalatedTests({available:false,items:[{status:'escalated',attempts:1,history:[{}]}]}).length,0);
const text=api.missingTestText(rows,at,true);assert(text.includes('Löse die unten aufgeführten Probleme selbstständig'));assert(text.includes('veraltet'));assert(text.includes('Quellenzeit fehlt'));assert(text.includes('DETEST'));
assert(!text.includes('never-export'));assert(!text.includes('999'));assert(!text.includes('issuer\ntext'));
assert.equal(api.missingTests(null,null).length,0);
assert.equal(api.missingTests({comparisons:[study.comparisons[0],study.comparisons[0]]},null).length,1);
assert(api.missingTestText([],at,false).includes('kein Nachweis allgemeiner Fehlerfreiheit'));
class El{constructor(tag){this.tag=tag;this.children=[];this.style={};this.events={};this.attrs={};this.textContent='';}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,f){this.events[k]=f;}}
const doc={createElement:t=>new El(t),createElementNS:(_,t)=>new El(t)},shared=[];
const window={document:doc,navigator:{share:async data=>shared.push(data)}};
vm.runInNewContext(fs.readFileSync('comparison_diagrams.js','utf8'),{window,Date,Event:class{},setInterval:()=>{}});
const panel=new El('section');window.BobDiagrams.mount(panel);window.BobDiagrams.update(study,audit);
const repair={available:true,workerCheckedAt:at,counts:{trying:1,escalated:1},items:[{id:'title:EUR:'+at,type:'Titelvergleich',currency:'EUR',at,status:'escalated',attempts:1,reasons:['DETEST'],reason:'Originalnachweis fehlt',history:[{at,action:'Archiv prüfen',result:'Nicht rekonstruierbar'}]}]};
window.BobDiagrams.repairs(repair);
const all=()=>{const list=[];function walk(e){list.push(e);e.children.forEach(walk);}walk(panel);return list;};
assert.equal(shared.length,0,'Rendering never transmits the report');
assert(!all().some(e=>e.tag==='button'&&e.textContent.includes('selbstständig lösen')));
assert(all().some(e=>e.textContent.includes('KI-Reparaturwächter automatisch geprüft')));
window.BobDiagrams.unavailable();assert.equal(shared.length,0);
console.log('Historical missing-test details retained without manual sharing action');
