const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{}};vm.runInNewContext(fs.readFileSync('degiro_assistant.js','utf8'),ctx);
const b=ctx.window.BobDegiro,now=Date.parse('2026-10-03T18:00:00Z'),isin='DE000FG7MTA6';
const conditions=Object.fromEntries(Object.entries({ratio:.1,underlying:'XAU/USD',currency:'EUR',type:'Knock-out Turbo',maturity:'Open End'}).map(([k,value])=>[k,{value,source:'https://www.boerse-stuttgart.de/',conditionVerified:true,reviewedAt:'2026-10-03T17:59:00Z'}]));
const p={isin,isinConfirmed:true,productDirection:'LONG',ko:4143.437,quote:{isin,source:'Börse Stuttgart',checkedAt:'2026-10-03T17:59:00Z',productVerified:true,conditions,metadata:{status:2,ko:4143.437,direction:'LONG',termsDated:false}}};
const status=b.productTermsStatus(p,now);
assert.equal(status.values.ratio,.1);assert.equal(status.values.underlying,'XAU/USD');
assert(!status.complete);assert(status.reasons.some(x=>x.includes('nicht aktiv')));
assert(status.reasons.some(x=>x.includes('Basispreis in USD: Wert fehlt')));
assert(status.reasons.some(x=>x.includes('belegter Zeitbezug fehlt')));
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

// 2026-10-05 SG mobile screenshot: USD/date wrap below the amount.
const mobileSg='ISIN DE000FG5NMF2\nTyp Call\nBezugsverhältnis 10:1\nBasispreis 4.117,6769\nUSD (05.10.2026)\nKnock-Out-Barriere 4.117,6769\n© USD (05.10.2026)\nKnock-Out Zeit 00:00 - 24:00';
const mobile=b.detailScreenshotData(mobileSg,'DE000FG5NMF2');
assert(mobile.ok,mobile.reason);assert.equal(mobile.terms.strike.value,4117.6769);
assert.equal(mobile.terms.ko.value,4117.6769);assert.equal(mobile.terms.ko.dateText,'05.10.2026');
assert.equal(mobile.terms.ko.at,null);
// Actual local OCR line order and damaged date: retain amount, not a guessed date.
const wrappedOcr=mobileSg.replace('Basispreis 4.117,6769\nUSD (05.10.2026)','. . 4.117,6769\nBasispreis © USD (05:10:2026)').replace('© USD (05.10.2026)','® USD (0 3:10:2026)');
const damaged=b.detailScreenshotData(wrappedOcr,'DE000FG5NMF2');
assert(damaged.ok,damaged.reason);assert.equal(damaged.terms.strike.value,4117.6769);
assert.equal(damaged.terms.ko.value,4117.6769);assert.equal(damaged.terms.ko.dateText,null);
assert.equal(damaged.terms.ko.at,null);assert(damaged.terms.ko.ocrCorrection.includes('Aktualität nicht bestätigt'));
for(const date of ['31.02.2026','05:10:2026']){
 const x=b.detailScreenshotData(mobileSg.replaceAll('05.10.2026',date),'DE000FG5NMF2');
 assert(x.ok);assert.equal(x.terms.ko.dateText,null);assert.equal(x.terms.ko.at,null);
}
assert(!b.detailScreenshotData(mobileSg.replace('© USD','Andere Zeile\nUSD'),'DE000FG5NMF2').ok);
assert(!b.detailScreenshotData(mobileSg+'\nKnock-Out-Barriere 4.118,0000 USD','DE000FG5NMF2').ok);
assert(!b.detailScreenshotData('Kurs von: 10:45:14 (05.10.2026)\nGeld 4,310 EUR\nBrief 4,320 EUR','DE000FG5NMF2').ok);
console.log('Wrapped SG terms preserve amounts, identity checks and unconfirmed dates');

