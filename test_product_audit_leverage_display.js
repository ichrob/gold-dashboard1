'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const panel=fs.readFileSync('degiro_product_audit_panel.py','utf8');
const start=panel.indexOf(' const fmt=iso=>');
const end=panel.indexOf(' // A previously complete *analysis*',start);
assert(start>0&&end>start);
const context={};
vm.createContext(context);
vm.runInContext(panel.slice(start,end)+'\n;globalThis.leverageLabel=leverageObservationLabel;globalThis.leverageTime=leverageTimeLabel;',context);
const value={isin:'DE000SX7PE82',leverageSourceAt:null,
 leverageObservation:{value:7.33099042283274,current:true,
 kind:'shared-issuer-observation',at:'2026-11-06T08:46:49Z',researchOnly:true}};
const shown=context.leverageLabel(value,'ok');
assert(context.leverageLabel(value,'stale').includes('Prüfbericht nicht aktuell'));
assert(shown.includes('7.33×'));
assert(shown.includes('SG-Recherchebeobachtung'));
assert(shown.includes('nicht aus DEGIRO abgelesen'));
assert(shown.includes('keine Handelsfreigabe'));
assert(context.leverageTime(value).includes('kein eigener Original-Hebelzeitstempel'));
for(const no of [{}, {leverageObservation:{value:7.3,current:false}},
 {leverageObservation:{value:-2,current:true}},
 {leverageObservation:{value:NaN,current:true}}]) {
 assert(context.leverageLabel(no,'ok').includes('kein aktueller Analyse-Hebel'));
}
assert(panel.includes("'\\nAnalyse-Hebel: '+leverageObservationLabel(item,r.status)"));
assert(panel.includes("'\\nHinweis: DEGIRO-Hebel aus dieser Lesung nicht belegt."));
assert(!shown.includes('ausführbarer'));
console.log('Handy partial leverage vs issuer research observation clearly separated.');
