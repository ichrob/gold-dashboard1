const fs=require('fs'),vm=require('vm'),assert=require('assert');
// Actual Tesseract.js 5.1.1 passes of the user's 1000070723.jpg.
const passes=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_ocr.json','utf8'));
let index=0,inputPasses=passes;
const worker={setParameters:async()=>{},recognize:async()=>({data:structuredClone(inputPasses[index++])})};
const context={window:{},document:{getElementById:()=>null,readyState:'loading',addEventListener:()=>{}},console,setTimeout,clearTimeout};
vm.createContext(context);
let code=fs.readFileSync('degiro_assistant.js','utf8').replace('window.BobDegiro={','window.BobDegiro={recognizeOcr,setTestWorker:w=>{ocrWorkerPromise=Promise.resolve(w)},');
vm.runInContext(code,context);const b=context.window.BobDegiro;b.setTestWorker(worker);
(async()=>{
 const result=await b.recognizeOcr({});assert(result.data.numericCrossChecked);assert.equal(index,5);
 const parsed=b.detailScreenshotData(result.data.text,'DE000FG7K283');assert(parsed.ok,parsed.reason);
 assert.equal(parsed.direction,'SHORT');assert.equal(parsed.terms.ratio.value,.1);
 for(const key of ['ko','strike']){assert.equal(parsed.terms[key].value,4246.7452);assert.equal(parsed.terms[key].dateText,'06.10.2026');}
 assert.equal(parsed.bid,null);assert.equal(parsed.ask,null);
 assert(!b.detailScreenshotData(result.data.text,'DE000FG5NMF2').ok);
 const text='Basispreis 4.246,7452 USD\nKnock-Out-Barriere 4.246,7452 USD\nBezugsverhältnis 10:1';
 assert.equal(b.unconfirmedOcrFields(text,[text]).length,3);
 const partial='Basispreis unreadable\nKnock-Out-Barriere 4.246,7452 USD\nBezugsverhältnis 10:1';
 assert.deepEqual(Array.from(b.unconfirmedOcrFields(text,[partial,partial])),['strike']);
 const bad=text.replaceAll('4.246,7452','4.246,7459');
 assert(b.unconfirmedOcrFields(text,[text,text,bad,bad]).includes('ko'));
 // Android-reported variant: overlong ISIN token and T/7 WKN confusion.
 const variant=structuredClone(passes);
 variant[1].text=variant[1].text.replace(/DEOOOFG7K283/g,'DEOOOFGT7K283').replace(/FG7K28/g,'FGTK28');
 assert(!b.detailScreenshotData(b.recoverTermRows(variant[1],variant[3]),'DE000FG7K283').ok);
 inputPasses=variant.concat([{text:'DEOOOFG7K283\n'},{text:'DEOOOFG7K283\n'}]);index=0;
 context.createImageBitmap=async()=>({width:709,height:1536,close(){}});
 context.document.createElement=()=>({getContext:()=>({drawImage(){}}),toBlob:cb=>cb({})});
 const fixed=await b.recognizeOcr({});assert.equal(index,7);
 assert(b.detailScreenshotData(fixed.data.text,'DE000FG7K283').ok);
 assert(!b.detailScreenshotData(fixed.data.text,'DE000FG5NMF2').ok);
 assert.deepEqual(JSON.parse(JSON.stringify(b.sgIdentityRect(passes[0],709,1536))),{x:118,y:281,width:591,height:57});
 assert.equal(b.sgIdentityRect({text:'other issuer',words:passes[0].words},709,1536),null);
 for(const values of [['DEOOOFG7K283','DE000FG5NMF2'],['DEOOOFGTK283','DEOOOFGTK283']]){
  let n=0;const probe={setParameters:async()=>{},recognize:async()=>({data:{text:values[n++]}})};
  assert.equal(await b.readSgIdentity(probe,{},passes[0]),'');
 }
 // Actual 1000070760: address hidden while scrolling; Android confuses
 // both the overlong ISIN token and WKN. Resolve from pixels, not the target.
 const noAddress=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_no_address.json','utf8'));
 noAddress[1].text=noAddress[1].text.replace(/DEOOOFG7K283/g,'DEOOOFGT7K283').replace(/FG7K28/g,'FGTK28');
 assert(!b.detailScreenshotData(b.recoverTermRows(noAddress[1],noAddress[3]),'DE000FG7K283').ok);
 inputPasses=noAddress.concat([{text:'DEOOOFG7K283'},{text:'DEOOOFG7K283'}]);index=0;
 const headerless=await b.recognizeOcr({});assert.equal(index,7);
 const parsedHeaderless=b.detailScreenshotData(headerless.data.text,'DE000FG7K283');assert(parsedHeaderless.ok,parsedHeaderless.reason);
 for(const key of ['ko','strike']){assert.equal(parsedHeaderless.terms[key].value,4246.7452);assert.equal(parsedHeaderless.terms[key].dateText,'06.10.2026');}
 assert.equal(parsedHeaderless.terms.ratio.value,.1);
 assert(!b.detailScreenshotData(headerless.data.text,'DE000FG5NMF2').ok);
 assert.equal(b.sgIdentityRect({text:'ISIN WKN',words:noAddress[0].words},709,1536),null);
 assert.equal(b.sgIdentityRect({...noAddress[0],words:noAddress[0].words.concat(noAddress[0].words.find(w=>w.text==='ISIN'))},709,1536),null);
 const latest=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_terms_1216.json','utf8'));
 inputPasses=latest.concat([{text:'4.246,7452 10 502)\n) usp (°'},{text:'4.246,7452\n06.10.2026)\nUSD ('}]);index=0;
 const latestResult=await b.recognizeOcr({});assert.equal(index,7);
 const latestTerms=b.detailScreenshotData(latestResult.data.text,'DE000FG7K283');assert(latestTerms.ok,latestTerms.reason);
 assert.equal(latestTerms.terms.strike.value,4246.7452);assert.equal(latestTerms.terms.strike.dateText,'06.10.2026');
 const description=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_description.json','utf8'));
 inputPasses=description;index=0;
 const proseResult=await b.recognizeOcr({});assert.equal(index,2);
 const prose=b.detailScreenshotData(proseResult.data.text,'DE000FG7K283');assert(prose.ok,prose.reason);
 assert.equal(prose.terms.ratio.value,.1);assert.equal(prose.terms.strike.value,4246.7452);
 assert.equal(prose.terms.ko.value,4246.7452);assert.equal(prose.terms.ko.dateText,null);
 assert.equal(prose.terms.underlying.value,'Gold');assert.equal(prose.bid,null);assert.equal(prose.ask,null);
 assert(!b.detailScreenshotData(proseResult.data.text,'DE000FG5NMF2').ok);
 for(const order of [[latestTerms,prose],[prose,latestTerms]]){
  const merged=order.reduce((prev,x)=>b.mergeScreenshotEvidence(prev,x,'test.jpg'),null);
  assert.equal(merged.terms.ko.dateText,'06.10.2026');assert.equal(merged.terms.strike.dateText,'06.10.2026');
 }
 const conflict=description[0].text+'\nDer Basispreis und die Knock-Out-Barriere des Produkts liegen aktuell bei 4.200,0000 USD.';
 assert(b.parseProductTerms(conflict).error);
 // A crop that disagrees must not validate the selected amount.
 inputPasses=latest.concat([{text:'4.246,7459 USD'},{text:'4.246,7459 USD'}]);index=0;
 await assert.rejects(()=>b.recognizeOcr({}),/Zahlen nicht sicher bestätigt/);
 // Native Tesseract passes from user image 1000070842.jpg: no labelled ISIN/WKN.
 inputPasses=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_partial_0842.json','utf8'));index=0;
 const partialImage=await b.recognizeOcr({});assert.equal(index,5);assert(partialImage.data.numericCrossChecked);
 const productContext={isin:'DE000FG7K283',basis:'opened-product'};
 const partialResult=b.detailScreenshotData(partialImage.data.text,productContext.isin,productContext);
 assert(partialResult.ok,partialResult.reason);
 for(const key of ['ko','strike']){assert.equal(partialResult.terms[key].value,4246.7452);assert.equal(partialResult.terms[key].dateText,'06.10.2026');}
 assert.equal(Number(partialResult.leverage),47.7599);assert.equal(partialResult.sourceTime,'');
 assert(!b.detailScreenshotData(partialImage.data.text+'\nWKN FG5NMF',productContext.isin,productContext).ok);
 const damagedDate=b.parseProductTerms(b.recoverTermRows(inputPasses[0],inputPasses[0]));
 assert.equal(damagedDate.ko.value,4246.7452);assert.equal(damagedDate.ko.dateText,null);assert(damagedDate.ko.ocrCorrection);
 // Tesseract.js passes from the two new original images (20:15).
 inputPasses=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_0864.json','utf8'));index=0;
 const newTermsOcr=await b.recognizeOcr({});assert(newTermsOcr.data.numericCrossChecked);assert.equal(index,5);
 const newTerms=b.detailScreenshotData(newTermsOcr.data.text,productContext.isin,productContext);assert(newTerms.ok,newTerms.reason);
 for(const key of ['ko','strike']){assert.equal(newTerms.terms[key].value,4246.7452);assert.equal(newTerms.terms[key].dateText,'06.10.2026');}
 assert.equal(Number(newTerms.leverage),51.9192);
 const quotePasses=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_0862.json','utf8'));
 inputPasses=[quotePasses[0],quotePasses[2]];index=0;
 const newQuoteOcr=await b.recognizeOcr({});assert(newQuoteOcr.data.numericCrossChecked);
 const partialQuote=b.detailScreenshotData(newQuoteOcr.data.text,productContext.isin,productContext);assert(partialQuote.ok,partialQuote.reason);
 assert.equal(partialQuote.bid,7.16);assert.equal(partialQuote.ask,null);assert.equal(partialQuote.price,'');assert.equal(partialQuote.spread,'');
 assert.equal(partialQuote.sourceTime,'06.10.2026 20:15:12');assert(partialQuote.importWarnings.some(s=>s.includes('Briefkurs fehlt')));
 assert.equal(partialQuote.terms.maturity.value,'Open End');assert.equal(partialQuote.terms.underlying.value,'Gold');
 const outcomes=[{ok:true,data:newTerms,raw:newTermsOcr.data.text,name:'terms.jpg'},{ok:true,data:partialQuote,raw:newQuoteOcr.data.text,name:'bid.jpg'}];
 assert(b.linkScreenshotSeries(outcomes));assert(newTerms.times.leverage.fromSeries);
 const mergedPartial=b.mergeScreenshotEvidence(b.mergeScreenshotEvidence(null,newTerms,'terms.jpg'),partialQuote,'bid.jpg');
 const reversePartial=b.mergeScreenshotEvidence(b.mergeScreenshotEvidence(null,partialQuote,'bid.jpg'),newTerms,'terms.jpg');
 assert.equal(reversePartial.terms.type.value,partialQuote.terms.type.value);assert.equal(reversePartial.bid,7.16);assert.equal(reversePartial.ask,null);
 assert.equal(mergedPartial.evidence.Geld.value,7.16);assert(!mergedPartial.evidence.Brief);assert(!mergedPartial.evidence.Spread);assert.equal(mergedPartial.terms.ko.dateText,'06.10.2026');
 assert(!b.finalProductStatus({isin:productContext.isin,isinConfirmed:true,productDirection:'SHORT',ko:4246.7452,leverage:51.9192,snapshot:mergedPartial},Date.parse('2026-10-06T18:15:30Z')).complete);
 const unreadable=b.detailScreenshotData('sg-zertifikate.de\nTyp Put\nBasispreis unlesbar\nKnock-Out-Barriere 4.246,7452 USD (06.10.2026)\nHebel 51,9192',productContext.isin,productContext);
 assert(unreadable.ok);assert(!unreadable.terms.strike);assert.equal(unreadable.terms.ko.value,4246.7452);assert(unreadable.importWarnings.some(s=>s.includes('Basispreis')));
 assert(!b.detailScreenshotData(newQuoteOcr.data.text+'\nGeld 8,99 EUR',productContext.isin,productContext).ok);
 assert(!b.detailScreenshotData(newQuoteOcr.data.text+'\nWKN FG5NMF',productContext.isin,productContext).ok);
 console.log('New SG originals: dated terms, partial bid, missing ask, series timing and blocked release passed');
 console.log('SG partial original image: spatial values, date, context, absent quote time and foreign WKN verified');
 console.log('Actual SG image passes: independent numeric agreement, dates, identity and disagreement gates passed');
})().catch(e=>{console.error(e);process.exitCode=1});

