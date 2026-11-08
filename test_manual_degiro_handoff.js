'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('real_trade_journal.js','utf8');
const start=src.indexOf(' function manualDegiroHandoff(');
const end=src.indexOf(' function renderWorkflow(', start);
assert(start>0 && end>start,'Manual helper must appear before workflow renderer');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.onclick=null;this.href='';}
 append(...parts){this.children.push(...parts);}
 replaceChildren(...parts){this.children=[...parts];this.textContent='';}
}
const fields={isin:'DE000FG4JXV7',quantity:'5',entry:'8.75',direction:'LONG'};
const ctx={
 document:{createElement:tag=>new Element(tag),
  querySelector:selector=>({value:fields[selector.match(/"([^"]+)"/)?.[1]]||''})},
 navigator:{clipboard:{writeText:async()=>{}}},
 console,
};
vm.createContext(ctx);vm.runInContext(src.slice(start,end),ctx);
const render=ctx.manualDegiroHandoff;
function flatten(node){return [node.textContent||'',...(node.children||[]).flatMap(flatten)].join(' ');}
let view=render({active:null},{});
assert.match(flatten(view),/Kaufentwurf/);
assert.match(flatten(view),/unbestätigt/);
assert(!view.children.some(x=>x.textContent==='Order platzieren'),'No submit-order button');
const draft=view.children.find(x=>x.tagName==='details');
draft.children.find(x=>x.tagName==='button').onclick();
assert.match(flatten(draft),/Nicht|unbestätigt/);
assert.match(flatten(draft),/ISIN kopieren/);
assert.match(flatten(draft),/Stückzahl kopieren/);
let trade={snapshot:{dir:'SHORT',product:{isin:'DE000FG4JXV7',quantity:12,currency:'EUR'},
 purchase:{transactionId:'confirmed-1',at:'2026-11-09T14:00:00Z'}}};
view=render({active:trade,validPlan:true},{available:true,stop:10.11,currency:'EUR'});
assert.match(flatten(view),/Verkauf|Ausstieg/);
assert.match(flatten(view),/Stop|Stopp/);
assert.match(flatten(view),/12/);
assert.match(flatten(view),/DE000FG4JXV7/);
assert.match(flatten(view),/manuell/);
assert(!/submitOrder|placeOrder|sendOrder|fetch\(/.test(src.slice(start,end)));
view=render({active:{snapshot:{product:{isin:'DE000FG4JXV7',quantity:2}}},validPlan:false},{});
assert.match(flatten(view),/Ohne eindeutige Ausführungsquittung/);
view=render({active:{snapshot:{product:{isin:'INVALID',quantity:0},
 purchase:{transactionId:'confirmed-1',at:'2026-11-09T14:00:00Z'}}},validPlan:false},{});
assert.match(flatten(view),/Kein Verkaufsentwurf/);
console.log('DEGIRO manual handoff: buy draft, active position, stop, exit and no trade action passed');
