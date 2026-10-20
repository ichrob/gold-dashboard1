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
const researchPanel=new El('section');let mcoMounts=0;
const doc={getElementById:id=>id==='bob-view-research'?researchPanel:null,createElement:t=>new El(t),createElementNS:(_,t)=>new El(t),dispatchEvent:()=>{}};
const window={document:doc,BobMcoComparison:{mount:host=>{mcoMounts++;host.append(new El('mco-comparison'));}}};vm.runInNewContext(fs.readFileSync('comparison_diagrams.js','utf8'),{window,setInterval:()=>{},Event:class{},Date,console});
const panel=new El('section');window.BobDiagrams.mount(panel);
const groups=panel.children.filter(e=>e.tag==='details');
assert.deepEqual(groups.map(e=>e.children[0].textContent),['Markt','Mein Trade','Simulation','Lernen']);
assert.equal(mcoMounts,1);assert.equal(researchPanel.children.length,1,'MCO comparison has one home in research');
assert(groups[1].children.some(e=>e.attrs['data-view']==='trade'),'Current trade curve is linked, not duplicated');
assert(groups[0].children.some(e=>e.attrs['data-view']==='overview'),'Live market chart stays in overview');
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
// Evidence does not count adjacent ticks or fill missing outcomes as successes.
const many=Array.from({length:40},(_,i)=>({at:at+i*60000,value:i?10:null}));
const ev=api.evidenceStats(many,'value',15*60000);assert.equal(ev.selected,3);assert.equal(ev.separated,2);assert.equal(ev.days,1);assert.equal(ev.interval,null);
const days=Array.from({length:12},(_,i)=>({day:'2026-10-'+String(i+1).padStart(2,'0'),count:2,total:i%4>=2?2:-2}));
const ci=api.uncertainty(days);assert(ci.low<0&&ci.high>0);assert.deepEqual(ci,api.uncertainty(days));
assert.equal(api.uncertainty(days.slice(0,9)),null);
const events=[{at,event:'adopted'},{at:at+60000,event:'rollback',reason:'New evidence worse'}];
assert.equal(api.laterEvidence(events,0,[{at:at-1,value:99},{at,value:99},{at:at+1,value:2},{at:at+60000,value:99}],'value').mean,2);
assert(api.overview(study,null,'EUR','horizon').better[0].includes('Noch keine aktuell aktive Übernahme'));
const activeStudy={...study,states:{EUR:{...study.states.EUR,history:events}}};
window.BobDiagrams.update(activeStudy,{precisionLearning:{states:[]}});
// Switch back to the matching currency for the event markers.
const sel=all().filter(e=>e.tag==='select')[0];sel.value='EUR';sel.events.change();
assert(all().some(e=>e.textContent==='Auf einen Blick'));
assert(all().some(e=>e.textContent.includes('Aussagekraft')));
assert(all().some(e=>e.textContent.includes('New evidence worse')));
assert(all().some(e=>e.attrs['aria-label']?.includes('Übernommen')));
window.BobDiagrams.unavailable();assert(all().some(e=>e.textContent.includes('Eine aktuelle Verbesserung ist damit nicht bestätigt')));
// Progress counts saved checks, not profitable outcomes or fabricated future tests.
assert.equal(api.testProgress(null,null).percent,null);
const pendingStudy={comparisons:[{at,currency:'EUR',outcome:null}]};
assert.equal(api.testProgress(pendingStudy,null).percent,0);
const completedStudy={comparisons:[{at,currency:'EUR',outcome:{complete:true}}]};
assert.equal(api.testProgress(completedStudy,null).percent,100);
const incompleteStudy={comparisons:[{at,currency:'EUR',outcome:{complete:false,status:'incomplete'}}]};
const incompleteProgress=api.testProgress(incompleteStudy,null);assert.equal(incompleteProgress.percent,100);assert.equal(incompleteProgress.done,0);assert.equal(incompleteProgress.unusable,1);
assert.equal(api.testProgress({comparisons:[...completedStudy.comparisons,...completedStudy.comparisons]},null).total,1);
const signalProgress=api.testProgress(null,{metrics:{'15':{evaluated:3,neutral:1,missing:4,missingReasons:{pending:1,invalidStart:1,missingFollowup:2}}}});
assert.equal(signalProgress.total,8);assert.equal(signalProgress.done,4);assert.equal(signalProgress.unusable,1);assert.equal(signalProgress.open,3);assert.equal(signalProgress.percent,62.5);
const shadowPending={lifecycle:{comparisons:[{slot:at,currency:'EUR',complete:true,status:'complete',stopComparison:{complete:false,pending:['x']}}]}};
assert.equal(api.testProgress(shadowPending,null).open,1);assert.equal(api.testProgress(shadowPending,null).percent,50);
window.BobDiagrams.update(pendingStudy);let bar=all().find(e=>e.attrs.role==='progressbar');assert.equal(bar.attrs['aria-valuenow'],'0');
window.BobDiagrams.update(completedStudy);bar=all().find(e=>e.attrs.role==='progressbar');assert.equal(bar.attrs['aria-valuenow'],'100');
assert(all().some(e=>e.textContent.includes('100 % abgeschlossen')));
window.BobDiagrams.unavailable();assert(all().some(e=>e.textContent.includes('Stand veraltet – keine aktuelle Fortschrittsbestätigung')));
window.BobDiagrams.update(null);bar=all().find(e=>e.attrs.role==='progressbar');assert.equal(bar.attrs['aria-valuenow'],undefined);
assert(all().some(e=>e.textContent==='Noch keine gespeicherten Prüfungen'));

window.BobDiagrams.update(completedStudy);
window.BobDiagrams.repairs({available:true,workerCheckedAt:Date.now(),items:[],counts:{},modelReview:{counts:{modelled:4},items:[],note:'Getrennt',evidenceSummary:{counts:{original:5,estimated:4,unavailable:3,pending:2},labels:{original:'Mit Originaldaten bestätigt',estimated:'Mit Schätzdaten ausgewertet',unavailable:'Nicht auswertbar',pending:'Nachprüfung ausstehend'},note:'Nur Signalprüfungen mit Datenlücken'}}});
for(const label of ['Mit Originaldaten bestätigt: 5','Mit Schätzdaten ausgewertet: 4','Nicht auswertbar: 3','Nachprüfung ausstehend: 2'])assert(all().some(e=>e.textContent===label));
assert(all().some(e=>e.textContent.includes('Stopp, Ziel und KO bleiben')));
window.BobDiagrams.repairsUnavailable();
assert(all().some(e=>e.textContent.includes('Datenlücken · letzter Stand')));
