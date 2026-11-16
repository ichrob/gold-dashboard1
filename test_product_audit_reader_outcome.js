"use strict";
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const panel=fs.readFileSync('degiro_product_audit_panel.py','utf8');
const start=panel.indexOf("  const handset=byId('bobHandyReadEvidenceItems');");
const end=panel.indexOf('  // Visible warning',start);
assert(start>0&&end>start);
function element(){return {children:[],dataset:{},style:{},textContent:'',
 append(...nodes){this.children.push(...nodes);},replaceChildren(){this.children=[];},querySelectorAll(){return [];}};}
function render(receipt){
 const root=element();
 const context={byId:()=>root,document:{createElement:element},safe:String,fmt:String,
  leverageObservationLabel:()=>'',r:{status:'ok'},items:[{isin:'DE000FD0S0G4',state:'incomplete',
   handsetObservation:{code:'COMPLETE',observedAt:'2026-10-28T10:59:00Z',fields:{Geld:'13,06',Brief:'13,07'},missingFields:[],latestReadReceipt:receipt}}]};
 vm.runInNewContext(panel.slice(start,end),context);
 const row=root.children[1];return row.children.map(x=>x.textContent).join('\n');
}
const failure=render({code:'READ_TIMEOUT',receivedAt:'2026-10-28T11:01:00Z',hasObservation:false});
assert(failure.includes('Lesung nicht abgeschlossen'));
assert(failure.includes('Aktualisierung ohne neue Werte'));
assert(failure.includes('früheren Lesung'));
assert(failure.includes('Geld: 13,06'));
assert(failure.includes('2026-10-28T10:59:00Z'));
assert(!failure.includes('Angeforderte Felder gelesen'));
const success=render({code:'COMPLETE',receivedAt:'2026-10-28T11:01:00Z',hasObservation:true});
assert(success.includes('Angeforderte Felder gelesen'));
assert(!success.includes('Aktualisierung ohne neue Werte'));
assert(render(undefined).includes('Angeforderte Felder gelesen'));
console.log('Failed refresh stays visible alongside retained historical handset values.');