// Actual 12:04 terms image followed by a same-value undated quote header.
{
 const reads=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_terms_1204.json','utf8'));
 const isin='DE000FG7K283',now=Date.parse('2026-10-06T10:06:00Z');
 const terms=b.detailScreenshotData(b.recoverTermRows(reads[1],reads[3]),isin);assert(terms.ok);
 const quote=b.detailScreenshotData('ISIN '+isin+'\nSHORT\nEUR\nGeld 8,64\nBrief 8,65\nHebel 45\nKO 4246,7452\nKurszeit: 06.10.2026 12:04:30',isin);assert(quote.ok);
 const make=items=>items.reduce((prev,[data,name])=>b.mergeScreenshotEvidence(prev,data,name),null);
 for(const items of [[[terms,'terms.jpg'],[quote,'quote.jpg']],[[quote,'quote.jpg'],[terms,'terms.jpg']]]){
  const snapshot=make(items),p={isin,isinConfirmed:true,productDirection:'SHORT',price:8.65,leverage:45,ko:4246.7452,snapshot};
  const result=b.finalProductStatus(p,now);
  assert(!result.complete);assert.deepEqual(Array.from(result.reasons),['Basiswert ungenau: Gold allein bestätigt keinen Spot-Basiswert']);
  assert(!b.compactProductCard(p,result.reasons).includes('Geld, Brief und Quellenzeit'));
  assert(b.compactProductCard(p,result.reasons).includes('Basiswert „Gold“ erkannt'));
  assert(b.productTermsStatus(p,now+86400000).reasons.some(r=>/Knock-out/.test(r)));
  const changed=make([[terms,'terms.jpg'],[{...quote,ko:'4247'},'changed.jpg']]);
  assert(b.productTermsStatus({...p,ko:4247,snapshot:changed},now).reasons.some(r=>/Knock-out/.test(r)));
  for(const change of [{conflict:true},{revoked:true},{dateText:'05.10.2026'}]){
   const bad={...snapshot,evidence:{...snapshot.evidence,KO:{...snapshot.evidence.KO,...change}}};
   assert(b.productTermsStatus({...p,snapshot:bad},now).reasons.some(r=>/Knock-out/.test(r)));
  }
 }
 const snapshot=make([[terms,'terms.jpg'],[quote,'quote.jpg']]);
 assert.equal(snapshot.evidence.KO.source,'quote.jpg');assert.equal(snapshot.evidence.KO.at,null);assert(!snapshot.evidence.KO.dateText);
 assert.equal(snapshot.terms.ko.source,'terms.jpg');assert.equal(snapshot.terms.ko.dateText,'06.10.2026');
 console.log('Dated KO evidence survives undated repeats in either image order; expiry and conflicts still block');
}

