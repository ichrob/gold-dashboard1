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
const reversalText=testOverviewLines({version:1,intradayTimingStudy:{version:'v2',status:'legacy-positions-draining',legacyOpenPositions:1,exitPolicy:'confirmed-reversal-exit-v1',variants:[]}}).join(' ');
assert.match(reversalText,/maximale Haltedauer/);
assert.match(reversalText,/Bestätigte Trendumkehr: vorher aussteigen/);
assert.match(reversalText,/neuem gültigem Einstieg mit neuer Kursbeobachtung/);
assert.match(reversalText,/1 Positionen noch offen/);

const handsetLines=testOverviewLines({version:1,handsetComparisons:{status:'observed',accepted:2,dailyFxAccepted:2,missingFx:0,unpaired:1,items:[{isin:'TEST',quantity:1,grossEur:1.78,modelNetEur:-.28,feesEur:2,slippageEur:.06,fxApproximation:true,fxDate:'2026-11-06'}],note:'Keine Kontobuchung'}}).join(' ');
assert.match(handsetLines,/2 Tageskurs-Umrechnungen akzeptiert/);
assert.match(handsetLines,/0 Währungsgrundlagen fehlen/);
assert.match(handsetLines,/nach Modellkosten -0.28 €/);
assert.match(handsetLines,/Tageskurs-Näherung 2026-11-06 akzeptiert/);
assert.doesNotMatch(testOverviewLines({version:1,handsetComparisons:{status:'unavailable'}}).join(' '),/Handy-Kursvergleiche/);
const reviewed=testOverviewLines({version:1,qualityCampaign:{version:'synthetic',studies:[],historicalReview:{status:'observed',counts:{reviewed:2,modeled:1,unavailable:1},items:[{study:'entry-delay',closedAt:1,modelStatus:'endpoint-model',returnsPct:{'0s':-2.16}},{study:'warning-confirmed',closedAt:2,modelStatus:'unavailable',returnsPct:{}}],note:'Originalergebnisse bleiben unbestätigt.'}}}).join(' ');
assert.match(reviewed,/2 Fälle · 1 mit Endpunktmodell berechnet · 1 ohne ausreichende Berechnungsgrundlage/);
assert.match(reviewed,/-2.160 %/);
assert.match(reviewed,/Originalergebnisse bleiben unbestätigt/);
