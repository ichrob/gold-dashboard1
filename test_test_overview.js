const assert=require('node:assert/strict');
const {testOverviewLines}=require('./bob_unified_workspace.js');
assert.match(testOverviewLines(null).join(' '),/nicht verfügbar/);
const rows=testOverviewLines({version:1,items:[{label:'Test',state:'observed',sampledRecords:0,comparableCases:null,missing:'Nachweis fehlt'}],chainSampleAvailable:false});
assert.match(rows.join(' '),/Stichprobe: 0/);
assert.match(rows.join(' '),/Vergleichbare Fälle: unbekannt/);
assert.match(rows.join(' '),/Abschluss nicht bestätigt/);
assert.match(rows.join(' '),/keine Fallnachweise/);
for(const [state,label] of [['waiting-for-signal','wartet auf bestätigte Richtung'],['input-blocked','Originaldaten nicht bestätigt'],['night-paused','planmäßige Nacht-/Wochenendpause']]){
 const text=testOverviewLines({version:1,items:[{label:'Vergleich',state,sampledRecords:0,comparableCases:null,missing:'Neue Fälle erforderlich.'}]}).join(' ');
 assert.ok(text.includes(label));
 assert.match(text,/Vergleichbare Fälle: unbekannt/);
 assert.match(text,/Abschluss nicht bestätigt/);
}
console.log('Test overview: absent, zero, unknown and incomplete evidence kept distinct');
