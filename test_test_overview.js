const assert=require('node:assert/strict');
const {testOverviewLines}=require('./bob_unified_workspace.js');
assert.match(testOverviewLines(null).join(' '),/nicht verfügbar/);
const rows=testOverviewLines({version:1,items:[{label:'Test',state:'observed',sampledRecords:0,comparableCases:null,missing:'Nachweis fehlt'}],chainSampleAvailable:false});
assert.match(rows.join(' '),/Stichprobe: 0/);
assert.match(rows.join(' '),/Vergleichbare Fälle: unbekannt/);
assert.match(rows.join(' '),/Abschluss nicht bestätigt/);
assert.match(rows.join(' '),/keine Fallnachweise/);
console.log('Test overview: absent, zero, unknown and incomplete evidence kept distinct');