// SG browser-title WKN and quotes from the supplied 11:13 / 11:14 images.
const sgTitle='FG5NMF - 4,71/ 4,72 €\nsg-zertifikate.de\nFG5NMF\nKurs von: 11:13:52 (05.10.2026)\nGeld\n4,710 EUR';
const titleQuote=b.detailScreenshotData(sgTitle,'DE000FG5NMF2');
assert(titleQuote.ok,titleQuote.reason);assert.equal(titleQuote.identityBasis,'WKN');
assert.equal(titleQuote.bid,4.71);assert.equal(titleQuote.ask,4.72);
assert.equal(titleQuote.sourceTime,'05.10.2026 11:13:52');assert.equal(titleQuote.times.quote.at,null);
const nextQuote=b.detailScreenshotData('FG5NMF - 4,69 / 4,70 €\nsg-zertifikate.de\n4,690 EUR\nBrief\n4,700 EUR','DE000FG5NMF2');
assert(nextQuote.ok,nextQuote.reason);assert.equal(nextQuote.bid,4.69);assert.equal(nextQuote.ask,4.7);
const firstQuote=b.mergeScreenshotEvidence(null,titleQuote,'11-13.jpg');
const nextMerged=b.mergeScreenshotEvidence(firstQuote,nextQuote,'11-14.jpg');
assert.equal(nextMerged.sourceTime,'');assert.equal(nextMerged.evidence.Geld.at,null);assert.equal(nextMerged.times.quote.at,null);
assert.equal(nextMerged.bid,4.69);assert.equal(nextMerged.ask,4.7);
for(const bad of [sgTitle.replaceAll('FG5NMF','FG309G'),sgTitle+'\nISIN DE000FG309G0'])assert(!b.detailScreenshotData(bad,'DE000FG5NMF2').ok);
const partialTitle=b.detailScreenshotData(sgTitle.replace('4,710 EUR','4,690 EUR'),'DE000FG5NMF2');
assert(partialTitle.ok);assert.equal(partialTitle.bid,4.69);assert.equal(partialTitle.ask,null);assert(partialTitle.importWarnings[0].includes('Briefkurs fehlt'));
assert(!b.detailScreenshotData('Indikation Basiswert 4.166,350 USD\n05.10.2026 11:14:01','DE000FG5NMF2').ok);
const wknTerms=b.detailScreenshotData('WKN FG5NMF\nBezugsverhältnis 10:1','DE000FG5NMF2');assert(wknTerms.ok);
const actualWrapped='ISIN DEOOOFG5NMF2\nWKN FG5NMF\nTyp Call\n; , 4.117,6769\nBasispreis ® USD (22:10:2028)\nKnock-Out-Barriere 4.117,6769\noO USD (JR 0E2026)';
const wrap=b.detailScreenshotData(actualWrapped,'DE000FG5NMF2');assert(wrap.ok,wrap.reason);
assert.equal(wrap.terms.strike.value,4117.6769);assert.equal(wrap.terms.ko.value,4117.6769);assert.equal(wrap.terms.ko.dateText,null);
console.log('WKN identity, same-image SG title quotes, real mobile table layout and isolated timestamps passed');

// Simulate Android revoking a provider-backed file once its input is cleared.
(async()=>{
 ctx.File=File;
 let released=false;
 const input={files:[{name:'sg.jpg',type:'image/jpeg',lastModified:1,arrayBuffer:async()=>{await Promise.resolve();if(released)throw Error('File could not be read! Code=0');return Uint8Array.from([1,2,3]).buffer;}}],set value(v){released=true;}};
 const copies=await b.retainSelectedImages(input);
 assert(released);assert.equal(copies[0].name,'sg.jpg');
 assert.deepEqual(Array.from(new Uint8Array(await copies[0].arrayBuffer())),[1,2,3]);
 assert.equal((await b.retainSelectedImages({files:[]})).length,0);
 await assert.rejects(b.retainSelectedImages({files:[{arrayBuffer:async()=>{throw Error('provider denied');}}]}),/Galerie-Bild konnte nicht gelesen werden/);
 const resetFails={files:[new File(['image'],'test.jpg')],set value(v){throw Error('reset failed');}};
 assert.equal((await b.retainSelectedImages(resetFails))[0].name,'test.jpg');
 await assert.rejects(b.retainSelectedImages({files:[new File([],'empty.jpg')]}),/EMPTY_IMAGE/);
 console.log('Android file retained before picker reset; cancel and read failure tested');
})().catch(e=>{console.error(e);process.exitCode=1;});

const originalSgOcr='21:40 BHG « 451 ED\n= Q BB ESSERE.e | ZERTIFIKATE\nStammdaten\nISIN DEOOOFG4JXV7\nWKN FG4JXV\nClassic Turbo-\n\nProduktare Optionsscheine\nAbwicklungsart © Barausgleich\nBasiswert @ Gold\nBezugsverhaltnis © 10:1\nTyp Put\nBasispreis © 4.460,000 USD\nKnock-Out-Barriere 4,460,000 USD\n@\nKnock-Out Zeit 00:00 - 24:00\nAusgabetag © 10.09.2026\nfinaler Bewertungstag 18.12.2026\n0)\n\nFalligkeitstag © 28.12.2026\nIm Durchschnitt erleiden 7 von 10 Kleinanlegern Verluste\nbeim Handel mit Turbo-Optionsscheinen. Turbo-\nOptionsscheine sind hoch risikoreiche Produkte und\nnicht fiir langfristige Anlagestrategien geeignet.\n\nIII O <\n';
const realImageResult=b.detailScreenshotData(originalSgOcr,"DE000FG4JXV7");
assert(realImageResult.ok);assert.equal(realImageResult.ko,"4460");assert.equal(realImageResult.terms.strike.value,4460);assert.equal(realImageResult.terms.ratio.value,.1);assert(realImageResult.terms.ko.ocrCorrection);assert.equal(realImageResult.terms.ko.at,null);

