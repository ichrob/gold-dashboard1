'use strict';
const assert=require('node:assert/strict'),fs=require('fs');
const {researchGuide:guide,sourceFibMarks}=require('./video_brief.js');
const now=Date.parse('2026-10-27T12:00:00Z'),at=new Date(now-10000).toISOString();
const item={publishedAt:now/1000-3600,transcriptAnalyzed:true,trustedTranscript:true,outlook:'LONG',horizon:'längerfristig',enhancements:{summary:{kind:'ai',partial:true}},overview:{sections:[{key:'conditions',evidenceIds:['c','c','absent']}],evidence:[{id:'c',at:30,text:'If support holds, gold could rise.'}]}};
const before=JSON.stringify(item),bob={fresh:true,at,direction:'SHORT',reason:'15m und 5m bestätigt'};
let r=guide(item,bob,now);
assert.match(r.age,/Aktuelles Video/);assert.match(r.status,/Teilweise ausgewertet/);assert.equal(r.conditions.length,1);assert.equal(r.conditions[0].text,item.overview.evidence[0].text);
assert.equal(r.direction,'LONG');assert.equal(r.bobDirection,'SHORT');assert.equal(r.horizon,'längerfristig');assert.match(r.comparison,/Keine direkte Signalbestätigung/);assert.equal(JSON.stringify(item),before);
assert.match(guide({...item,publishedAt:null},bob,now).age,/Datum unbekannt/);
assert.match(guide({...item,publishedAt:null,publishedDate:'2026-10-27'},bob,now).age,/Uhrzeit unbekannt/);
assert.match(guide({...item,publishedAt:now/1000-90000},bob,now).age,/Älteres Video/);
assert.match(guide({...item,publicFallback:true},bob,now).age,/Ersatzvideo/);
assert.match(guide({...item,publishedAt:now/1000+1},bob,now).age,/Datum unbekannt/);
assert.equal(guide({...item,trustedTranscript:false},bob,now).direction,'UNKLAR');
assert.equal(guide(item,{...bob,at:new Date(now-60001).toISOString()},now).bobDirection,'NICHT_AKTUELL');
assert.equal(guide(item,{...bob,at:'2026-10-27T12:00:00'},now).bobDirection,'NICHT_AKTUELL');
assert.equal(guide(item,{...bob,fresh:false},now).bobDirection,'NICHT_AKTUELL');
assert.equal(guide({...item,overview:{sections:[{key:'conditions',evidenceIds:['c']}],evidence:[{id:'c',at:-1,text:'bad'}]}},bob,now).conditions.length,0);
const mark={key:'r618',price:4200,at:32,quote:'The Fibonacci 61.8 percent level is at 4200.'};
assert.equal(sourceFibMarks({...item,mcoFibonacci:[mark]}).length,1);
for(const changed of [{at:null},{quote:''},{price:NaN},{key:'invented'}])assert.equal(sourceFibMarks({...item,mcoFibonacci:[{...mark,...changed}]}).length,0);
assert.equal(sourceFibMarks({...item,trustedTranscript:false,mcoFibonacci:[mark]}).length,0);
assert.equal(sourceFibMarks({...item,transcriptAnalyzed:false,mcoFibonacci:[mark]}).length,0);
const html=fs.readFileSync('Bob.html','utf8');assert(html.includes('renderGuide(box,x,window.BobResearchContext?.())'));assert(html.includes('guide.age'));assert(html.includes('near:false'));assert(!html.includes("['● Nahe Kursmarken'"));
console.log('Research guide: dates, fallback, partial summaries, conditional evidence, stale Bob comparison and chart provenance passed');
// Exercise the rendered guide and its refresh without network or trade mutations.
const vm=require('node:vm');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.textContent='';this.parent=null;}
 append(...nodes){for(const child of nodes){child.parent=this;this.children.push(child);}}
 get isConnected(){return this.tag==='root'||!!this.parent?.isConnected;}
 get firstElementChild(){return this.children[0];}
 replaceWith(other){const parent=this.parent;if(!parent)return;parent.children[parent.children.indexOf(this)]=other;other.parent=parent;this.parent=null;}
}
const document={visibilityState:'visible',createElement:tag=>new Element(tag)},timers=[];
const browser={document,BobResearchContext:()=>({fresh:false})};
const env={window:browser,URL,Date,setInterval:fn=>timers.push(fn)};vm.createContext(env);vm.runInContext(fs.readFileSync('video_brief.js','utf8'),env);
const host=new Element('root'),renderItem={...item,url:'https://www.youtube.com/watch?v=wjLMQ7QfMiM'};
browser.BobVideoBrief.renderGuide(host,renderItem,{fresh:true,direction:'SHORT',at:new Date().toISOString()});
function texts(el){return [el.textContent,...el.children.flatMap(texts)];}
assert(texts(host).includes('SHORT'));
assert(texts(host).some(t=>t.includes('Teilweise ausgewertet')));
assert(texts(host).some(t=>t.includes('Originalstelle')));
timers[0]();assert(texts(host).includes('Nicht aktuell bestätigt'));assert(!texts(host).includes('SHORT'));assert.equal(host.children.length,1);
console.log('Rendered research comparison refreshes stale signals without duplicate sections or external writes');
