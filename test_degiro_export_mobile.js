/* Synthetic-only mobile rendering tests. No account access or browser network. */
'use strict';
const assert=require('node:assert/strict');
const {readReport,renderResults}=require('./degiro_report_import');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.attrs={};this.listeners={};this.textContent='';this.className='';}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(key,value){this.attrs[key]=value;}
 addEventListener(event,handler){this.listeners[event]=handler;}
}
const document={createElement:tag=>new Element(tag)};
const csv=[
 'Produkt,Symbol/ISIN,Anzahl,Schlußkurs,Wert,,Wert in CHF',
 'CASH & CASH FUND & F, , , ,CHF,503.31,503.31',
 'SG GOLD FUTURE FAKTOR LONG HB 15,DE000FE4UF84,1,0.12,EUR,0.12,0.11'
].join('\n');
const data=readReport(csv),host=new Element('div');
const copied=[];
renderResults(document,host,data,x=>copied.push(x));
function flatten(n){return [n,...n.children.flatMap(flatten)];}
const all=flatten(host);
assert.equal(data.records.length,1);
assert.equal(data.cashBalances.length,1);
assert.equal(all.filter(e=>e.tag==='table').length,0,'No wide tables on mobile');
assert.equal(all.filter(e=>e.tag==='article').length,1,'Each position has its own mobile card');
assert.equal(all.filter(e=>e.tag==='button').length,1,'Each ISIN has a copy control');
assert(all.some(e=>e.textContent.includes('Faktorprodukt')),'Factor warning remains visible');
assert(all.some(e=>e.textContent==='503.31 CHF'),'Cash amount is visible');
assert(all.some(e=>e.textContent==='0.12 EUR'),'Exact export precision preserved');
assert(all.some(e=>e.textContent==='0.11 CHF'),'Original account currency is displayed');
assert(all.some(e=>e.textContent.includes('keine Live-Kontoverbindung')));
all.find(e=>e.tag==='button').listeners.click();
assert.deepEqual(copied,['DE000FE4UF84']);
const evilCSV='ISIN,Anzahl,Produkt\nDE000FE4UF84,1,"<script>alert(1)</script>"';
const evil=readReport(evilCSV),safeHost=new Element('div');
renderResults(document,safeHost,evil,()=>{});
assert(flatten(safeHost).some(e=>e.textContent==='<script>alert(1)</script>'));
assert(!flatten(safeHost).some(e=>e.tag==='script'),'CSV text never becomes script elements');
assert.equal(evil.brokerVerified,false);
assert.equal(evil.ordersEnabled,false);
console.log('DEGIRO mobile export cards tests passed');