const summary=b.screenshotSummary({terms:{ratio:{value:.1,source:'SG'},ko:{value:4460,source:'SG'}},evidence:{KO:{value:4460,source:'SG'}},listEvidence:{source:'Liste',ratioText:'Bv 10 – Berechnungsfaktor noch nicht bestätigt'}});
assert(!summary.includes('<table'));assert.equal((summary.match(/KO-Barriere/g)||[]).length,1);
assert(summary.includes('Bezugsverhältnis eingelesen: 0.1'));assert(!summary.includes('Berechnungsfaktor noch'));
assert(summary.includes('noch nicht bestätigt'));
// Isolate unconfirmed image evidence: verified issuer terms otherwise correctly win.
const unconfirmed=b.productTermsStatus({...p,quote:null,snapshot:{isin,terms:{ratio:{value:.1,source:'SG'}}}},now);
assert(unconfirmed.reasons.some(x=>x.includes('Bezugsverhältnis: Wert eingelesen')));
assert.equal(unconfirmed.values.ratio,undefined);
console.log('Mobile evidence summary and unconfirmed value distinction passed');

const compact=b.compactProductCard({isin:'DE000FG4JXV7',index:1,productDirection:'SHORT',snapshot:{terms:{ratio:{value:.1},strike:{value:4460}}}},['Geld fehlt','Brief fehlt']);
assert(compact.includes('Automatisch erkannte Werte'));
assert(!compact.includes('data-card-confirm'));
assert(compact.includes('data-selection-upload="1"'));
assert(compact.includes('Quellen und Einzelheiten'));assert(compact.includes('/product-details/fg4jxv'));
assert.equal((compact.match(/Geld, Brief und Quellenzeit \(Kursdaten\)/g)||[]).length,1);

// Real Tesseract.js 5.1.1 output from the supplied 1000070489 SG screenshot.
const wasmPrimary = {"text": "M4586 CNC RAIN 77)\n= Q EERE | zeRmFKaTE\nISIN DEOOOFG5NMF2\nWKN FG5NMF\n\nBEST Turbo-\nProduktart Optionsscheine (Open-\nEnd)\nBasiswert © Gold\nBezugsverhaltnis © 10:1\nTyp Call\nBasispreis ® pall (22:10:2028)\nKnock-Out-Barriere 4.117,6769\noO USD (JRA 0E2026)\nKnock-Out Zeit 00:00 - 24:00\nAusgabetag ® 04.08.2026\nQuanto ® Nein\n@ Risikopramie ® 5,00%\nKennzahlen\nIm Durchschnitt erleiden 7 von 10 Kleinanlegern Verluste\nbeim Handel mit Turbo-Optionsscheinen. Turbo-\nOptionsscheine sind hoch risikoreiche Produkte und\nnicht fur langfristige Anlagestrategien geeignet.\nHallo, haben Sie Fragen? Chat online (°°\n1 @) <\n"};
const wasmCells = {"words": [{"text": "Typ", "bbox": {"x0": 106, "y0": 1146, "x1": 188, "y1": 1196}}, {"text": "Call", "bbox": {"x0": 1226, "y0": 1144, "x1": 1312, "y1": 1186}}, {"text": "4.117,6769", "bbox": {"x0": 728, "y0": 1276, "x1": 988, "y1": 1324}}, {"text": "Basispreis", "bbox": {"x0": 108, "y0": 1308, "x1": 358, "y1": 1360}}, {"text": "®", "bbox": {"x0": 386, "y0": 1308, "x1": 432, "y1": 1356}}, {"text": "05.10.2026)", "bbox": {"x0": 1034, "y0": 1302, "x1": 1310, "y1": 1358}}, {"text": "USD", "bbox": {"x0": 892, "y0": 1334, "x1": 988, "y1": 1374}}, {"text": "(", "bbox": {"x0": 1018, "y0": 1340, "x1": 1030, "y1": 1396}}, {"text": "Knock-Out-Barriere", "bbox": {"x0": 108, "y0": 1478, "x1": 592, "y1": 1518}}, {"text": "4.117,6769", "bbox": {"x0": 728, "y0": 1484, "x1": 988, "y1": 1534}}, {"text": "05.10.2026)", "bbox": {"x0": 1034, "y0": 1510, "x1": 1310, "y1": 1566}}, {"text": "®", "bbox": {"x0": 116, "y0": 1546, "x1": 164, "y1": 1594}}, {"text": "USD", "bbox": {"x0": 892, "y0": 1544, "x1": 988, "y1": 1584}}, {"text": "(", "bbox": {"x0": 1018, "y0": 1550, "x1": 1030, "y1": 1606}}, {"text": "Knock-Out", "bbox": {"x0": 108, "y0": 1672, "x1": 362, "y1": 1712}}, {"text": "Zeit", "bbox": {"x0": 380, "y0": 1672, "x1": 468, "y1": 1712}}, {"text": "00:00", "bbox": {"x0": 1012, "y0": 1674, "x1": 1138, "y1": 1714}}, {"text": "-", "bbox": {"x0": 1156, "y0": 1696, "x1": 1168, "y1": 1700}}, {"text": "24:00", "bbox": {"x0": 1186, "y0": 1674, "x1": 1312, "y1": 1714}}]};
const recovered=b.recoverTermRows(wasmPrimary,wasmCells);
const wasmTerms=b.detailScreenshotData(recovered,'DE000FG5NMF2');
assert(wasmTerms.ok,wasmTerms.reason);
for(const key of ['strike','ko']){assert.equal(wasmTerms.terms[key].value,4117.6769);assert.equal(wasmTerms.terms[key].dateText,'05.10.2026');assert.equal(wasmTerms.terms[key].at,null);}
assert.equal(wasmTerms.terms.ratio.value,.1);
assert(!b.detailScreenshotData(recovered,'DE000FG309G0').ok);
const noStrike={words:wasmCells.words.filter(w=>!(w.text==='4.117,6769'&&w.bbox.y0<1400))};
assert(b.recoverTermRows(wasmPrimary,noStrike).includes('Basispreis ® pall'));
const duplicate={words:wasmCells.words.concat(wasmCells.words.find(w=>w.text==='4.117,6769'))};
assert(b.recoverTermRows(wasmPrimary,duplicate).includes('Basispreis ® pall'));
const conflicting={text:wasmPrimary.text.replace('Basispreis ® pall (22:10:2028)','Basispreis 4.118,0000 USD')};
assert(b.recoverTermRows(conflicting,wasmCells).includes('Basispreis 4.118,0000 USD'));
const noCurrency={words:wasmCells.words.filter(w=>w.text!=='USD')};
assert.equal(b.recoverTermRows(wasmPrimary,noCurrency),wasmPrimary.text);
console.log('Actual WASM table recovery, independent cells, conflicts, identity and date-only freshness passed');

