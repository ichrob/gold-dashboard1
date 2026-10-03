const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,now=Date.parse('2026-10-03T18:00:00Z'),isin='DE000FG7MTA6';
const conditions=Object.fromEntries(Object.entries({ratio:.1,underlying:'XAU/USD',currency:'EUR',type:'Knock-out Turbo',maturity:'Open End'}).map(([k,value])=>[k,{value,source:'https://www.boerse-stuttgart.de/',conditionVerified:true,reviewedAt:'2026-10-03T17:59:00Z'}]));
const p={isin,isinConfirmed:true,productDirection:'LONG',ko:4143.437,quote:{isin,source:'Börse Stuttgart',checkedAt:'2026-10-03T17:59:00Z',productVerified:true,conditions,metadata:{status:2,ko:4143.437,direction:'LONG',termsDated:false}}};
const status=b.productTermsStatus(p,now);
assert.equal(status.values.ratio,.1);assert.equal(status.values.underlying,'XAU/USD');
assert(!status.complete);assert(status.reasons.some(x=>x.includes('nicht aktiv')));
assert(status.reasons.some(x=>x.includes('Basispreis in USD: Wert fehlt')));
assert(status.reasons.some(x=>x.includes('datierter Produktnachweis')));
console.log('Stuttgart terms/status/freshness tests passed');

assert(!b.evaluateProduct({...p,spot:4200,direction:"LONG",leverage:10}).ok);

// SG table transcription from supplied screenshots: decimal comma, ratio and date-only evidence.
const sgText='ISIN DE000FG309G0\nTyp Put\nBezugsverhältnis 10:1\nBasispreis 4.635,8091 USD (02.10.2026)\nKnock-Out-Barriere 4.635,8091 USD (02.10.2026)';
const parsed=b.detailScreenshotData(sgText,'DE000FG309G0');
assert(parsed.ok,parsed.reason);assert.equal(parsed.terms.ratio.value,.1);
assert.equal(parsed.terms.strike.value,4635.8091);assert.equal(parsed.ko,'4635.8091');
assert.equal(parsed.terms.strike.dateText,'02.10.2026');assert.equal(parsed.terms.strike.at,null);
const merged=b.mergeScreenshotEvidence(null,parsed,'SG-Stammdaten.jpg');
assert.equal(merged.evidence.KO.dateText,'02.10.2026');assert.equal(merged.evidence.KO.at,null);
assert(!b.detailScreenshotData(sgText,'DE000FG4JXV7').ok);
assert(!b.detailScreenshotData('Basispreis 4.635,8091 USD (02.10.2026)','DE000FG309G0').ok);
const mismatch=b.productTermsStatus({...p,ko:4143.44},now);
assert(mismatch.reasons.some(x=>x.includes('gespeichert 4143.44 USD')&&x.includes('Quelle 4143.437 USD')));
console.log('SG numeric/date-only import, identity rejection and KO conflict explanation passed');

// Simulate Android revoking a provider-backed file once its input is cleared.
(async()=>{
 ctx.File=File;
 let released=false;
 const input={files:[{name:'sg.jpg',type:'image/jpeg',lastModified:1,arrayBuffer:async()=>{await Promise.resolve();if(released)throw Error('File could not be read! Code=0');return Uint8Array.from([1,2,3]).buffer;}}],set value(v){released=true;}};
 const copies=await b.retainSelectedImages(input);
 assert(released);assert.equal(copies[0].name,'sg.jpg');
 assert.deepEqual(Array.from(new Uint8Array(await copies[0].arrayBuffer())),[1,2,3]);
 assert.equal((await b.retainSelectedImages({files:[]})).length,0);
 await assert.rejects(b.retainSelectedImages({files:[{arrayBuffer:async()=>{throw Error('provider denied');}}]}),/auf dem Gerät speichern/);
 console.log('Android file retained before picker reset; cancel and read failure tested');
})().catch(e=>{console.error(e);process.exitCode=1;});

const originalSgOcr='21:40 BHG « 451 ED\n= Q BB ESSERE.e | ZERTIFIKATE\nStammdaten\nISIN DEOOOFG4JXV7\nWKN FG4JXV\nClassic Turbo-\n\nProduktare Optionsscheine\nAbwicklungsart © Barausgleich\nBasiswert @ Gold\nBezugsverhaltnis © 10:1\nTyp Put\nBasispreis © 4.460,000 USD\nKnock-Out-Barriere 4,460,000 USD\n@\nKnock-Out Zeit 00:00 - 24:00\nAusgabetag © 10.09.2026\nfinaler Bewertungstag 18.12.2026\n0)\n\nFalligkeitstag © 28.12.2026\nIm Durchschnitt erleiden 7 von 10 Kleinanlegern Verluste\nbeim Handel mit Turbo-Optionsscheinen. Turbo-\nOptionsscheine sind hoch risikoreiche Produkte und\nnicht fiir langfristige Anlagestrategien geeignet.\n\nIII O <\n';
const realImageResult=b.detailScreenshotData(originalSgOcr,"DE000FG4JXV7");
assert(realImageResult.ok);assert.equal(realImageResult.ko,"4460");assert.equal(realImageResult.terms.strike.value,4460);assert.equal(realImageResult.terms.ratio.value,.1);assert(realImageResult.terms.ko.ocrCorrection);assert.equal(realImageResult.terms.ko.at,null);

const summary=b.screenshotSummary({terms:{ratio:{value:.1,source:'SG'},ko:{value:4460,source:'SG'}},evidence:{KO:{value:4460,source:'SG'}},listEvidence:{source:'Liste',ratioText:'Bv 10 – Berechnungsfaktor noch nicht bestätigt'}});
assert(!summary.includes('<table'));assert.equal((summary.match(/KO-Barriere/g)||[]).length,1);
assert(summary.includes('Bezugsverhältnis eingelesen: 0.1'));assert(!summary.includes('Berechnungsfaktor noch'));
assert(summary.includes('noch nicht bestätigt'));
const unconfirmed=b.productTermsStatus({...p,snapshot:{isin,terms:{ratio:{value:.1,source:'SG'}}}},now);
assert(unconfirmed.reasons.some(x=>x.includes('Bezugsverhältnis: Wert eingelesen')));
assert.equal(unconfirmed.values.ratio,undefined);
console.log('Mobile evidence summary and unconfirmed value distinction passed');