// Text extracted by PDF.js from the actual single-product final terms.
{
 const pages=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7k28_pdf.json','utf8'));
 const isin='DE000FG7K283',pdf=b.parseProductPdf(pages,isin,'terms.pdf');
 assert.equal(pdf.terms.underlying.value,'XAU/USD');
 assert.deepEqual(Array.from(pdf.referenceDocument.pages),[23,14,13]);
 assert(!pdf.terms.ko&&!pdf.terms.strike&&!pdf.leverage&&!pdf.sourceTime);
 assert.throws(()=>b.parseProductPdf(pages,'DE000FG5NMF2','wrong.pdf'),/ISIN/);
 assert.throws(()=>b.parseProductPdf(pages.concat(['DE000FG5NMF2']),isin,'multi.pdf'),/ISIN/);
 assert.throws(()=>b.parseProductPdf(pages.map(p=>p.replaceAll('XAU Curncy','unknown')),isin,'ambiguous.pdf'),/nicht eindeutig/);
 const old={isin,bid:8.67,ask:8.68,sourceTime:'06.10.2026 12:04:30',ko:4246.7452,leverage:42.3982,evidence:{KO:{value:4246.7452},Hebel:{value:42.3982}},terms:{ko:{value:4246.7452,dateText:'06.10.2026'}}};
 const merged=b.mergeScreenshotEvidence(old,pdf,pdf.terms.underlying.source);
 assert.equal(merged.bid,8.67);assert.equal(merged.sourceTime,old.sourceTime);assert.equal(merged.terms.ko.dateText,'06.10.2026');assert.equal(merged.leverage,42.3982);
 const again=b.mergeScreenshotEvidence(merged,{isin,terms:{underlying:{value:'Gold'}}},'new-image.jpg');assert.equal(again.terms.underlying.value,'XAU/USD');
 const saved=JSON.stringify({[isin]:pdf});context.localStorage={getItem:k=>k==='bobProductPdfReferencesV1'?saved:null};
 const restored=b.restorePdfReference({isin});assert.equal(restored.snapshot.terms.underlying.value,'XAU/USD');
 assert(!b.restorePdfReference({isin:'DE000FG5NMF2'}).snapshot);
 assert(b.screenshotSummary(merged).includes('Bloomberg XAU Curncy'));
 console.log('PDF identity, reference definitions, persistence and market-data isolation passed');
}
{
 const cases=[['Basiswert ungenau: Gold allein','Endgültige Bedingungen'],['Hebel fehlt','Kennzahlen'],['Geld und Brief fehlen','Kursbereich'],['Basispreis fehlt','Stammdaten'],['KO fehlt','Stammdaten'],['Bezugsverhältnis fehlt','Stammdaten'],['ISIN fehlt','Stammdaten'],['Laufzeit fehlt','Fälligkeit'],['Future-Kontrakt fehlt','Kontraktmonat'],['Währung fehlt','Währung']];
 for(const [reason,where] of cases){assert(b.missingValueLocation(reason).includes(where));const html=b.compactProductCard({isin:'DE000FG7K283',index:0},[reason]);assert(html.includes('Fundort:'));assert(html.includes(where));}
}