// Automatic acceptance derives from the matched image and unchanged evidence.
const autoShot=b.mergeScreenshotEvidence(null,wasmTerms,'SG-Stammdaten.jpg');
const autoProduct={isin:'DE000FG5NMF2',productDirection:'LONG',ko:4117.6769,snapshot:autoShot};
assert(b.automaticIdentity(autoProduct));
assert(!b.automaticIdentity({...autoProduct,ko:4100}));
assert(!b.automaticIdentity({...autoProduct,productDirection:'SHORT'}));
assert(!b.automaticIdentity({...autoProduct,isin:'DE000FG309G0'}));
assert(!b.automaticIdentity({isin:'DE000FG5NMF2',isinConfirmed:true}));
const autoStatus=b.productTermsStatus({...autoProduct,isinConfirmed:b.automaticIdentity(autoProduct)},Date.parse('2026-10-05T11:00:00Z'));
assert.equal(autoStatus.values.ratio,.1);
assert.equal(autoStatus.values.type,'BEST Turbo-Optionsscheine (Open-End)');
assert.equal(autoStatus.values.maturity,'Open End');
assert(autoStatus.reasons.some(r=>r.includes('Gold allein')));
assert(autoStatus.reasons.some(r=>r.includes('belegter Zeitbezug fehlt')));
assert(b.productTermsStatus({...autoProduct,isinConfirmed:true},Date.parse('2026-10-05T22:00:00Z')).reasons.some(r=>r.includes('belegter Zeitbezug fehlt')));
assert(!autoStatus.complete);
assert.equal(autoShot.terms.strike.at,null);
assert(!b.automaticCondition({source:'image',value:0},'ratio'));
assert(!b.automaticCondition({source:'image',value:.1,conflict:true},'ratio'));
const autoQuote=b.detailScreenshotData('WKN FG5NMF\nTyp Call\nGeld 4,69 EUR\nBrief 4,70 EUR','DE000FG5NMF2');
const quoteProduct={isin:autoQuote.isin,productDirection:'LONG',price:4.7,snapshot:b.mergeScreenshotEvidence(null,autoQuote,'quote.jpg')};
assert(b.automaticIdentity(quoteProduct));
assert(!b.automaticIdentity({...quoteProduct,price:4.8}));
console.log('Automatic image acceptance without user flag; wrong identity, edits and missing evidence remain blocked');
