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
const modelLines=testOverviewLines({version:1,items:[],qualityCampaign:{version:'test',studies:[],modeledSimulation:{status:'collecting',studies:[{id:'entry-delay',label:'Verzögerung',complete:2,estimatedComplete:1,open:0,inconclusive:3}],note:'Schätzungen separat'}},recentFollowups:{status:'observed',items:[{state:'original-awaiting-harvest'},{state:'estimated'}]}}).join(' ');
assert.match(modelLines,/davon mit Schätzung 1/);
assert.match(modelLines,/Originalkurs vorhanden · Verarbeitung steht aus/);
assert.match(modelLines,/mit Schätzwerten ausgewertet/);

const timingText=testOverviewLines({version:1,intradayTimingStudy:{version:'v1',status:'collecting',observationFresh:false,variants:[{mode:'original',variant:'base5',label:'5m Basis',horizonMinutes:30,closed:0,inconclusive:2,falseStarts:0,meanOriginalNetPct:null,meanEstimatedNetPct:null}],latency:{direction:'LONG',firstWarningObservedAt:1793955600000,confirmationObservedAt:null,pushSentAt:null,pushEvidence:'Kein Android-Anzeigenachweis'},note:'Keine KO-Produktrendite'}}).join(' ');
assert.match(timingText,/Aktueller Lauf nicht bestätigt/);
assert.match(timingText,/3 \/ 5 \/ 7 Minuten/);
assert.match(timingText,/2 ungeklärt/);
assert.match(timingText,/noch unbekannt Original/);
assert.match(timingText,/Hauptbestätigung unbekannt/);
assert.match(timingText,/Kein Android-Anzeigenachweis/);
assert.match(timingText,/Keine KO-Produktrendite/);