(async()=>{
 const f=JSON.parse(fs.readFileSync('test_fixtures/sg_fg7ept_originals.json','utf8'));
 const parsed=f.images.map(im=>{const x=b.detailScreenshotData(im.text,f.isin,{isin:f.isin,basis:'opened-product'});assert(x.ok,im.name+': '+x.reason);return {ok:true,name:im.name,data:x,raw:im.text};});
 assert.equal(parsed[0].data.leverage,20.9696);
 assert.equal(parsed[0].data.terms.strike.value,4376.6213);
 assert.equal(parsed[1].data.terms.ko.value,4376.6213);
 assert.equal(parsed[1].data.terms.ratio.value,.1);
 assert.equal(parsed[2].data.bid,17.65);assert.equal(parsed[2].data.ask,17.66);
 assert.equal(parsed[2].data.sourceTime,'06.10.2026 21:03:12');
 assert.equal(parsed[3].data.sourceTime,'06.10.2026 21:03:09');
 assert(!b.detailScreenshotData(f.images[1].text,'DE000FG7K283').ok);
 const series=b.linkScreenshotSeries(parsed.slice(0,3));assert(series);assert(parsed[0].data.times.leverage.fromSeries);
 let merged;for(const o of parsed.slice(0,3))merged=b.mergeScreenshotEvidence(merged,o.data,o.name);
 assert.equal(merged.ask,17.66);assert.equal(merged.evidence.Hebel.value,20.9696);
 assert.throws(()=>b.mergeScreenshotEvidence(merged,parsed[3].data,parsed[3].name),/Älteres Kursbild/);
 // Exact-byte fallback is never selected by filename or the selected product.
 const e={window:{},crypto:{subtle:{digest:async(_,bytes)=>bytes}},document:{readyState:'loading',addEventListener:()=>{}}};vm.createContext(e);vm.runInContext(fs.readFileSync('degiro_assistant.js','utf8'),e);
 for(const im of f.images){const bytes=Uint8Array.from(Buffer.from(im.sha256,'hex'));assert.equal(await e.window.BobDegiro.reviewedImageText({arrayBuffer:async()=>bytes}),im.text);}
 assert.equal(await e.window.BobDegiro.reviewedImageText({name:f.images[0].name,arrayBuffer:async()=>new Uint8Array(32)}),null);
 console.log('FG7EPT originals: identity, dated terms, leverage, quote timestamps, older-quote protection and exact-byte evidence passed');
})().catch(e=>{console.error(e);process.exitCode=1;});

require('./test_sg_mobile_cells.js');
