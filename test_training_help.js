'use strict';
const assert=require('node:assert/strict');
const h=require('./training_help.js');
const now=1800000000000;
const report=(items,workerCheckedAt=now)=>({available:true,items,workerCheckedAt});
const attempt={at:now,action:'Archiv prüfen',result:'Originalkurs fehlt'};
const row={id:'signal:abc:60',type:'Signalprüfung',status:'trying',attempts:1,history:[attempt]};
let items=h.classify(report([row]),now);
assert.equal(h.marker(items,'learning'),'(X)');assert.equal(h.marker(items,'diagrams'),'(X)');assert.equal(h.marker(items,'simulation'),'');
items=h.classify(report([{...row,status:'escalated',attempts:3}]),now);
assert.equal(h.marker(items,'learning'),'X');
assert.match(h.reportText(items,now,false),/Archiv prüfen/);
assert.match(h.reportText(items,now,false),/Originalkurs fehlt/);
assert.doesNotMatch(h.reportText(h.classify(report([row]),now),now,false),/Problemkennung: signal:abc/);
assert.equal(h.marker(h.classify(report([{...row,status:'recovered'}]),now),'learning'),'');
assert.equal(h.marker(h.classify(report([{...row,status:'escalated',attempts:0,history:[]}]),now),'learning'),'(X)');
assert.equal(h.marker(h.classify(report([],now-500000),now,1),'simulation'),'(X)');
assert.equal(h.marker(h.classify(report([],now-500000),now,3),'simulation'),'X');
assert.equal(h.marker(h.classify(report([]),now,3),'simulation'),'');
items=h.classify(report([{...row,id:'exit:CHF:123',status:'escalated'}]),now);
assert.equal(h.marker(items,'simulation'),'X');assert.equal(h.marker(items,'improve'),'');
assert.match(h.reportText(items,now,true),/Weitere|weitere/);
const grouped={...report(Array.from({length:15},()=>({...row,status:'escalated'}))),problemGroups:[{id:'test:signal:missingFollowup',kind:'signal',status:'escalated',cases:15,escalated:15,maxAttempts:3,reason:'missingFollowup',type:'Original-Folgekurs fehlt'}]};
const one=h.classify(grouped,now);assert.equal(one.length,1);assert.equal(one[0].cases,15);assert.doesNotMatch(h.reportText(one,now,false),/Betroffene Testfälle: 15/);
(async()=>{
 let copied=false;
 assert.equal(await h.share({share:async()=>{const e=Error();e.name='AbortError';throw e;},clipboard:{writeText:async()=>{copied=true;}}},'x'),'cancelled');assert.equal(copied,false);
 assert.equal(await h.share({share:async()=>{}},'x'),'shared');
 assert.equal(await h.share({share:async()=>{throw Error();},clipboard:{writeText:async()=>{copied=true;}}},'x'),'copied');assert.equal(copied,true);
 assert.equal(await h.share({},'x'),'manual');
 console.log('Training help state transitions and explicit sharing: OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
assert.equal(h.explanation(one,'learning'),'');
assert.doesNotMatch(h.explanation(one,'learning'),/Aktueller Abruf/);
assert.match(h.explanation([{id:'technical:improve',sections:['improve']}],'improve'),/Aktueller Abruf/);
assert.equal(h.explanation(one,'improve'),'');
// A temporary outage must not leave a hidden section permanently marked X.
{
 const vm=require('node:vm'),fs=require('node:fs'),scheduled=new Map();let seq=0,retries=0;
 const window={document:{hidden:false},fetch:async()=>({ok:true,json:async()=>({ok:true,status:'queued'})})};
 vm.runInNewContext(fs.readFileSync('training_help.js','utf8'),{window,Date,AbortSignal,setInterval(){},setTimeout(fn,delay){scheduled.set(++seq,{fn,delay});return seq;},clearTimeout(id){scheduled.delete(id);}});
 const retry=()=>{retries++;window.BobTrainingHelp.observe('improve',false,retry);};
 window.BobTrainingHelp.observe('improve',false,retry);
 for(let i=0;i<4;i++){const [id,timer]=scheduled.entries().next().value;scheduled.delete(id);timer.fn();}
 assert.equal(retries,4);assert.equal([...scheduled.values()][0].delay,60000);
 window.BobTrainingHelp.observe('improve',true);
 assert.equal(scheduled.size,0);
}

// Retired historical evidence gaps are not actionable warnings or share requests.
assert.equal(h.marker(one,'learning'),'');
assert.equal(h.marker(one,'diagrams'),'');
assert.equal(h.actionable(one).length,0);
const tech={id:'technical:audit',sections:['learning','diagrams'],state:'escalated'};
assert.equal(h.marker([...one,tech],'learning'),'X');
assert.equal(h.marker([...one,{...tech,state:'trying'}],'learning'),'(X)');
assert.equal(h.marker([...one,{...tech,id:'test:signal:unknown'}],'learning'),'X');
const withEvidence={modelReview:{evidenceSummary:{counts:{original:8,estimated:4,unavailable:3,pending:2}}}};
const before=JSON.stringify(one);
assert.equal(h.explanation(one,'learning',withEvidence),'');
const text=h.evidenceText(withEvidence);
assert.match(text,/8 mit Originaldaten bestätigt/);
assert.match(text,/4 mit Schätzdaten ausgewertet/);
assert.match(text,/3 nicht auswertbar/);
assert.match(text,/2 Nachprüfungen ausstehend/);
assert.match(text,/Schätzdaten bleiben getrennt/);
assert.equal(JSON.stringify(one),before,'Display must not close unresolved archive cases');
assert.equal(h.evidenceText({}), '');
withEvidence.modelReview.evidenceSummary.counts.original=-1;
assert.equal(h.evidenceText(withEvidence),'');

// No manual handoff controls. Failure is queued automatically, retried on
// unconfirmed delivery, and never presented as a completed repair.
(async()=>{
 const fs=require('node:fs'),vm=require('node:vm');
 class Element{
  constructor(tag){this.tag=tag;this.children=[];this.style={};this.dataset={};this.hidden=false;}
  append(...xs){this.children.push(...xs);}setAttribute(){}
  querySelector(){return null;}
 }
 const group=new Element('section'),nodes=[],intervals=[];let queueCalls=0,accept=false;
 const historical={...grouped,workerCheckedAt:Date.now()};
 const doc={hidden:false,createElement:tag=>{const e=new Element(tag);nodes.push(e);return e;},querySelectorAll:()=>[],querySelector:()=>null,addEventListener(){}};
 const window={document:doc,navigator:{share(){throw Error('No user sharing required');}},fetch:async(url,opts)=>{
  if(url==='/api/assistance'){
   queueCalls++;assert.deepEqual(JSON.parse(opts.body),{code:'training-audit-unavailable'});
   return {ok:accept,json:async()=>({ok:accept,status:accept?'queued':'unavailable'})};
  }
  return {ok:true,json:async()=>historical};
 }};
 vm.runInNewContext(fs.readFileSync('training_help.js','utf8'),{window,Date,AbortSignal,setInterval(fn){intervals.push(fn);},setTimeout(){},clearTimeout(){}});
 window.BobTrainingHelp.mount(group);
 await new Promise(resolve=>setImmediate(resolve));
 const box=group.children[0];assert.equal(box.hidden,true);
 assert(!nodes.some(x=>['button','textarea','a'].includes(x.tag)));
 for(let n=0;n<3;n++)window.BobTrainingHelp.observe('audit',false);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(queueCalls,1);assert.equal(box.hidden,false);
 assert(nodes.some(x=>/Fehlererfassung noch nicht bestätigt/.test(x.textContent||'')));
 accept=true;intervals[0]();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(queueCalls,2);
 assert(nodes.some(x=>/für die automatische KI-Prüfung erfasst/.test(x.textContent||'')));
 intervals[0]();await new Promise(resolve=>setImmediate(resolve));assert.equal(queueCalls,2,'Do not duplicate a confirmed queue entry');
 window.BobTrainingHelp.observe('audit',true);assert.equal(box.hidden,true);
 assert.equal(historical.problemGroups[0].status,'escalated','Archive evidence remains unchanged');
 console.log('Automatic training handoff: no sharing controls, anonymous queue, retry, deduplication and recovery passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
